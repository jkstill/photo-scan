#!/usr/bin/env python3
"""Rebuild the photo_tags lookup table from photo_ai.tags_json."""

import argparse
import os
import sqlite3
import sys

REBUILD_SQL_DELETE = "DELETE FROM photo_tags"
REBUILD_SQL_INSERT = """
    INSERT INTO photo_tags (tag, tag_count)
    SELECT je.value, COUNT(*)
    FROM photo_ai p, json_each(p.tags_json) je
    WHERE je.value IS NOT NULL
    GROUP BY je.value
"""

DUMP_SQL = "SELECT tag, tag_count FROM photo_tags ORDER BY tag"


def rebuild_tags(conn) -> int:
    """Rebuild photo_tags from photo_ai.tags_json. Returns the resulting tag count."""
    cur = conn.cursor()
    cur.execute(REBUILD_SQL_DELETE)
    cur.execute(REBUILD_SQL_INSERT)
    cur.execute("SELECT COUNT(*) FROM photo_tags")
    count = cur.fetchone()[0]
    conn.commit()
    return count


def dump_tags(conn, out) -> None:
    cur = conn.cursor()
    cur.execute(DUMP_SQL)
    for tag, tag_count in cur:
        out.write(f"{tag}\t{tag_count}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Rebuild the photo_tags lookup table from photo_ai.tags_json.")
    ap.add_argument("--db", default=os.environ.get("PHOTO_DB", "photos.db"), help="Path to the SQLite database file.")
    ap.add_argument(
        "--dump", nargs="?", const="-", default=None, metavar="FILE",
        help="Dump tag/count as tab-separated text instead of rebuilding. Writes to stdout, or FILE if given.",
    )
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    try:
        if args.dump is not None:
            if args.dump == "-":
                dump_tags(conn, sys.stdout)
            else:
                with open(args.dump, "w", encoding="utf-8") as f:
                    dump_tags(conn, f)
        else:
            count = rebuild_tags(conn)
            print(f"Rebuilt photo_tags: {count} tags.")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        raise SystemExit(0)
