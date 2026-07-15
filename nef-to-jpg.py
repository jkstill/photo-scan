#!/usr/bin/env python3
"""Generate companion JPEGs for Nikon NEF files from their embedded preview."""

import argparse
import io
import logging
import os
import sys

from PIL import Image, TiffImagePlugin

SUBIFD_TAG = 330
JPEG_OFFSET_TAG = 513  # JPEGInterchangeFormat
JPEG_LENGTH_TAG = 514  # JPEGInterchangeFormatLength


def setup_logging(verbose: bool) -> logging.Logger:
    logger = logging.getLogger("nef_to_jpg")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


def target_jpg_path(nef_path: str) -> str:
    base, ext = os.path.splitext(nef_path)
    if ext.isupper():
        return base + ".JPG"
    return base + ".jpg"


def find_existing_jpg(nef_path: str) -> str | None:
    base, _ = os.path.splitext(nef_path)
    for candidate in (base + ".jpg", base + ".JPG"):
        if os.path.exists(candidate):
            return candidate
    return None


def largest_embedded_jpeg(nef_path: str) -> tuple[int, int]:
    """Return (offset, length) of the largest embedded JPEG preview in a NEF file."""
    with open(nef_path, "rb") as fp:
        ifh = fp.read(8)
        fp.seek(0)
        with Image.open(fp) as im:
            tags = im.tag_v2
            candidates = []
            if JPEG_OFFSET_TAG in tags and JPEG_LENGTH_TAG in tags:
                candidates.append((tags[JPEG_OFFSET_TAG], tags[JPEG_LENGTH_TAG]))
            for sub_offset in tags.get(SUBIFD_TAG, ()):
                ifd = TiffImagePlugin.ImageFileDirectory_v2(ifh)
                fp.seek(sub_offset)
                try:
                    ifd.load(fp)
                except Exception:
                    continue
                if JPEG_OFFSET_TAG in ifd and JPEG_LENGTH_TAG in ifd:
                    candidates.append((ifd[JPEG_OFFSET_TAG], ifd[JPEG_LENGTH_TAG]))
        if not candidates:
            raise ValueError("no embedded JPEG preview found")
        return max(candidates, key=lambda c: c[1])


def extract_preview_jpeg(nef_path: str) -> bytes:
    offset, length = largest_embedded_jpeg(nef_path)
    with open(nef_path, "rb") as fp:
        fp.seek(offset)
        data = fp.read(length)
    Image.open(io.BytesIO(data)).verify()
    return data


def find_nef_files(root_dir: str):
    for dirpath, _dirnames, filenames in os.walk(root_dir):
        for name in filenames:
            if os.path.splitext(name)[1].lower() == ".nef":
                yield os.path.join(dirpath, name)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate companion JPEGs from Nikon NEF embedded previews.")
    ap.add_argument("root_dir", help="Starting directory to search for NEF files")
    ap.add_argument("-n", "--dry-run", action="store_true", help="Show what would be done without writing files")
    ap.add_argument("--force", action="store_true", help="Regenerate the JPEG even if one already exists")
    ap.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = ap.parse_args()

    logger = setup_logging(args.verbose)

    if not os.path.isdir(args.root_dir):
        logger.error(f"Not a directory: {args.root_dir}")
        return 1

    generated = skipped = regenerated = errors = 0

    for nef_path in find_nef_files(args.root_dir):
        existing = find_existing_jpg(nef_path)

        if existing and os.path.getmtime(nef_path) > os.path.getmtime(existing):
            logger.debug(f"NEF is newer than {existing}")

        if existing and not args.force:
            logger.debug(f"SKIP (exists): {existing}")
            skipped += 1
            continue

        out_path = existing if existing else target_jpg_path(nef_path)
        verb = "REGENERATE" if existing else "GENERATE"

        if args.dry_run:
            logger.info(f"[DRY RUN] {verb}: {out_path} <- {nef_path}")
            if existing:
                regenerated += 1
            else:
                generated += 1
            continue

        try:
            data = extract_preview_jpeg(nef_path)
            with open(out_path, "wb") as out:
                out.write(data)
            logger.info(f"{verb}: {out_path} <- {nef_path}")
            if existing:
                regenerated += 1
            else:
                generated += 1
        except Exception as e:
            logger.error(f"FAILED: {nef_path}: {e}")
            errors += 1

    logger.info(
        f"Done. generated={generated} regenerated={regenerated} skipped={skipped} errors={errors}"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
