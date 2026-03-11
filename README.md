# Photo AI Scanner & Search App

A comprehensive suite of tools to scan local photo directories, automatically generate AI captions and tags using `llava:7b`, embed them into an Oracle 23ai database using `mxbai-embed-large`, and provide both a modern web UI and a command-line interface for lightning-fast semantic vector searches.

Though the default LLM for captions and tags is `llava:7b`, the system is designed to be modular. You can easily swap in any Ollama-compatible model for vision or embedding tasks by changing the command-line parameters.

I have had better results with `gemma3:12b` than I have had with `llava:7b` for captioning and tagging

While `gemma3:12b` is  slower, it does a better job of tagging. Sometimes `llava:7b` misses obvious tags or generates captions that are too generic. If you have the resources to run `gemma3:12b`, I highly recommend using it for the best results. You can specify the model to use for vision and embedding tasks via command-line parameters when running the photo loading script.

## Prerequisites

- **Python 3.12+**
- **Oracle Database 23ai** (Must support Vector columns and JSON features)
- **Ollama** running locally or remotely with the following models pulled:
  - `llava:7b` (for image vision, captioning, and tagging)
  - `mxbai-embed-large` (for text embeddings)
- **Python Packages:**
  ```bash
  pip install oracledb requests pillow flask
  ```

---

## 1. Database Configuration

Before scanning any photos, you must set up the `photo_ai` table in your Oracle database. The table stores the file paths, JSON tags, EXIF data, and the high-dimensional vectors.

Run the provided DDL script via SQL*Plus or SQLcl:

```sql
sqlplus scott/tiger@server/pdb1.example.com @table-photo-ai.sql
```

*Note: The table includes a highly performant virtual column (`exif_date_original`) that indexes the `DateTimeOriginal` EXIF tag natively for fast date range filtering.*

---

## 2. Scanning and Analyzing Photos

Use `load-photos-walk.py` to recursively scan a directory, extract EXIF data, generate captions/tags via Ollama, and load the vectors into Oracle. 

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
    --oracle-dsn someserver/pdb1.example.com \
    --oracle-user scott \
    --oracle-pass tiger \
    --commit-every 50 \
    --limit 1000
```
*Tip: The script writes logs to `photo_loader_errors.log` by default so you can review any failed analyses.*

---

## 3. Web Interface

The `photo-match-display-server` provides a modern, responsive web UI (Flask) for searching your photo collection.

### Starting the Server
Start the backend server, specifying your database credentials:

The credendtials are for an Oracle database, and ollama is running on the same machine.

It is not necessary for them to be on the same machine, but is is a little easier to set up if they are. If you want to run ollama on a different machine, just specify the `--ollama-host` parameter with the correct URL when running the photo loading script.

```bash
python3 photo-match-display-server \
    --host server \
    --port 1521 \
    --dbname pdb1.example.com \
    --username scott \
    --password tiger \
    --web-port 5000 \
    --limit 20
```

### Using the Web App
1. Open your browser to `http://localhost:5000`.
2. **Vector Search:** Type keywords (e.g., "red car", "dog playing in grass"). The app will query the database based on *semantic meaning*, not just exact word matches.
3. **Exact Tags:** You can additionally filter by exact tags. The tag input includes an autocomplete feature that dynamically pulls all known tags from your database.
4. **Date Filtering:** Select a date range. The database utilizes the virtual `exif_date_original` index for near-instant results.
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
- `-d`, `--show-distance`: Display the Oracle cosine similarity score.

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
./maintain-photos.py \
    --host server \
    --port 1521 \
    --dbname pdb1.example.com \
    --username scott \
    --password tiger
```
