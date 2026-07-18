#!/usr/bin/env python3
"""
One-time cleanup for tags the vision model jammed together instead of
splitting: joined with a literal backslash instead of a tab, or dumped as
one long space-separated JSON string element instead of one element per tag
(see the normalize_tags() fixes in load-photos-walk.py). Re-splits affected
tags_json entries in place using the same splitting logic, without calling
Ollama again.
"""

import argparse
import importlib.util
import json
import os
import sqlite3
import sys


def load_sibling(script_dir: str, filename: str, module_name: str):
    path = os.path.join(script_dir, filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=os.environ.get("PHOTO_DB", "photos.db"), help="Path to the SQLite database file.")
    ap.add_argument("--dry-run", action="store_true", help="Report what would change without writing.")
    args = ap.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    loader = load_sibling(script_dir, "load-photos-walk.py", "loader")

    def needs_split(t) -> bool:
        if not isinstance(t, str):
            return False
        return "\\" in t or len(t.split(' ')) > 3

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()

    cur.execute("SELECT photo_id, tags_json FROM photo_ai")
    rows = cur.fetchall()

    fixed = 0
    for photo_id, tags_json in rows:
        try:
            tags = json.loads(tags_json) if tags_json else []
        except Exception:
            continue

        if not any(needs_split(t) for t in tags):
            continue

        new_tags = []
        seen = set()
        for t in tags:
            if needs_split(t):
                pieces = loader.normalize_tags(t, lowercase=True)
            else:
                pieces = [t] if isinstance(t, str) else []
            for p in pieces:
                if p not in seen:
                    seen.add(p)
                    new_tags.append(p)

        if new_tags == tags:
            continue

        fixed += 1
        if args.dry_run:
            print(f"photo_id={photo_id}: {tags} -> {new_tags}")
        else:
            cur.execute("UPDATE photo_ai SET tags_json = ? WHERE photo_id = ?", (json.dumps(new_tags), photo_id))

    if args.dry_run:
        print(f"Would fix {fixed} rows (of {len(rows)} candidates).")
        conn.close()
        return 0

    conn.commit()
    print(f"Fixed {fixed} rows.")

    if fixed:
        rebuilder = load_sibling(script_dir, "rebuild-tags.py", "rebuilder")
        count = rebuilder.rebuild_tags(conn)
        print(f"Rebuilt photo_tags: {count} tags.")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
