#!/usr/bin/env python3

import argparse
import importlib.util
import json
import logging
import os
import re
import sqlite3
import sys

from vector_search import normalize_ollama_host, vector_to_blob

def setup_logging():
    logger = logging.getLogger("db_cleanup")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger

def count_sentences(text: str) -> int:
    if not text:
        return 0
    # Split by ., ?, or ! followed by whitespace or end of string
    parts = re.split(r'[.!?]+(?:\s+|$)', text.strip())
    # Return count of non-empty parts
    return len([p for p in parts if p.strip()])

def main():
    parser = argparse.ArgumentParser(description="Clean up captions and tags in the photo_ai table")
    parser.add_argument("--db", default=os.environ.get("PHOTO_DB", "photos.db"), help="Path to the SQLite database file.")
    parser.add_argument("--ollama-host", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"), help="Ollama Host URL")
    parser.add_argument("--vision-model", default=os.environ.get("VISION_MODEL", "llava:7b"), help="Vision model name")
    parser.add_argument("--embed-model", default=os.environ.get("EMBED_MODEL", "mxbai-embed-large"), help="Embedding model name")
    parser.add_argument("--dims", type=int, default=1024, help="Embedding dimensions")
    args = parser.parse_args()
    args.ollama_host = normalize_ollama_host(args.ollama_host)

    logger = setup_logging()

    # Dynamically load load-photos-walk.py to reuse its exact logic for generating and embedding
    script_dir = os.path.dirname(os.path.abspath(__file__))
    loader_path = os.path.join(script_dir, "load-photos-walk.py")
    if not os.path.exists(loader_path):
        logger.error(f"Cannot find {loader_path}. It is required for generation logic.")
        return 1

    spec = importlib.util.spec_from_file_location("loader", loader_path)
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()

    logger.info("Fetching all photos from the database...")
    cur.execute("SELECT photo_id, file_path, caption, tags_json FROM photo_ai ORDER BY photo_id")
    rows = cur.fetchall()

    updates_made = 0

    for row in rows:
        photo_id = row[0]
        file_path = row[1]
        caption = (row[2] or "").strip()

        tags_raw = row[3]
        try:
            tags = json.loads(tags_raw) if tags_raw else []
        except Exception:
            tags = []

        needs_regen = False
        needs_trunc = False
        reasons = []

        # Rule 1: Caption more than 100 characters
        if len(caption) > 100:
            needs_regen = True
            reasons.append(f"Caption too long ({len(caption)} chars)")

        # Rule 2: Caption more than 1 sentence
        sentence_count = count_sentences(caption)
        if sentence_count > 1:
            needs_regen = True
            reasons.append(f"Multiple sentences ({sentence_count})")

        # Rule 3: No tags
        if not tags or len(tags) == 0:
            needs_regen = True
            reasons.append("No tags found")

        # Rule 4: More than 20 tags
        if tags and len(tags) > 20:
            needs_trunc = True
            if not needs_regen:
                reasons.append(f"Too many tags ({len(tags)}), truncating")

        if not needs_regen and not needs_trunc:
            continue

        logger.info(f"Photo ID {photo_id} ({os.path.basename(file_path)}) flagged: {', '.join(reasons)}")

        new_caption = caption
        new_tags = tags

        # Regenerate if required
        if needs_regen:
            logger.info(f"  -> Regenerating with {args.vision_model}...")
            try:
                # Use the new strict prompt we defined in load-photos-walk.py
                new_caption, new_tags = loader.ollama_generate_caption_tags(
                    ollama_host=args.ollama_host,
                    model=args.vision_model,
                    prompt=loader.DEFAULT_PROMPT,
                    image_path=file_path,
                    retries=2
                )
            except Exception as e:
                logger.error(f"  -> Failed to regenerate for {file_path}: {e}")
                continue

            # If the regenerated caption STILL violates the rules, we might want to forcefully truncate it
            # But the new prompt is much stricter, so we'll trust it and apply basic cleanup
            if len(new_caption) > 100:
                logger.warning(f"  -> Regenerated caption still > 100 chars, truncating strictly.")
                new_caption = new_caption[:97] + "..."
            if count_sentences(new_caption) > 1:
                logger.warning(f"  -> Regenerated caption still > 1 sentence, splitting strictly.")
                new_caption = re.split(r'[.!?]+(?:\s+|$)', new_caption.strip())[0] + "."

        # Truncate tags to 20 maximum (applies to both old tags and newly generated tags)
        if new_tags and len(new_tags) > 20:
            logger.info(f"  -> Truncating tags from {len(new_tags)} to 20")
            new_tags = new_tags[:20]

        # Since data changed, we MUST recompute the embedding
        embed_text = new_caption
        if new_tags:
            embed_text += "\nTags: " + ", ".join(new_tags)

        logger.info(f"  -> Re-embedding with {args.embed_model}...")
        try:
            vec = loader.ollama_embed(
                ollama_host=args.ollama_host,
                embed_model=args.embed_model,
                text=embed_text,
                expected_dims=args.dims,
                retries=2
            )
        except Exception as e:
            logger.error(f"  -> Failed to embed for {file_path}: {e}")
            continue

        # Update the database
        try:
            upd_cur = conn.cursor()
            upd_cur.execute("""
                UPDATE photo_ai
                SET caption = :c, tags_json = :t, embedding = :e
                WHERE photo_id = :id
            """, {
                "c": new_caption,
                "t": json.dumps(new_tags),
                "e": vector_to_blob(vec),
                "id": photo_id
            })
            conn.commit()
            upd_cur.close()
            logger.info(f"  -> Successfully updated DB for Photo ID {photo_id}")
            updates_made += 1
        except Exception as e:
            logger.error(f"  -> Database update failed for {file_path}: {e}")

    cur.close()
    conn.close()
    logger.info(f"Maintenance complete. Updated {updates_made} photos.")

if __name__ == "__main__":
    sys.exit(main())
