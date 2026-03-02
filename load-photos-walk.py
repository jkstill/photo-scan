#!/usr/bin/env python3

import argparse
import base64
import hashlib
import json
import logging
import os
import re
import sys
from array import array
from typing import Dict, List, Optional, Tuple

import requests
import oracledb
from PIL import Image, ExifTags


FENCE_LINE_RE = re.compile(r"(?m)^\s*```[a-zA-Z]*\s*$")
JSON_OBJ_RE = re.compile(r"(?s)\{.*\}")
WHITESPACE_RE = re.compile(r"\s+")


DEFAULT_PROMPT = (
    'Analyze the image and provide a caption and tags in ONLY two lines.\n'
    'NO markdown. NO code fences. NO column headers.\n'
    'DO NOT use prefixes like "Line 1:", "Caption:", or "Tags:".\n\n'
    'Line 1: A single sentence describing the image.\n'
    'Line 2: 12 to 20 lowercase tags separated by tabs.\n'
)


def setup_logging(log_file: str) -> logging.Logger:
    logger = logging.getLogger("photo_loader")
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_images(root_dir: str) -> str:
    exts = {".jpg", ".jpeg", ".png"}
    for dirpath, _, filenames in os.walk(root_dir):
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in exts:
                yield os.path.join(dirpath, fn)


def parse_llava_response(resp_value) -> Dict:
    """
    Ollama /api/generate returns a string.
    We expect it to be TSV format:
    line 1: caption
    line 2: tag1 \t tag2 \t tag3 ...
    """
    if isinstance(resp_value, dict):
        return resp_value

    if not isinstance(resp_value, str):
        raise ValueError(f"Unexpected Ollama response type: {type(resp_value)}")

    s = resp_value.strip()

    # Strip fenced code blocks, even if indented
    s = FENCE_LINE_RE.sub("", s).strip()

    lines = [line.strip() for line in s.split('\n') if line.strip()]
    
    caption = ""
    tags = []
    
    if len(lines) >= 1:
        caption = lines[0]
        # Remove common prefixes from caption
        caption = re.sub(r'(?i)^(line 1:|caption:)\s*', '', caption).strip()
        # Remove surrounding quotes
        caption = caption.strip('"\'')
    
    if len(lines) >= 2:
        tags_line = lines[1]
        # Remove common prefixes from tags line (can be multiple like 'Line 2: tags:')
        tags_line = re.sub(r'(?i)^(line 2:|tags:)\s*', '', tags_line).strip()
        tags_line = re.sub(r'(?i)^(tags:)\s*', '', tags_line).strip()
        
        # Try splitting by tab first
        tags = [t.strip().strip('"\'') for t in tags_line.split('\t') if t.strip()]
        
        # Fallback if separated by commas instead of tabs
        if len(tags) <= 1 and ',' in tags_line:
             tags = [t.strip().strip('"\'') for t in tags_line.split(',') if t.strip()]

    return {"caption": caption, "tags": tags}


def normalize_caption_tags(obj: Dict) -> Tuple[str, List[str]]:
    caption = obj.get("caption")
    if caption is None and isinstance(obj.get("captions"), list) and obj["captions"]:
        caption = obj["captions"][0]
    if caption is None:
        caption = ""
    caption = str(caption).strip()

    tags_in = obj.get("tags") or []
    tags_out: List[str] = []
    seen = set()

    for t in tags_in:
        tt = str(t).lower().replace("_", " ")
        tt = WHITESPACE_RE.sub(" ", tt).strip()
        if not tt:
            continue
        if tt not in seen:
            seen.add(tt)
            tags_out.append(tt)

    return caption, tags_out


def extract_exif(image_path: str) -> Optional[List[Dict[str, str]]]:
    """Extract EXIF data from the image including sub-IFDs and return as a list of tag/value objects."""
    try:
        with Image.open(image_path) as img:
            exif_obj = img.getexif()
            if not exif_obj:
                return None

            exif_data = []

            def add_tags(ifd, tag_map):
                for k, v in ifd.items():
                    tag_name = tag_map.get(k, k)
                    val = v
                    if isinstance(v, bytes):
                        val = v.decode(errors="replace").strip("\x00")
                    exif_data.append({"tag": str(tag_name), "val": str(val)})

            # Top-level tags
            add_tags(exif_obj, ExifTags.TAGS)

            # Sub-IFDs (Exif, GPSInfo, Interop)
            for ifd_id in [ExifTags.IFD.Exif, ExifTags.IFD.GPSInfo, ExifTags.IFD.Interop]:
                try:
                    sub_ifd = exif_obj.get_ifd(ifd_id)
                    if sub_ifd:
                        tag_map = ExifTags.TAGS
                        if ifd_id == ExifTags.IFD.GPSInfo:
                            tag_map = ExifTags.GPSTAGS
                        add_tags(sub_ifd, tag_map)
                except Exception:
                    pass

            return exif_data if exif_data else None
    except Exception as e:
        logging.getLogger("photo_loader").debug(f"Could not extract EXIF for {image_path}: {e}")
        return None


def ollama_generate_caption_tags(
    ollama_host: str,
    model: str,
    prompt: str,
    image_path: str,
    timeout_sec: int = 240,
    retries: int = 1,
) -> Tuple[str, List[str]]:
    img_b64 = base64.b64encode(open(image_path, "rb").read()).decode("ascii")
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [img_b64],
        "stream": False,
    }

    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(
                f"{ollama_host}/api/generate",
                json=payload,
                timeout=timeout_sec,
            )
            r.raise_for_status()
            data = r.json()
            obj = parse_llava_response(data.get("response"))
            return normalize_caption_tags(obj)
        except Exception as e:
            last_err = e
            if attempt < retries:
                continue

    raise last_err if last_err else RuntimeError("Unknown generate failure")


