#!/usr/bin/env python3
"""
Exhaustively verify that every headword and every inflected form in the
vendored SQLite database resolves correctly in the built StarDict
dictionary.

For each row in `word` (with non-NULL meaning):
  - the `name` must resolve to itself
  - every `derivative_form.name` whose `base_word_id` points to this word
    must resolve to this word

Verification is done via sdcv (the same lookup logic KOReader uses), with
batched queries for speed. The script exits 0 on full coverage and 1 on
any miss or wrong headword.

Credits / data sources: see vendor/README.md and the project README.md.
This script does not produce dictionary content; it only checks that the
conversion preserved every entry from the source database.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_DB = REPO_ROOT.joinpath("vendor", "db.sqlite")
DEFAULT_DATA_DIR = REPO_ROOT.joinpath("out", "stardict")
DEFAULT_DICT_NAME = "bulgarian"


def build_expected_map(conn: sqlite3.Connection) -> dict[str, set[str]]:
    """Return {surface_form -> {legitimate_headword(s)}}.

    Replicates the build pipeline's choice that lowest-id wins per name -
    but for verification purposes, if a surface form (headword or inflected)
    legitimately maps to multiple possible canonical headwords, we accept
    any of them as a valid answer.
    """
    cur = conn.cursor()
    expected: dict[str, set[str]] = {}

    # All headwords with meanings.
    cur.execute(
        "SELECT id, name FROM word "
        "WHERE meaning IS NOT NULL "
        "ORDER BY name ASC, id ASC"
    )
    word_id_to_name: dict[int, str] = {}
    for wid, name in cur.fetchall():
        if not name:
            continue
        word_id_to_name[wid] = name
        # The headword resolves to itself.
        expected.setdefault(name, set()).add(name)

    # Inflected forms pointing back to a kept word.
    cur.execute("SELECT base_word_id, name FROM derivative_form")
    for base_id, fname in cur.fetchall():
        if base_id is None or not fname:
            continue
        if " " in fname:
            # Upstream excludes multi-word derivative forms; we match that.
            continue
        canonical = word_id_to_name.get(base_id)
        if canonical is None:
            # The derivative points to a stub word (NULL meaning) that we
            # did not export. Ignore - the form isn't expected to resolve.
            continue
        expected.setdefault(fname, set()).add(canonical)

    return expected


def chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def lookup_batch(words: list[str], data_dir: Path) -> list[list[dict]]:
    cmd = [
        "sdcv",
        "--non-interactive",
        "--json-output",
        "--exact-search",
        "--utf8-input",
        "--utf8-output",
        "--data-dir", str(data_dir),
        "--only-data-dir",
        "--",
        *words,
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", check=False
    )
    # sdcv exits 2 when ANY queried word has no match; the output is still
    # well-formed JSON ([] for misses), so we treat that exit as non-fatal.
    if proc.returncode not in (0, 2):
        sys.stderr.write(f"sdcv failed (exit {proc.returncode}):\n{proc.stderr}\n")
        sys.exit(2)

    results: list[list[dict]] = []
    # Parse the output as a stream of top-level JSON values, NOT line by line.
    # sdcv emits one JSON array per query, but the precise output framing
    # depends on the build: some versions print plain "[]\n[...]\n", others
    # interleave informational messages on stdout (e.g. "save to cache ..."
    # on first run with a cold cache), and a JSON string with an embedded
    # literal newline would also split across two lines. The raw_decode
    # loop sidesteps all of that by consuming exactly one JSON value at a
    # time and skipping any non-JSON noise between values.
    decoder = json.JSONDecoder()
    text = proc.stdout
    pos = 0
    n = len(text)
    while pos < n:
        # Skip whitespace and any non-JSON noise until we find '[' (the
        # start of an sdcv result array).
        while pos < n and text[pos] != "[":
            pos += 1
        if pos >= n:
            break
        try:
            value, end = decoder.raw_decode(text, pos)
        except json.JSONDecodeError as e:
            sys.stderr.write(
                f"Bad JSON from sdcv at offset {pos}: {e}\n"
                f"  near={text[pos:pos + 200]!r}\n"
            )
            sys.exit(2)
        results.append(value)
        pos = end

    if len(results) != len(words):
        sys.stderr.write(
            f"sdcv returned {len(results)} JSON lines for {len(words)} queries; "
            "cannot align results.\n"
        )
        sys.exit(2)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--dict-name", default=DEFAULT_DICT_NAME)
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--max-misses", type=int, default=20)
    args = parser.parse_args()

    ifo = args.data_dir.joinpath(args.dict_name, f"{args.dict_name}.ifo")
    if not ifo.exists():
        sys.exit(f"FATAL: built dictionary not found at {ifo}. Run `make build` first.")
    if not args.db.is_file():
        sys.exit(f"FATAL: SQLite database not found at {args.db}.")

    print(f"Building expected word -> headword map from {args.db} ...", flush=True)
    conn = sqlite3.connect(str(args.db))
    try:
        expected = build_expected_map(conn)
    finally:
        conn.close()
    words = sorted(expected.keys())
    total = len(words)
    print(f"Verifying {total} unique surface forms against {args.dict_name} via sdcv...", flush=True)

    misses: list[tuple[str, set[str], list[str]]] = []
    wrong_headword: list[tuple[str, set[str], list[str]]] = []
    n_ok = 0
    progress_every = max(1, total // 20)

    for chunk_idx, chunk in enumerate(chunked(words, args.batch_size)):
        results = lookup_batch(chunk, args.data_dir)
        for word, hits in zip(chunk, results):
            expected_heads = expected[word]
            if not hits:
                misses.append((word, expected_heads, []))
                continue
            returned = [h.get("word", "") for h in hits]
            if any(r in expected_heads for r in returned):
                n_ok += 1
            else:
                wrong_headword.append((word, expected_heads, returned))

        done = min(total, (chunk_idx + 1) * args.batch_size)
        if done % progress_every < args.batch_size:
            print(
                f"  ... {done}/{total} checked  "
                f"(ok={n_ok}, miss={len(misses)}, wrong={len(wrong_headword)})",
                flush=True,
            )

    print()
    print(f"Resolved correctly:    {n_ok}/{total}")
    print(f"Missing from dict:     {len(misses)}")
    print(f"Resolved to wrong hw:  {len(wrong_headword)}")

    if misses:
        print()
        print(f"First {min(len(misses), args.max_misses)} missing words:")
        for word, expected_heads, _ in misses[:args.max_misses]:
            print(f"  {word!r}  (expected one of {sorted(expected_heads)})")
    if wrong_headword:
        print()
        print(f"First {min(len(wrong_headword), args.max_misses)} surface forms resolving to wrong headword:")
        for word, expected_heads, returned in wrong_headword[:args.max_misses]:
            print(f"  {word!r}  expected one of {sorted(expected_heads)}, got {returned}")

    if misses or wrong_headword:
        print()
        print("FAIL: not every database entry is fully represented in the StarDict output.")
        return 1

    print()
    print("PASS: every database headword and every inflected form resolves to a canonical entry.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
