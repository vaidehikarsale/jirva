"""
JIRVA - Query Search Tool
-----------------------------
Embeds a query using the BGE-recommended query instruction prefix, then
searches BOTH Qdrant collections (jirva_400 and jirva_600) and prints the
top results side by side, so you can directly compare which chunk-size
variant retrieves better for a given query.

Usage:
    python query_search.py "Why can't I move my issue to Done?"
    python query_search.py "Why can't I move my issue to Done?" --top-k 3
"""

import argparse
import os

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
COLLECTIONS = ["jirva_400", "jirva_600"]


def print_results(collection_name, results):
    print(f"\n--- {collection_name} ---")
    if not results:
        print("  (no results)")
        return
    for rank, r in enumerate(results, start=1):
        payload = r.payload
        snippet = payload["content"][:220].replace("\n", " ")
        print(f"  #{rank} | score={r.score:.4f} | {payload['document_title']} [{payload['category']}]")
        print(f"      chunk_id: {payload['chunk_id']}")
        print(f"      url: {payload['source_url']}")
        print(f"      snippet: {snippet}...")


def main():
    parser = argparse.ArgumentParser(description="Search JIRVA's Qdrant collections with a test query")
    parser.add_argument("query", help="The query text to search for")
    parser.add_argument("--top-k", type=int, default=3, help="Number of results to show per collection (default 3)")
    args = parser.parse_args()

    load_dotenv()
    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")

    print(f"Loading embedding model: {MODEL_NAME} ...")
    model = SentenceTransformer(MODEL_NAME)
    client = QdrantClient(url=url, api_key=api_key)

    query_text = QUERY_PREFIX + args.query
    query_vector = model.encode(query_text, normalize_embeddings=True).tolist()

    print(f"\nQuery: \"{args.query}\"")

    for collection in COLLECTIONS:
        response = client.query_points(
            collection_name=collection,
            query=query_vector,
            limit=args.top_k,
            with_payload=True,
        )
        print_results(collection, response.points)


if __name__ == "__main__":
    main()
