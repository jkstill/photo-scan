#!/usr/bin/env python3
"""Rebuild the photo_tags lookup table from photo_ai.tags_json."""

import argparse
import os
import sys

import oracledb

REBUILD_SQL_DELETE = "DELETE FROM photo_tags"
REBUILD_SQL_INSERT = """
    INSERT INTO photo_tags (tag, tag_count)
    SELECT jt.tag, COUNT(*)
    FROM photo_ai p,
         JSON_TABLE(p.tags_json, '$[*]' COLUMNS (tag VARCHAR2(100) PATH '$')) jt
    WHERE jt.tag IS NOT NULL
    GROUP BY jt.tag
"""

DUMP_SQL = "SELECT tag, tag_count FROM photo_tags ORDER BY tag"


def rebuild_tags(conn) -> int:
    """Rebuild photo_tags from photo_ai.tags_json. Returns the resulting tag count."""
    with conn.cursor() as cur:
        cur.execute(REBUILD_SQL_DELETE)
        cur.execute(REBUILD_SQL_INSERT)
        cur.execute("SELECT COUNT(*) FROM photo_tags")
        count = cur.fetchone()[0]
    conn.commit()
    return count


def dump_tags(conn, out) -> None:
    with conn.cursor() as cur:
        cur.execute(DUMP_SQL)
        for tag, tag_count in cur:
            out.write(f"{tag}\t{tag_count}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Rebuild the photo_tags lookup table from photo_ai.tags_json.")
    ap.add_argument("--oracle-dsn", default=os.environ.get("ORACLE_DSN", "localhost/FREEPDB1"))
    ap.add_argument("--oracle-user", default=os.environ.get("ORACLE_USER", "system"))
    ap.add_argument("--oracle-pass", default=os.environ.get("ORACLE_PASS", ""))
    ap.add_argument(
        "--dump", nargs="?", const="-", default=None, metavar="FILE",
        help="Dump tag/count as tab-separated text instead of rebuilding. Writes to stdout, or FILE if given.",
    )
    args = ap.parse_args()

    conn = oracledb.connect(user=args.oracle_user, password=args.oracle_pass, dsn=args.oracle_dsn)
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
