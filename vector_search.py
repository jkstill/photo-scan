"""Cosine-distance ranking over embeddings stored as float32 BLOBs in SQLite."""

from array import array

import numpy as np


def blob_to_vector(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def vector_to_blob(vec) -> bytes:
    return array("f", vec).tobytes()


def normalize_ollama_host(host: str) -> str:
    """Ollama's own OLLAMA_HOST env var format omits the scheme (e.g. 'localhost:11434');
    requests needs one, so add http:// if the caller didn't supply http(s)://."""
    if not host.startswith("http://") and not host.startswith("https://"):
        return "http://" + host
    return host


def top_n_by_cosine_distance(query_vec, rows, embedding_key: str, n: int):
    """
    rows: list of dicts, each containing an `embedding_key` entry with the raw BLOB.
    Returns the top-n rows (dicts, unmodified apart from a "distance" key added)
    sorted by ascending cosine distance to query_vec.
    """
    if not rows:
        return []

    query = np.asarray(query_vec, dtype=np.float32)
    query_norm = np.linalg.norm(query)

    matrix = np.stack([blob_to_vector(r[embedding_key]) for r in rows])
    matrix_norms = np.linalg.norm(matrix, axis=1)

    similarity = (matrix @ query) / (matrix_norms * query_norm)
    distance = 1.0 - similarity

    order = np.argsort(distance)[:n]

    results = []
    for i in order:
        row = dict(rows[i])
        row.pop(embedding_key, None)
        row["distance"] = round(float(distance[i]), 4)
        results.append(row)
    return results
