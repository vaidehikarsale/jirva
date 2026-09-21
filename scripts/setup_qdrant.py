"""
JIRVA - Qdrant Collection Setup
----------------------------------
Creates the two Qdrant collections used for the chunk-size comparison:
    jirva_400  - embeddings of the 400-token chunk variant
    jirva_600  - embeddings of the 600-token chunk variant

Both use 384-dimensional vectors (matching BAAI/bge-small-en-v1.5) and
cosine distance.

Safe to rerun: if a collection already exists, it is left untouched and
simply reported - this script never deletes or recreates existing data.

Reads QDRANT_URL and QDRANT_API_KEY from a .env file in the project root
(never hardcode these values).

Usage:
    python setup_qdrant.py
"""

import os
import sys

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

VECTOR_SIZE = 384  # bge-small-en-v1.5 output dimension
COLLECTIONS = ["jirva_400", "jirva_600"]


def main():
    load_dotenv()  # looks for a .env file in the current or parent directories

    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")

    if not url or not api_key:
        print("ERROR: QDRANT_URL and/or QDRANT_API_KEY not found.")
        print("Check that your .env file exists in the project root and contains both values.")
        sys.exit(1)

    print(f"Connecting to Qdrant at {url} ...")
    client = QdrantClient(url=url, api_key=api_key)

    existing = {c.name for c in client.get_collections().collections}
    print(f"Existing collections found: {existing or 'none'}\n")

    for name in COLLECTIONS:
        if name in existing:
            print(f"[SKIP] Collection '{name}' already exists - leaving it untouched.")
            continue

        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        print(f"[CREATED] Collection '{name}' (size={VECTOR_SIZE}, distance=Cosine)")

    print("\n--- Verification ---")
    for name in COLLECTIONS:
        info = client.get_collection(name)
        print(f"{name}: vector_size={info.config.params.vectors.size}, "
              f"distance={info.config.params.vectors.distance}, "
              f"points_count={info.points_count}")


if __name__ == "__main__":
    main()