def ollama_embed(
    ollama_host: str,
    embed_model: str,
    text: str,
    expected_dims: int,
    timeout_sec: int = 60,
    retries: int = 1,
) -> array:
    payload = {"model": embed_model, "input": text}

    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(
                f"{ollama_host}/api/embed",
                json=payload,
                timeout=timeout_sec,
            )
            r.raise_for_status()
            vec = r.json()["embeddings"][0]
            if len(vec) != expected_dims:
                raise ValueError(
                    f"Embedding length {len(vec)} != {expected_dims} for model {embed_model}"
                )
            return array("f", vec)  # float32
        except Exception as e:
            last_err = e
            if attempt < retries:
                continue

    raise last_err if last_err else RuntimeError("Unknown embed failure")


def already_loaded(cur: oracledb.Cursor, sha: str) -> bool:
    cur.execute("select 1 from photo_ai where file_sha256 = :s", {"s": sha})
    return cur.fetchone() is not None


def main() -> int:
    ap = argparse.ArgumentParser(description="Walk photos, caption+tag with LLaVA, embed with mxbai, load into Oracle.")
    ap.add_argument("root_dir", help="Root directory to walk")
    ap.add_argument("--ollama-host", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    ap.add_argument("--vision-model", default=os.environ.get("VISION_MODEL", "llava:7b"))
    ap.add_argument("--embed-model", default=os.environ.get("EMBED_MODEL", "mxbai-embed-large"))
    ap.add_argument("--dims", type=int, default=1024, help="Embedding dimensions. Default 1024 for mxbai-embed-large.")
    ap.add_argument("--oracle-dsn", default=os.environ.get("ORACLE_DSN", "localhost/FREEPDB1"))
    ap.add_argument("--oracle-user", default=os.environ.get("ORACLE_USER", "system"))
    ap.add_argument("--oracle-pass", default=os.environ.get("ORACLE_PASS", ""))
    ap.add_argument("--limit", type=int, default=0, help="Stop after inserting N new photos. 0 means no limit.")
    ap.add_argument("--commit-every", type=int, default=25, help="Commit after N inserts.")
    ap.add_argument("--error-log", default="photo_loader_errors.log", help="Error log file path.")
    ap.add_argument("--prompt-file", default="", help="Optional file containing the prompt for the vision model.")
    ap.add_argument("--generate-retries", type=int, default=1, help="Retries for vision calls.")
    ap.add_argument("--embed-retries", type=int, default=1, help="Retries for embedding calls.")
    args = ap.parse_args()

    root_dir = os.path.abspath(args.root_dir)
    if not os.path.isdir(root_dir):
        print(f"ERROR: not a directory: {root_dir}", file=sys.stderr)
        return 2

    logger = setup_logging(args.error_log)
    logger.info(f"Starting. root_dir={root_dir} ollama={args.ollama_host} vision_model={args.vision_model} embed_model={args.embed_model}")

    prompt = DEFAULT_PROMPT
    if args.prompt_file:
        with open(args.prompt_file, "r", encoding="utf-8") as f:
            prompt = f.read()

    conn = oracledb.connect(user=args.oracle_user, password=args.oracle_pass, dsn=args.oracle_dsn)
    cur = conn.cursor()

    ins_sql = """
    insert into photo_ai (file_path, file_sha256, caption, tags_json, embed_model, embedding, exif_json)
    values (:p, :s, :c, :t, :m, :e, :ex)
    """

    inserted = 0
    seen_files = 0

    try:
        for path in iter_images(root_dir):
            seen_files += 1
            full_path = os.path.abspath(path)

            # print a dot every 10 files to show progress in the terminal
            if seen_files % 10 == 0:
                print(".", end="", flush=True)

            try:
                sha = sha256_file(full_path)
                if already_loaded(cur, sha):
                    continue

                caption, tags = ollama_generate_caption_tags(
                    ollama_host=args.ollama_host,
                    model=args.vision_model,
                    prompt=prompt,
                    image_path=full_path,
                    retries=args.generate_retries,
                )

                embed_text = caption
                if tags:
                    embed_text += "\nTags: " + ", ".join(tags)

                vec = ollama_embed(
                    ollama_host=args.ollama_host,
                    embed_model=args.embed_model,
                    text=embed_text,
                    expected_dims=args.dims,
                    retries=args.embed_retries,
                )

                exif_data = extract_exif(full_path)
                exif_json_str = json.dumps(exif_data) if exif_data else None

                cur.execute(ins_sql, {
                    "p": full_path,
                    "s": sha,
                    "c": caption,
                    "t": json.dumps(tags),
                    "m": args.embed_model,
                    "e": vec,
                    "ex": exif_json_str,
                })

                inserted += 1
                if inserted % args.commit_every == 0:
                    conn.commit()
                    logger.info(f"Committed inserts={inserted} scanned_files={seen_files}")

                if args.limit and inserted >= args.limit:
                    logger.info(f"Limit reached. inserted={inserted} scanned_files={seen_files}")
                    break

            except Exception as e:
                logger.error(f"FILE={full_path} ERROR={repr(e)}")
                continue

        conn.commit()
        logger.info(f"Done. inserted={inserted} scanned_files={seen_files}")

    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

    # print a summary line at the end, include a leading newline to separate from the dots printed during processing
    print(f"\nFinished. Inserted {inserted} new photos. Scanned {seen_files} files.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

