"""
JIRVA - BM25 Keyword Search
-------------------------------
Builds an in-memory BM25 index from a chunk variant folder and supports
keyword search. Designed to be imported by the hybrid retrieval script
(Task 3), but also runnable standalone to test BM25 alone.

The index is rebuilt fresh from the chunk JSON files every run - no
persisted/cached index file, so it never goes stale relative to your
actual chunk data.

Usage (standalone test):
    python bm25_search.py "permission scheme" --chunks-dir ../data/chunks/400_variant --top-k 5
"""

import argparse
import json
import os
import re

from rank_bm25 import BM25Okapi

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def tokenize(text):
    """Simple lowercase alphanumeric tokenizer - good enough for BM25 on
    technical terminology like 'JQL', 'Browse Projects permission', etc."""
    return TOKEN_PATTERN.findall(text.lower())


def load_chunks(chunks_dir):
    """Walk <chunks_dir>/<category>/*.json and return a list of chunk dicts."""
    chunks = []
    for category in sorted(os.listdir(chunks_dir)):
        category_path = os.path.join(chunks_dir, category)
        if not os.path.isdir(category_path):
            continue
        for fname in sorted(os.listdir(category_path)):
            if fname.endswith(".json"):
                with open(os.path.join(category_path, fname), "r", encoding="utf-8") as f:
                    try:
                        chunks.append(json.load(f))
                    except json.JSONDecodeError:
                        continue
    return chunks


def build_bm25_index(chunks_dir):
    """Returns (bm25_index, chunks_list). chunks_list[i] corresponds to the
    i-th document in the BM25 index, so BM25 result indices map directly back
    to chunk metadata."""
    chunks = load_chunks(chunks_dir)
    tokenized_corpus = [tokenize(c["content"]) for c in chunks]
    bm25 = BM25Okapi(tokenized_corpus)
    return bm25, chunks


def search(bm25, chunks, query, top_k=5):
    """Returns a list of (chunk_dict, score) tuples, sorted best-first."""
    tokenized_query = tokenize(query)
    scores = bm25.get_scores(tokenized_query)
    ranked = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
    return [(chunks[i], scores[i]) for i in ranked[:top_k]]


def print_results(results):
    for rank, (chunk, score) in enumerate(results, start=1):
        snippet = chunk["content"][:220].replace("\n", " ")
        print(f"  #{rank} | score={score:.4f} | {chunk['document_title']} [{chunk['category']}]")
        print(f"      chunk_id: {chunk['chunk_id']}")
        print(f"      url: {chunk['source_url']}")
        print(f"      snippet: {snippet}...")


def main():
    parser = argparse.ArgumentParser(description="Standalone BM25 keyword search test")
    parser.add_argument("query", help="The query text to search for")
    parser.add_argument("--chunks-dir", required=True, help="Path to a chunk variant folder")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results to show (default 5)")
    args = parser.parse_args()

    print(f"Building BM25 index from {args.chunks_dir} ...")
    bm25, chunks = build_bm25_index(args.chunks_dir)
    print(f"Indexed {len(chunks)} chunks\n")

    print(f"Query: \"{args.query}\"")
    results = search(bm25, chunks, args.query, args.top_k)
    print_results(results)


if __name__ == "__main__":
    main()
