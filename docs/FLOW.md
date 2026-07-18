# Photo AI Scanner — End-to-End Flow

## System Overview

```mermaid
graph TD
    subgraph Ingest["1. Ingest (load-photos-walk.py)"]
        A[Photo directory] --> B[load-photos-walk.py]
        B --> C[(Oracle 23ai\nphoto_ai)]
    end

    subgraph Maintain["2. Maintain (maintain-photos.py)"]
        C --> D[maintain-photos.py]
        D -->|re-generate / re-embed| C
    end

    subgraph Search["3. Search"]
        E[Browser] --> F[photo-match-display-server\nFlask]
        G[Terminal] --> H[photo-match.py]
        F --> C
        H --> C
    end

    subgraph AI["Ollama Models"]
        O1[Vision model\nllava:7b / gemma3:12b]
        O2[Embed model\nmxbai-embed-large]
    end

    B --> O1
    B --> O2
    D --> O1
    D --> O2
    F --> O2
    H --> O2
```

---

## Prerequisites

| Component | Requirement |
|---|---|
| Python | 3.12+ |
| Oracle DB | 23ai with Vector and JSON support |
| Ollama | Running locally or remotely |
| Ollama models | `llava:7b` (or `gemma3:12b`) + `mxbai-embed-large` |
| Python packages | `oracledb`, `requests`, `pillow`, `flask` |

---

## Step 0 — Database Setup

Run the DDL once before any photos are loaded.

```sql
sqlplus scott/tiger@server/pdb1.example.com @table-photo-ai.sql
```

```mermaid
erDiagram
    PHOTO_AI {
        number photo_id PK "identity, auto"
        varchar2 file_path "full disk path"
        varchar2 file_sha256 UK "dedup key"
        clob caption "AI-generated sentence"
        json tags_json "array of lowercase tags"
        varchar2 embed_model "model name used"
        vector embedding "1024-dim float32"
        timestamp created_ts "auto"
        json exif_json "array of tag/val objects"
        timestamp exif_date_original "virtual, indexed"
    }
```

`exif_date_original` is a **virtual column** derived from `exif_json` — it extracts the `DateTimeOriginal` EXIF field and converts it to a `TIMESTAMP`. A B-tree index on this column makes date-range queries instant.

---

## Step 1 — Photo Ingestion (`load-photos-walk.py`)

```mermaid
flowchart TD
    Start([Start]) --> WalkDir["Walk root directory\nos.walk() — .jpg .jpeg .png"]
    WalkDir --> NextFile{Next file?}
    NextFile -- No --> Commit["Final commit"] --> Done([Done])
    NextFile -- Yes --> Hash["SHA-256 hash file"]
    Hash --> AlreadyLoaded{"Already in DB?\nSELECT by sha256"}
    AlreadyLoaded -- Yes --> NextFile
    AlreadyLoaded -- No --> Vision["Ollama /api/generate\nvision model → caption + tags"]
    Vision --> ParseLLM["parse_llava_response()\nLine 1 = caption\nLine 2 = tab-delimited tags"]
    ParseLLM --> NormalizeTags["normalize_tags()\nStrip prefixes, dedupe,\nlowercase, handle JSON/CSV/TSV"]
    NormalizeTags --> EmbedText["Build embed text:\ncaption + newline + Tags: tag1, tag2 ..."]
    EmbedText --> Embed["Ollama /api/embed\nmxbai-embed-large → 1024-dim vector"]
    Embed --> EXIF["extract_exif()\nPillow — top-level + GPS + Interop IFDs"]
    EXIF --> Insert["INSERT into photo_ai\n(path, sha256, caption, tags_json,\n embed_model, embedding, exif_json)"]
    Insert --> CommitCheck{"inserted % commit_every == 0?"}
    CommitCheck -- Yes --> CommitMid["conn.commit()"] --> NextFile
    CommitCheck -- No --> NextFile
```

### Key behaviors

- **Dedup**: SHA-256 hash prevents reprocessing the same file, even if renamed or moved.
- **Retries**: Both vision and embed calls retry `--generate-retries` / `--embed-retries` times before logging and skipping.
- **Progress**: A dot is printed to the terminal every 10 files; errors go to `photo_loader_errors.log`.
- **Batch commits**: `--commit-every` (default 25) controls how often Oracle commits; the final commit runs unconditionally.

### Prompt sent to the vision model

```
Analyze the image and provide a caption and tags in ONLY two lines.
NO markdown. NO code fences. NO column headers.
DO NOT use prefixes like "Line 1:", "Caption:", or "Tags:".

Line 1: A single sentence describing the image.
Line 2: 12 to 20 lowercase tags separated by tabs.
```

---

## Step 2 — Maintenance (`maintain-photos.py`)

Run periodically to clean up rows where the LLM ignored the prompt rules.

