#!/usr/bin/env python3
"""
One-shot migration: parse a MySQL dump of the "Речко" database and produce a
tailored SQLite database containing only the tables and columns we actually
need to build a Bulgarian StarDict dictionary.

Usage:
    python3 scripts/dump_to_sqlite.py <db.sql> <output.sqlite>

Uses only the Python standard library. Streams the input line by line so
memory usage stays modest even on the ~700 MB upstream dump.

Tables kept (only the dictionary-relevant columns):
    word              id, name, name_stressed, name_broken, meaning,
                      synonyms, classification, type_id, pronounciation,
                      etymology, related_words, derived_words
    derivative_form   id, name, base_word_id
    word_type         id, name, speech_part
    incorrect_form    id, name, correct_word_id

Tables intentionally dropped:
    abstract_word, revision, word_revision, incorrect_form_revision,
    word_translation, sf_guard_user, sf_guard_user_profile, sf_guard_group,
    sf_guard_group_permission, sf_guard_permission, sf_guard_remember_key,
    sf_guard_user_group, sf_guard_user_permission

These are Symfony auth scaffolding and edit-history tables that have no
bearing on the dictionary content.

Credits / data sources: see vendor/README.md and the project README.md.
The dump itself is the property of the chitanka.info community; this
script is only a converter.
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path


# Which columns from each MySQL table we want to import, in the order they
# appear in the dump. Indexes are 0-based and refer to the dump's column
# order (i.e. matching the CREATE TABLE definitions).
TABLES = {
    "word": {
        # Dump column order:
        # 0:id 1:name 2:name_stressed 3:name_broken 4:name_condensed 5:meaning
        # 6:synonyms 7:classification 8:type_id 9:pronounciation 10:etymology
        # 11:related_words 12:derived_words 13:chitanka_count 14:chitanka_percent
        # 15:chitanka_rank 16:search_count 17:source 18:other_langs
        # 19:deleted_at 20:corpus_count 21:corpus_percent 22:corpus_rank
        "keep": {
            0: ("id", "INTEGER PRIMARY KEY"),
            1: ("name", "TEXT"),
            2: ("name_stressed", "TEXT"),
            3: ("name_broken", "TEXT"),
            5: ("meaning", "TEXT"),
            6: ("synonyms", "TEXT"),
            7: ("classification", "TEXT"),
            8: ("type_id", "INTEGER"),
            9: ("pronounciation", "TEXT"),   # sic - upstream typo, preserved
            10: ("etymology", "TEXT"),
            11: ("related_words", "TEXT"),
            12: ("derived_words", "TEXT"),
        },
    },
    "derivative_form": {
        # 0:id 1:name 2:name_stressed 3:name_broken 4:name_condensed
        # 5:description 6:is_infinitive 7:base_word_id 8:search_count
        # 9:corpus_rank 10:corpus_count 11:corpus_percent
        "keep": {
            0: ("id", "INTEGER PRIMARY KEY"),
            1: ("name", "TEXT"),
            7: ("base_word_id", "INTEGER"),
        },
    },
    "word_type": {
        # 0:id 1:name 2:idi_number 3:speech_part 4:comment 5:rules
        # 6:rules_test 7:example_word
        "keep": {
            0: ("id", "INTEGER PRIMARY KEY"),
            1: ("name", "TEXT"),
            3: ("speech_part", "TEXT"),
        },
    },
    "incorrect_form": {
        # 0:id 1:name 2:correct_word_id 3:search_count 4:deleted_at
        "keep": {
            0: ("id", "INTEGER PRIMARY KEY"),
            1: ("name", "TEXT"),
            2: ("correct_word_id", "INTEGER"),
        },
    },
}


# Matches a complete INSERT INTO `tbl` VALUES (...),(...),...,(...); on a
# single physical line (MySQL dumps put each INSERT on one line, even if it
# spans hundreds of kilobytes).
INSERT_RE = re.compile(r"^INSERT INTO `([^`]+)` VALUES (.*);\s*$")


# MySQL string escape sequences. Anything not in this map is left as the
# escaped character itself (matching MySQL's behavior for unknown escapes).
ESCAPES = {
    "'": "'",
    '"': '"',
    "\\": "\\",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "0": "\0",
    "Z": "\x1a",
    "b": "\b",
}


def split_tuples(values_clause: str):
    """Iterate over MySQL VALUES tuples, yielding the body between '(' and ')'.

    Handles strings that may contain unescaped commas, parens, or quotes.
    Uses a small state machine rather than regex so we never get fooled by
    string contents that look like tuple boundaries.
    """
    depth = 0
    in_str = False
    start = None
    n = len(values_clause)
    i = 0
    while i < n:
        c = values_clause[i]
        if in_str:
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == "'":
                in_str = False
            i += 1
            continue
        if c == "'":
            in_str = True
            i += 1
            continue
        if c == "(":
            if depth == 0:
                start = i + 1
            depth += 1
            i += 1
            continue
        if c == ")":
            depth -= 1
            if depth == 0:
                yield values_clause[start:i]
                start = None
            i += 1
            continue
        i += 1


def parse_tuple_body(s: str) -> list:
    """Parse the comma-separated fields inside a MySQL tuple body."""
    out = []
    i = 0
    n = len(s)
    while i < n:
        while i < n and s[i] == " ":
            i += 1
        if i >= n:
            break
        c = s[i]
        if c == "'":
            # quoted string
            i += 1
            buf = []
            while i < n:
                ch = s[i]
                if ch == "\\" and i + 1 < n:
                    nxt = s[i + 1]
                    buf.append(ESCAPES.get(nxt, nxt))
                    i += 2
                elif ch == "'":
                    i += 1
                    break
                else:
                    buf.append(ch)
                    i += 1
            out.append("".join(buf))
        elif s[i:i + 4] == "NULL":
            out.append(None)
            i += 4
        else:
            # bareword: number, keyword, identifier
            j = i
            in_str = False
            while j < n:
                cj = s[j]
                if cj == "'" and (j == 0 or s[j-1] != "\\"):
                    in_str = not in_str
                if cj == "," and not in_str:
                    break
                j += 1
            out.append(s[i:j].strip())
            i = j
        # skip the comma separator
        while i < n and s[i] in " ,":
            i += 1
    return out


def create_schema(conn: sqlite3.Connection) -> None:
    """Create the target SQLite schema with only the columns we want."""
    cur = conn.cursor()
    for table, spec in TABLES.items():
        columns_sql = ", ".join(
            f'"{col}" {coltype}'
            for _, (col, coltype) in sorted(spec["keep"].items())
        )
        cur.execute(f'DROP TABLE IF EXISTS "{table}"')
        cur.execute(f'CREATE TABLE "{table}" ({columns_sql})')
    # Useful indexes for our queries.
    cur.execute('CREATE INDEX idx_word_name ON word(name)')
    cur.execute('CREATE INDEX idx_derivative_form_base_word_id ON derivative_form(base_word_id)')
    cur.execute('CREATE INDEX idx_incorrect_form_correct_word_id ON incorrect_form(correct_word_id)')
    conn.commit()


def import_dump(dump_path: Path, conn: sqlite3.Connection) -> dict[str, int]:
    """Stream-parse `dump_path` and insert rows into the SQLite tables."""
    counts: dict[str, int] = {t: 0 for t in TABLES}
    # Track tables we've already seen the first INSERT for, so that on the
    # SECOND duplicate CREATE TABLE / INSERT block in the dump we just keep
    # appending - the dump contains the same data twice in the same shape,
    # and the duplicate is harmless because the primary keys collide and we
    # use INSERT OR IGNORE.
    cur = conn.cursor()

    cur.execute("BEGIN")
    batches: dict[str, list[tuple]] = {t: [] for t in TABLES}
    BATCH_SIZE = 5000

    # Precompute the INSERT statement and column-index list per table.
    inserts: dict[str, tuple[str, list[int]]] = {}
    for table, spec in TABLES.items():
        idxs = sorted(spec["keep"].keys())
        col_names = [spec["keep"][i][0] for i in idxs]
        placeholders = ", ".join(["?"] * len(idxs))
        insert_sql = (
            f'INSERT OR IGNORE INTO "{table}" '
            f'({", ".join(f"\"{c}\"" for c in col_names)}) '
            f'VALUES ({placeholders})'
        )
        inserts[table] = (insert_sql, idxs)

    def flush(table: str) -> None:
        if not batches[table]:
            return
        sql, _ = inserts[table]
        cur.executemany(sql, batches[table])
        batches[table].clear()

    print(f"Reading dump from {dump_path} ...", flush=True)
    with open(dump_path, "r", encoding="utf-8", newline="\n") as f:
        for line_no, line in enumerate(f, 1):
            if not line.startswith("INSERT INTO"):
                continue
            m = INSERT_RE.match(line)
            if not m:
                continue
            table = m.group(1)
            if table not in TABLES:
                continue
            values_clause = m.group(2)
            _, idxs = inserts[table]
            n_idxs = max(idxs) + 1
            for tup_body in split_tuples(values_clause):
                fields = parse_tuple_body(tup_body)
                if len(fields) < n_idxs:
                    # Malformed tuple - skip it loudly.
                    sys.stderr.write(
                        f"  warning: short tuple ({len(fields)} fields) in {table} "
                        f"at line {line_no}; skipping\n"
                    )
                    continue
                row = tuple(fields[i] for i in idxs)
                batches[table].append(row)
                counts[table] += 1
                if len(batches[table]) >= BATCH_SIZE:
                    flush(table)

    for table in TABLES:
        flush(table)
    cur.execute("COMMIT")
    return counts


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        sys.stderr.write(
            "Usage: dump_to_sqlite.py <input.sql> <output.sqlite>\n"
        )
        return 2
    dump_path = Path(argv[1])
    out_path = Path(argv[2])
    if not dump_path.is_file():
        sys.stderr.write(f"Not a file: {dump_path}\n")
        return 2

    if out_path.exists():
        out_path.unlink()

    conn = sqlite3.connect(str(out_path))
    try:
        create_schema(conn)
        counts = import_dump(dump_path, conn)
    finally:
        conn.close()

    size = out_path.stat().st_size
    print(f"\nWrote {out_path}  ({size:,} bytes)")
    print("Row counts:")
    for table, n in counts.items():
        print(f"  {table:18s} {n:>10,}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
