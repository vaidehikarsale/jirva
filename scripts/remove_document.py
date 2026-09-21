"""
JIRVA - Remove Document
---------------------------
Cleanly removes a document by its document_id from every stage of the
pipeline: data/documents, both chunk variants, and both Qdrant collections.

Useful any time a source is found to be out of scope, low quality, or
wrong-platform after it's already been processed (as opposed to catching
it before collection).

Usage:
    python remove_document.py --document-id iss_001
"""

import argparse
import glob
import os

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, PayloadSchemaType

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOCUMENTS_DIR = os.path.join(PROJECT_ROOT, "data", "documents")
CHUNK_VARIANTS = ["400_variant", "600_variant"]
COLLECTIONS = ["jirva_400", "jirva_600"]


def ensure_document_id_index(client, collection):
    """Qdrant requires a payload index to filter-delete by a field. Safe to call
    repeatedly - if the index already exists, Qdrant just leaves it as is."""
    try:
        client.create_payload_index(
            collection_name=collection,
            field_name="document_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )
    except Exception:
        pass  # index already exists - nothing to do


def remove_document_file(doc_id):
    pattern = os.path.join(DOCUMENTS_DIR, "*", f"{doc_id}.json")
    matches = glob.glob(pattern)
    for path in matches:
        os.remove(path)
        print(f"  [REMOVED] {path}")
    if not matches:
        print(f"  [INFO] No document file found for {doc_id}")
    return len(matches)


def remove_chunk_files(doc_id):
    total = 0
    for variant in CHUNK_VARIANTS:
        pattern = os.path.join(PROJECT_ROOT, "data", "chunks", variant, "*", f"{doc_id}_c*.json")
        matches = glob.glob(pattern)
        for path in matches:
            os.remove(path)
            print(f"  [REMOVED] {path}")
        total += len(matches)
    if total == 0:
        print(f"  [INFO] No chunk files found for {doc_id}")
    return total


def remove_qdrant_points(doc_id):
    load_dotenv()
    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")
    client = QdrantClient(url=url, api_key=api_key)

    for collection in COLLECTIONS:
        ensure_document_id_index(client, collection)
        result = client.delete(
            collection_name=collection,
            points_selector=Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=doc_id))]
            ),
        )
        print(f"  [QDRANT] Deleted points for {doc_id} from '{collection}': {result.status}")


def main():
    parser = argparse.ArgumentParser(description="Remove a document from all JIRVA pipeline stages")
    parser.add_argument("--document-id", required=True, help="Document ID to remove, e.g. iss_001")
    args = parser.parse_args()

    print(f"Removing document: {args.document_id}\n")

    print("Step 1: document file")
    remove_document_file(args.document_id)

    print("\nStep 2: chunk files (both variants)")
    remove_chunk_files(args.document_id)

    print("\nStep 3: Qdrant points (both collections)")
    remove_qdrant_points(args.document_id)

    print(f"\nDone. {args.document_id} has been removed from all pipeline stages.")
    print("Remember to also remove its row from data/sources/sources_full.csv if it shouldn't be re-collected.")


if __name__ == "__main__":
    main()
