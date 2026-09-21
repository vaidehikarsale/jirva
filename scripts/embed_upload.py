"""
JIRVA - Embed and Upload Chunks to Qdrant
---------------------------------------------
Reads chunk JSON files from a chunk variant folder (e.g. data/chunks/400_variant),
embeds each chunk's content using BAAI/bge-small-en-v1.5 (run locally, free,
no API calls), and upserts each as a point into the matching Qdrant collection.

Rerun-safe: each chunk's Qdrant point ID is a deterministic UUID5 derived from
its chunk_id, so re-running this script overwrites the same points instead of
creating duplicates.

Usage:
    python embed_upload.py --chunks-dir <path> --collection <name> --log <log_csv>

Example:
    python embed_upload.py --chunks-dir ../data/chunks/400_variant --collection jirva_400 --log ../logs/embedding_log.csv
    python embed_upload.py --chunks-dir ../data/chunks/600_variant --collection jirva_600 --log ../logs/embedding_log.csv
"""

import argparse
import csv
import json
import os
import sys
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-small-en-v1.5"
BATCH_SIZE = 16
NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")  # fixed namespace for deterministic UUID5s


def log_row(log_path, chunk_id, category, collection, status, reason):
    file_exists = os.path.isfile(log_path)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "chunk_id", "category", "collection", "status", "reason"])
        writer.writerow([
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            chunk_id, category, collection, status, reason
        ])


def load_chunks(chunks_dir):
    """Walk <chunks_dir>/<category>/*.json and yield chunk dicts."""
    for category in sorted(os.listdir(chunks_dir)):
        category_path = os.path.join(chunks_dir, category)
        if not os.path.isdir(category_path):
            continue
        for fname in sorted(os.listdir(category_path)):
            if fname.endswith(".json"):
                with open(os.path.join(category_path, fname), "r", encoding="utf-8") as f:
                    try:
                        yield json.load(f)
                    except json.JSONDecodeError:
                        continue


def chunk_point_id(chunk_id):
    return str(uuid.uuid5(NAMESPACE, chunk_id))


def run(chunks_dir, collection, log_path):
    load_dotenv()
    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")
    if not url or not api_key:
        print("ERROR: QDRANT_URL/QDRANT_API_KEY not found in .env")
        sys.exit(1)

    print(f"Loading embedding model: {MODEL_NAME} (first run downloads it locally, then it's cached)")
    model = SentenceTransformer(MODEL_NAME)

    print(f"Connecting to Qdrant collection '{collection}' ...")
    client = QdrantClient(url=url, api_key=api_key)

    chunks = list(load_chunks(chunks_dir))
    print(f"Loaded {len(chunks)} chunks from {chunks_dir}\n")

    success, failed = 0, 0
    batch = []

    def flush_batch():
        nonlocal success, failed
        if not batch:
            return
        texts = [c["content"] for c in batch]
        try:
            vectors = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
        except Exception as e:
            for c in batch:
                print(f"  [FAILED] {c.get('chunk_id')}: embedding error: {e}")
                log_row(log_path, c.get("chunk_id"), c.get("category"), collection, "failed", f"embedding error: {e}")
                failed += 1
            batch.clear()
            return

        points = []
        for c, vector in zip(batch, vectors):
            point_id = chunk_point_id(c["chunk_id"])
            points.append(PointStruct(
                id=point_id,
                vector=vector.tolist(),
                payload={
                    "chunk_id": c["chunk_id"],
                    "document_id": c["document_id"],
                    "document_title": c["document_title"],
                    "source_url": c["source_url"],
                    "category": c["category"],
                    "source_type": c.get("source_type", "Atlassian Official Documentation"),
                    "chunk_index": c["chunk_index"],
                    "chunk_count_in_doc": c.get("chunk_count_in_doc"),
                    "content": c["content"],
                },
            ))

        try:
            client.upsert(collection_name=collection, points=points)
            for c in batch:
                print(f"  [SUCCESS] {c['chunk_id']} embedded and upserted")
                log_row(log_path, c["chunk_id"], c["category"], collection, "success", "upserted")
                success += 1
        except Exception as e:
            for c in batch:
                print(f"  [FAILED] {c.get('chunk_id')}: upsert error: {e}")
                log_row(log_path, c.get("chunk_id"), c.get("category"), collection, "failed", f"upsert error: {e}")
                failed += 1

        batch.clear()

    for chunk in chunks:
        batch.append(chunk)
        if len(batch) >= BATCH_SIZE:
            flush_batch()
    flush_batch()  # remaining partial batch

    print("\n--- Embedding + upload summary ---")
    print(f"Collection:     {collection}")
    print(f"Total chunks:   {len(chunks)}")
    print(f"Success:        {success}")
    print(f"Failed:         {failed}")
    print(f"Log written to: {log_path}")

    count = client.get_collection(collection).points_count
    print(f"Qdrant now reports {count} points in '{collection}'")


def main():
    parser = argparse.ArgumentParser(description="Embed JIRVA chunks and upload them to Qdrant")
    parser.add_argument("--chunks-dir", required=True, help="Path to a chunk variant folder, e.g. data/chunks/400_variant")
    parser.add_argument("--collection", required=True, help="Qdrant collection name, e.g. jirva_400")
    parser.add_argument("--log", required=True, help="Path to the embedding log CSV")
    args = parser.parse_args()

    if not os.path.isdir(args.chunks_dir):
        print(f"ERROR: chunks directory not found: {args.chunks_dir}")
        sys.exit(1)

    run(args.chunks_dir, args.collection, args.log)


if __name__ == "__main__":
    main()
