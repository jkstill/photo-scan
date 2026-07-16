# Photo AI Scanner & Search App

A comprehensive suite of tools to scan local photo directories, automatically generate AI captions and tags using `llava:7b`, embed them into a local SQLite database using `mxbai-embed-large`, and provide both a modern web UI and a command-line interface for semantic vector searches.

Though the default LLM for captions and tags is `llava:7b`, the system is designed to be modular. You can easily swap in any Ollama-compatible model for vision or embedding tasks by changing the command-line parameters.

I have had better results with `gemma3:12b` than I have had with `llava:7b` for captioning and tagging

While `gemma3:12b` is  slower, it does a better job of tagging. Sometimes `llava:7b` misses obvious tags or generates captions that are too generic. If you have the resources to run `gemma3:12b`, I highly recommend using it for the best results. You can specify the model to use for vision and embedding tasks via command-line parameters when running the photo loading script.

## Prerequisites

- **Python 3.12+** (SQLite support is built into the standard library)
- **Ollama** running locally or remotely with the following models pulled:
  - `llava:7b` (for image vision, captioning, and tagging)
  - `mxbai-embed-large` (for text embeddings)
- **Python Packages:**
  ```bash
  pip install requests pillow flask numpy
  ```

---

## 1. Database Configuration

Before scanning any photos, you must create the SQLite database file and its tables. There's no server to install or credentials to manage — it's a single local file.

```bash
sqlite3 photos.db < table-photo-ai-sqlite.sql
sqlite3 photos.db < table-photo-tags-sqlite.sql
```

*Note: `exif_date_original` is computed once at load time (from the `DateTimeOriginal` EXIF tag) and stored as an indexed column for fast date range filtering, rather than recomputed on every query.*

Every script that touches the database accepts `--db path/to/photos.db` (defaults to `photos.db` in the current directory, or the `PHOTO_DB` environment variable).

---

## 2. Scanning and Analyzing Photos

Use `load-photos-walk.py` to recursively scan a directory, extract EXIF data, generate captions/tags via Ollama, and load the vectors into SQLite.

### Basic Usage
```bash
./load-photos-walk.py /mnt/photos/vacation/
```

### Advanced Usage & Options
The script is robust and prevents duplicate processing by hashing files (`sha256`).

llava:7b is the default vision model, and mxbai-embed-large is the default embedding model, but you can specify any Ollama-compatible model for either task.

```bash
./load-photos-walk.py /mnt/photos/vacation/ \
    --ollama-host http://localhost:11434 \
    --vision-model gemma3:12b \
    --embed-model mxbai-embed-large \
    --db photos.db \
    --commit-every 50 \
    --limit 1000
```

