#!/usr/bin/env python3
"""
Build a Bulgarian StarDict dictionary by querying the vendored SQLite
database directly.

Usage:
    python3 scripts/build_stardict.py [--db PATH] [--out PATH]

Default paths:
    --db   vendor/db.sqlite          (committed; ~250 MB uncompressed)
    --out  out/stardict/bulgarian    (StarDict files written here)

The build pipeline:
    1. Query word table for (id, name, meaning) where meaning is not NULL,
       ordered by (name ASC, id ASC). Lowest-id wins per name (so each
       headword maps to exactly one canonical id, even when the source
       database has homograph rows for the same name).
    2. For each kept word, query derivative_form for its inflected forms.
    3. Render meaning text through format_meaning (raw Речко markup to HTML).
    4. Feed entries to PyGlossary's Glossary API and write StarDict output.

Inflected forms become StarDict alternates, so KOReader (and any other
StarDict-compatible reader) resolves declined Bulgarian words to the
correct headword entry.

Credits / data sources: see vendor/README.md and the project README.md.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# Local imports
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
from format_meaning import format_meaning  # noqa: E402

from pyglossary.glossary_v2 import Glossary  # noqa: E402


DEFAULT_DB = REPO_ROOT.joinpath("vendor", "db.sqlite")
DEFAULT_OUT = REPO_ROOT.joinpath("out", "stardict", "bulgarian")


def collect_entries(conn: sqlite3.Connection):
    """Yield (headword, [alt forms], rendered meaning HTML) per dictionary entry.

    Matches yanosh-k upstream semantics:
      - Only words with a non-NULL meaning are exported.
      - Homographs: lowest id wins per name.
      - The alt list includes inflected forms from derivative_form, deduped
        and excluding the headword itself.
    """
    cur = conn.cursor()

    # Build the set of known headwords so format_meaning can decide whether
    # to turn [[xref]] markup into a clickable bword:// link or to fall back
    # to plain text.
    cur.execute("SELECT name FROM word WHERE meaning IS NOT NULL")
    known_words: set[str] = {name for (name,) in cur.fetchall() if name}

    # Iterate dictionary entries (the "first by name asc, id asc" wins again).
    entries_cur = conn.cursor()
    entries_cur.execute(
        "SELECT id, name, meaning FROM word "
        "WHERE meaning IS NOT NULL "
        "ORDER BY name ASC, id ASC"
    )

    # Cache derivative-form lookups by NAME (not by base id). This way, when
    # two `word` rows share a name (homograph - e.g. два беля), we collect
    # inflections from BOTH base words and surface them all under the single
    # exported headword. The upstream PHP pipeline dropped one homograph's
    # inflections entirely (`if (!isset($keyedWords[$name]))` -> first wins);
    # building straight from SQLite lets us recover them.
    #
    # word_id -> name, used so we can group the per-base-id rows by name.
    wid_cur = conn.cursor()
    wid_cur.execute("SELECT id, name FROM word")
    wid_to_name: dict[int, str] = {wid: nm for wid, nm in wid_cur.fetchall() if nm}

    forms_by_name: dict[str, list[str]] = {}
    df_cur = conn.cursor()
    df_cur.execute("SELECT base_word_id, name FROM derivative_form ORDER BY base_word_id, name")
    for base_id, fname in df_cur.fetchall():
        if base_id is None or not fname:
            continue
        # Upstream excluded forms containing spaces (the 1b70524 commit by
        # @dannywinrow). Match that.
        if " " in fname:
            continue
        base_name = wid_to_name.get(base_id)
        if base_name is None:
            continue
        forms_by_name.setdefault(base_name, []).append(fname)

    seen_names: set[str] = set()
    for wid, name, raw_meaning in entries_cur.fetchall():
        if not name or name in seen_names:
            continue
        seen_names.add(name)

        rendered = format_meaning(raw_meaning, known_words) if raw_meaning else ""
        # Empty meaning becomes a placeholder dash so the entry is still
        # discoverable - two such words exist in the source data (see
        # vendor/README.md for details).
        if not rendered.strip():
            rendered = "—"

        # Build the alt list: inflected forms (deduped, headword removed).
        # Pulled by NAME so all homographs' inflections roll up here.
        alts: list[str] = []
        seen_in_entry = {name}
        for f in forms_by_name.get(name, []):
            if f not in seen_in_entry:
                seen_in_entry.add(f)
                alts.append(f)

        yield name, alts, rendered


def build(db_path: Path, out_dir: Path) -> None:
    if not db_path.is_file():
        sys.exit(f"FATAL: SQLite database not found at {db_path}")

    Glossary.init()
    glos = Glossary()
    glos.setInfo("title", "Български тълковен речник")
    glos.setInfo("author", "chitanka.info")
    glos.setInfo("description", "Български тълковен речник")
    glos.setInfo("sourceLang", "Bulgarian")
    glos.setInfo("targetLang", "Bulgarian")

    print(f"Reading entries from {db_path} ...", flush=True)
    total = with_alts = 0
    conn = sqlite3.connect(str(db_path))
    try:
        for headword, alts, rendered in collect_entries(conn):
            entry = glos.newEntry(
                word=[headword] + alts,
                defi=rendered,
                defiFormat="h",
            )
            glos.addEntry(entry)
            total += 1
            if alts:
                with_alts += 1
            if total % 5000 == 0:
                print(f"  ... {total} entries collected", flush=True)
    finally:
        conn.close()
    print(f"Loaded {total} entries ({with_alts} with inflected forms)", flush=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.iterdir():
        old.unlink()

    print(f"Writing StarDict to {out_dir} ...", flush=True)
    glos.write(
        str(out_dir.joinpath("bulgarian")),
        formatName="Stardict",
        dictzip=True,
    )
    print("Done.")
    for p in sorted(out_dir.iterdir()):
        print(f"  {p.name}  ({p.stat().st_size:,} bytes)")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    build(args.db, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