```mermaid
flowchart TD
    Start([Start]) --> Fetch["SELECT all rows\nphoto_id, file_path, caption, tags_json"]
    Fetch --> NextRow{Next row?}
    NextRow -- No --> Done([Done])
    NextRow -- Yes --> Check["Evaluate rules"]

    Check --> R1{"Caption > 100 chars?"}
    Check --> R2{"Caption > 1 sentence?"}
    Check --> R3{"No tags at all?"}
    Check --> R4{"Tags > 20?"}

    R1 -- Yes --> FlagRegen[needs_regen = True]
    R2 -- Yes --> FlagRegen
    R3 -- Yes --> FlagRegen
    R4 -- Yes --> FlagTrunc[needs_trunc = True]

    FlagRegen --> Regen["ollama_generate_caption_tags()\nRe-call vision model"]
    Regen --> PostCheck{"Still violates\nrules?"}
    PostCheck -- caption too long --> Truncate97["Truncate to 97 chars + '...'"]
    PostCheck -- multi-sentence --> SplitFirst["Keep first sentence only"]
    PostCheck -- OK --> Trunc20

    FlagTrunc --> Trunc20["Truncate tags list to 20"]
    Trunc20 --> ReEmbed["ollama_embed()\nRe-compute 1024-dim vector"]
    ReEmbed --> UpdateDB["UPDATE photo_ai\nSET caption, tags_json, embedding\nWHERE photo_id = :id\nCOMMIT"]
    UpdateDB --> NextRow

    R1 & R2 & R3 & R4 -- All No --> NextRow
```

`maintain-photos.py` dynamically imports `load-photos-walk.py` to reuse `ollama_generate_caption_tags`, `ollama_embed`, and `DEFAULT_PROMPT` exactly — no duplication.

---

## Step 3a — Web Search (`photo-match-display-server`)

```mermaid
sequenceDiagram
    participant Browser
    participant Flask as Flask server
    participant Ollama
    participant Oracle as Oracle 23ai

    Browser->>Flask: GET /
    Flask-->>Browser: index.html

    Browser->>Flask: GET /api/tags
    Flask->>Oracle: SELECT DISTINCT tags via JSON_TABLE
    Oracle-->>Flask: tag list
    Flask-->>Browser: JSON tag array (autocomplete)

    Note over Browser: User types keywords,<br/>selects filter tags,<br/>picks date range

    Browser->>Flask: POST /api/search {keywords, filter_tags, dates, limit}
    Flask->>Ollama: POST /api/embed {input: "keyword1 keyword2"}
    Ollama-->>Flask: 1024-dim float32 vector

    Flask->>Oracle: SELECT ... FROM photo_ai<br/>WHERE [tag filters] AND [date filters]<br/>ORDER BY VECTOR_DISTANCE(embedding, :vec, COSINE)<br/>FETCH FIRST :n ROWS ONLY
    Oracle-->>Flask: rows (photo_id, file_path, caption, tags, exif, date, dist)
    Flask-->>Browser: JSON results array

    Browser->>Flask: GET /image?path=/disk/path/photo.jpg
    Flask-->>Browser: image bytes (send_file)
```

### Search filters (combinable)

| Filter | Mechanism |
|---|---|
| Vector keywords | `VECTOR_DISTANCE(embedding, :vec, COSINE)` ORDER BY |
| Required tags | `JSON_EXISTS(tags_json, '$?(@ == $T)' PASSING :tag AS "T")` per tag |
| Date range | `exif_date_original BETWEEN :start AND :end` (uses virtual-column index) |
| Include undated | Toggle adds `OR exif_date_original IS NULL` |

### Web UI features

- **Autocomplete**: Tag input queries `/api/tags` on load; filters suggestions as you type.
- **Zoom modal**: Click any photo thumbnail to open a full-screen overlay.
- **EXIF modal**: "View EXIF Data" button renders all stored EXIF fields in a table.
- **File path toggle**: "Show file paths" reveals the absolute disk path on every card.
- **Sidebar toggle**: Collapsible sidebar for full-screen photo browsing on mobile.

---

## Step 3b — CLI Search (`photo-match.py`)

```mermaid
flowchart LR
    CLI["photo-match.py\n'mountains landscape' -l 5 -c -d"]
    Ollama["Ollama /api/embed\nmxbai-embed-large"]
    Oracle["Oracle 23ai\nVECTOR_DISTANCE COSINE"]
    Output["stdout\n[dist] file_path - caption"]

    CLI --> Ollama --> Oracle --> Output
```

```bash
./photo-match.py "mountains landscape" -l 5 -c -d
```

```
[0.1245]  /mnt/photos/vacation/IMG_01.jpg  - A snowy mountain peak against a blue sky.
[0.1582]  /mnt/photos/vacation/IMG_05.jpg  - A lush green valley surrounded by tall mountains.
```

Flags: `-l` limit · `-c` show caption · `-d` show cosine distance score

---

## Data Flow Summary

```mermaid
flowchart LR
    Photo["JPEG/PNG\non disk"]

    subgraph Ingest
        SHA["SHA-256\nhash"]
        Vision["Vision LLM\ncaption + tags"]
        Embed["Embed LLM\n1024-dim vector"]
        EXIF["Pillow\nEXIF extraction"]
    end

    subgraph Oracle["Oracle 23ai — photo_ai"]
        Row["file_path\nsha256\ncaption CLOB\ntags_json JSON\nembedding VECTOR(1024)\nexif_json JSON\nexif_date_original VIRTUAL"]
    end

    subgraph Search
        Vec["VECTOR_DISTANCE\nCOSINE ORDER BY"]
        TagF["JSON_EXISTS\nexact tag filter"]
        DateF["Virtual column\nindex range scan"]
    end

    Photo --> SHA --> Vision --> Embed --> Row
    Photo --> EXIF --> Row
    Row --> Vec & TagF & DateF
    Vec & TagF & DateF --> Results["Ranked\nresults"]
```