*The `photo_tags` lookup table (used by the web UI's tag dropdown) is automatically rebuilt after a run that inserts new photos. Rebuild it manually with `./rebuild-tags.py --db photos.db`, or dump it to text with `--dump`.*
*Tip: The script writes logs to `photo_loader_errors.log` by default so you can review any failed analyses.*

---

## 3. Web Interface

The `photo-match-display-server` provides a modern, responsive web UI (Flask) for searching your photo collection.

### Starting the Server
Start the backend server, pointing it at your database file:

Ollama does not need to run on the same machine as the app — specify the `--ollama-host` parameter with the correct URL if it's remote.

```bash
python3 photo-match-display-server \
    --db photos.db \
    --ollama-host http://localhost:11434 \
    --web-port 5000 \
    --limit 20
```

### Using the Web App
1. Open your browser to `http://localhost:5000`.
2. **Vector Search:** Type keywords (e.g., "red car", "dog playing in grass"). The app will query the database based on *semantic meaning*, not just exact word matches.
3. **Exact Tags:** You can additionally filter by exact tags. The tag input includes an autocomplete feature that dynamically pulls all known tags from your database.
4. **Date Filtering:** Select a date range. The indexed `exif_date_original` column keeps this fast.
5. **Interactive UI:** 
   - Click any photo to open a **high-res zoom modal**.
   - Click **"View EXIF Data"** to see detailed camera metrics in a tabular modal.
   - Toggle **"Show file paths"** to instantly reveal the absolute disk path for every photo.

---

## 4. Command Line Search

If you just need to find a file path quickly without spinning up the UI, use `photo-match.py`.

### Basic Search
Returns up to 100 file paths matching your semantic query:
```bash
./photo-match.py red car
```

### Advanced Options
- `-l`, `--limit`: Change the max number of results (default: 100).
- `-c`, `--show-caption`: Display the AI-generated caption next to the file path.
- `-d`, `--show-distance`: Display the cosine similarity score.
- `--db`: Path to the SQLite database file (default: `photos.db`).

**Example:** Show top 5 matches with captions and scores.
```bash
./photo-match.py "mountains landscape" -l 5 -c -d
```
*Output Example:*
```text
[0.1245]	/mnt/photos/vacation/IMG_01.jpg	- A snowy mountain peak against a blue sky.
[0.1582]	/mnt/photos/vacation/IMG_05.jpg	- A lush green valley surrounded by tall mountains.
```

---

## 5. Maintenance and Cleanup

Because LLMs can occasionally hallucinate or ignore formatting rules, `maintain-photos.py` is included to sanitize existing data without requiring a full rescan.

The maintenance script enforces the following rules:
1. Captions must be **1 sentence**.
2. Captions must be **<= 100 characters**.
3. Photos must have at least 1 tag.
4. Photos are limited to a maximum of 20 tags.

If a photo violates a rule, the script will automatically invoke Ollama to regenerate the caption/tags or truncate the tags array, recalculate the vector embedding, and update the database row.

### Running Maintenance
```bash
./maintain-photos.py --db photos.db
```

---

## 6. RAW (NEF) to JPEG Conversion

Web browsers can't display Nikon RAW (`.NEF`) files, and `load-photos-walk.py` needs a JPEG companion to caption, tag, and embed each photo. `nef-to-jpg.py` generates that companion by extracting the full-resolution JPEG preview that's already embedded in every NEF file — no RAW decoding library (e.g. `rawpy`) or external tool (e.g. `exiftool`) required, just `Pillow`.

For each `.NEF` file found, it looks at the embedded preview images stored in the file's `SubIFDs` and pulls out the largest one, writing those JPEG bytes to disk unchanged (no re-encoding, no quality loss).

### Behavior
- **`DSC_1234.jpg` already exists:** Left alone and reused as the companion image.
- **`DSC_1234.jpg` does not exist:** Generated from the embedded NEF preview.
- **`DSC_1234.NEF` is newer than `DSC_1234.jpg`:** Noted in verbose output, but the JPEG is still left alone unless `--force` is given.
- The generated JPEG's extension matches the case of the NEF's extension (`.NEF` → `.JPG`, `.nef` → `.jpg`). An existing JPEG of either case is honored, so files aren't duplicated.

### Basic Usage
```bash
./nef-to-jpg.py /mnt/photos/vacation/
```

### Options
- `-n`, `--dry-run`: Show what would be generated/regenerated without writing any files.
- `--force`: Regenerate the JPEG from the NEF preview even if one already exists.
- `-v`, `--verbose`: Enable debug-level logging (per-file skip/timestamp notes).

**Example:** Preview what a full rebuild would do before committing to it.
```bash
./nef-to-jpg.py --dry-run --force /mnt/photos/vacation/
```
*Output Example:*
```text
2026-07-15 16:12:32 [INFO] GENERATE: /mnt/photos/vacation/DSC_1514.JPG <- /mnt/photos/vacation/DSC_1514.NEF
2026-07-15 16:12:32 [INFO] Done. generated=1 regenerated=0 skipped=0 errors=0
```
