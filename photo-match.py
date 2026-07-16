#!/usr/bin/env python3

import argparse
import os
import sys
import sqlite3
import requests

from vector_search import normalize_ollama_host, top_n_by_cosine_distance

def main():
    parser = argparse.ArgumentParser(description="CLI Photo Vector Search")

    # Search parameters
    parser.add_argument("keywords", nargs='+', help="Keywords to perform vector search")
    parser.add_argument("-l", "--limit", type=int, default=100, help="Maximum number of photos to return (default: 100)")
    parser.add_argument("-c", "--show-caption", action="store_true", help="Display the caption alongside the file path")
    parser.add_argument("-d", "--show-distance", action="store_true", help="Display the vector distance score")

    # DB and AI parameters
    parser.add_argument("--db", default=os.environ.get("PHOTO_DB", "photos.db"), help="Path to the SQLite database file.")
    parser.add_argument("--ollama-host", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"), help="Ollama Host URL")
    parser.add_argument("--embed-model", default=os.environ.get("EMBED_MODEL", "mxbai-embed-large"), help="Embedding model name")

    args = parser.parse_args()
    args.ollama_host = normalize_ollama_host(args.ollama_host)

    search_text = " ".join(args.keywords)

    # 1. Generate Embedding via Ollama
    try:
        r = requests.post(
            f"{args.ollama_host}/api/embed",
            json={"model": args.embed_model, "input": search_text}
        )
        r.raise_for_status()
        vector = r.json()["embeddings"][0]
    except Exception as e:
        print(f"Error: Failed to generate embedding from Ollama: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Connect to Database and Search
    conn = None
    try:
        conn = sqlite3.connect(args.db)
        cur = conn.cursor()

        cur.execute("SELECT file_path, caption, embedding FROM photo_ai")
        columns = [c[0] for c in cur.description]
        candidates = [dict(zip(columns, row)) for row in cur.fetchall()]

        ranked = top_n_by_cosine_distance(vector, candidates, "embedding", args.limit)

        for row in ranked:
            output_parts = []

            if args.show_distance:
                output_parts.append(f"[{row['distance']:.4f}]")

            output_parts.append(row["file_path"])

            if args.show_caption:
                caption = (row["caption"] or "").strip()
                output_parts.append(f"- {caption}")

            print("\t".join(output_parts))

    except Exception as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    main()
