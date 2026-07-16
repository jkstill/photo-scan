#!/usr/bin/env python3
"""
Checks this app's runtime requirements (Python version, pip packages,
SQLite features, required project files, Ollama models) and writes a
pass/fail report to a file. Run it on the dev machine to see the
baseline, or on a new install to see what's missing.

Exit code: 0 if everything passed, 1 if anything failed.
"""

import argparse
import importlib.metadata
import importlib.util
import os
import shutil
import sqlite3
import sys

import requests

from vector_search import normalize_ollama_host

# (import name, pip distribution name) - they differ for Pillow
REQUIRED_PACKAGES = [
    ("requests", "requests"),
    ("PIL", "pillow"),
    ("flask", "flask"),
    ("numpy", "numpy"),
]
REQUIRED_FILES = [
    "table-photo-ai-sqlite.sql",
    "table-photo-tags-sqlite.sql",
    "vector_search.py",
    "load-photos-walk.py",
    "photo-match-display-server",
    "photo-match.py",
    "maintain-photos.py",
    "rebuild-tags.py",
    "templates/index.html",
]
MIN_PYTHON = (3, 12)


def check_python_version():
    ok = sys.version_info >= MIN_PYTHON
    have = ".".join(map(str, sys.version_info[:3]))
    need = ".".join(map(str, MIN_PYTHON))
    return ok, f"Python {have} (need >= {need})"


def check_package(import_name, dist_name):
    spec = importlib.util.find_spec(import_name)
    if spec is None:
        return False, f"package '{dist_name}' not installed"
    try:
        version = importlib.metadata.version(dist_name)
    except importlib.metadata.PackageNotFoundError:
        version = "unknown version"
    return True, f"package '{dist_name}' ({version})"


def check_sqlite_json1():
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("SELECT json_each.value FROM json_each('[1]')").fetchall()
        conn.close()
        return True, "sqlite3 JSON1 extension (json_each) available"
    except Exception as e:
        return False, f"sqlite3 JSON1 extension unavailable: {e}"


def check_sqlite_cli():
    path = shutil.which("sqlite3")
    if path:
        return True, f"sqlite3 CLI found ({path})"
    return False, "sqlite3 CLI not found on PATH (needed to create the DB from the .sql files)"


def check_file(path, script_dir):
    full = os.path.join(script_dir, path)
    if os.path.exists(full):
        return True, f"file '{path}' present"
    return False, f"file '{path}' missing"


def check_ollama(ollama_host, models):
    ollama_host = normalize_ollama_host(ollama_host)
    try:
        r = requests.get(f"{ollama_host}/api/tags", timeout=5)
        r.raise_for_status()
        installed = {m["name"] for m in r.json().get("models", [])}
    except Exception as e:
        return [(False, f"Ollama unreachable at {ollama_host}: {e}")]

    results = [(True, f"Ollama reachable at {ollama_host}")]
    for model in models:
        # Ollama tags include a version suffix (e.g. "mxbai-embed-large:latest")
        found = any(m == model or m.startswith(model + ":") for m in installed)
        if found:
            results.append((True, f"model '{model}' pulled"))
        else:
            results.append((False, f"model '{model}' not found on {ollama_host}"))
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ollama-host", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    ap.add_argument("--vision-model", default=os.environ.get("VISION_MODEL", "llava:7b"))
    ap.add_argument("--embed-model", default=os.environ.get("EMBED_MODEL", "mxbai-embed-large"))
    ap.add_argument("--out", default="requirements-report.txt", help="Report output file")
    ap.add_argument("--skip-ollama", action="store_true", help="Skip Ollama reachability/model checks")
    args = ap.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))

    results = []
    results.append(check_python_version())
    for import_name, dist_name in REQUIRED_PACKAGES:
        results.append(check_package(import_name, dist_name))
    results.append(check_sqlite_json1())
    results.append(check_sqlite_cli())
    for f in REQUIRED_FILES:
        results.append(check_file(f, script_dir))
    if not args.skip_ollama:
        results.extend(check_ollama(args.ollama_host, [args.vision_model, args.embed_model]))

    lines = []
    failed = 0
    for ok, msg in results:
        status = "OK  " if ok else "FAIL"
        if not ok:
            failed += 1
        lines.append(f"[{status}] {msg}")

    summary = f"\n{len(results) - failed}/{len(results)} checks passed."
    lines.append(summary)

    report = "\n".join(lines)
    print(report)

    with open(args.out, "w") as f:
        f.write(report + "\n")
    print(f"\nReport written to {args.out}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
