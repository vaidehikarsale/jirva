"""
JIRVA - Hybrid Retrieval (Vector + BM25 via Reciprocal Rank Fusion)
------------------------------------------------------------------------
Combines semantic vector search (Qdrant) and keyword search (BM25) into
one merged ranking, using Reciprocal Rank Fusion (RRF). RRF only looks at
RANK POSITION in each individual result list, not raw scores - this avoids
the problem of BM25 and cosine-similarity scores being on incomparable
scales.

RRF formula per chunk:
    score = 1/(k + rank_in_vector_results) + 1/(k + rank_in_bm25_results)
(a term is omitted if the chunk didn't appear in that list's top candidates)

Usage:
    python hybrid_search.py "your query" --chunks-dir ../data/chunks/400_variant --collection jirva_400
    python hybrid_search.py "your query" --chunks-dir ../data/chunks/400_variant --collection jirva_400 --top-k 5 --candidate-k 15
"""

import argparse
import os

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

from bm25_search import build_bm25_index, search as bm25_search_fn

MODEL_NAME = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
RRF_K = 60  # standard damping constant for Reciprocal Rank Fusion


def vector_search(client, model, collection, query, candidate_k):
    query_text = QUERY_PREFIX + query
    query_vector = model.encode(query_text, normalize_embeddings=True).tolist()
    response = client.query_points(
        collection_name=collection,
        query=query_vector,
        limit=candidate_k,
        with_payload=True,
    )
    # Returns list of (chunk_id, chunk_dict, rank) - rank is 1-indexed
    results = []
    for rank, point in enumerate(response.points, start=1):
        chunk = dict(point.payload)
        results.append((chunk["chunk_id"], chunk, rank))
    return results


def bm25_search(bm25, chunks, query, candidate_k):
    raw_results = bm25_search_fn(bm25, chunks, query, top_k=candidate_k)
    results = []
    for rank, (chunk, score) in enumerate(raw_results, start=1):
        results.append((chunk["chunk_id"], chunk, rank))
    return results


def reciprocal_rank_fusion(vector_results, bm25_results, k=RRF_K):
    """Merge two ranked lists into one, scored by RRF. Returns a list of
    (chunk_dict, rrf_score, vector_rank_or_None, bm25_rank_or_None),
    sorted best-first."""
    combined = {}  # chunk_id -> {"chunk": dict, "vector_rank": int|None, "bm25_rank": int|None}

    for chunk_id, chunk, rank in vector_results:
        combined.setdefault(chunk_id, {"chunk": chunk, "vector_rank": None, "bm25_rank": None})
        combined[chunk_id]["vector_rank"] = rank

    for chunk_id, chunk, rank in bm25_results:
        combined.setdefault(chunk_id, {"chunk": chunk, "vector_rank": None, "bm25_rank": None})
        combined[chunk_id]["bm25_rank"] = rank

    scored = []
    for chunk_id, info in combined.items():
        score = 0.0
        if info["vector_rank"] is not None:
            score += 1.0 / (k + info["vector_rank"])
        if info["bm25_rank"] is not None:
            score += 1.0 / (k + info["bm25_rank"])
        scored.append((info["chunk"], score, info["vector_rank"], info["bm25_rank"]))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def print_results(scored_results, top_k):
    for rank, (chunk, score, vec_rank, bm25_rank) in enumerate(scored_results[:top_k], start=1):
        found_by = []
        if vec_rank is not None:
            found_by.append(f"vector#{vec_rank}")
        if bm25_rank is not None:
            found_by.append(f"bm25#{bm25_rank}")
        found_by_str = " + ".join(found_by)

        snippet = chunk["content"][:220].replace("\n", " ")
        print(f"  #{rank} | rrf_score={score:.4f} | found by: {found_by_str}")
        print(f"      {chunk['document_title']} [{chunk['category']}]")
        print(f"      chunk_id: {chunk['chunk_id']}")
        print(f"      url: {chunk['source_url']}")
        print(f"      snippet: {snippet}...")


def main():
    parser = argparse.ArgumentParser(description="JIRVA hybrid retrieval: vector + BM25 via RRF")
    parser.add_argument("query", help="The query text to search for")
    parser.add_argument("--chunks-dir", required=True, help="Path to a chunk variant folder (for BM25)")
    parser.add_argument("--collection", required=True, help="Qdrant collection name (for vector search)")
    parser.add_argument("--top-k", type=int, default=5, help="Number of merged results to show (default 5)")
    parser.add_argument("--candidate-k", type=int, default=15,
                         help="Number of candidates to pull from EACH method before merging (default 15)")
    args = parser.parse_args()

    load_dotenv()
    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")

    print(f"Loading embedding model: {MODEL_NAME} ...")
    model = SentenceTransformer(MODEL_NAME)
    client = QdrantClient(url=url, api_key=api_key)

    print(f"Building BM25 index from {args.chunks_dir} ...")
    bm25, chunks = build_bm25_index(args.chunks_dir)
    print(f"Indexed {len(chunks)} chunks for BM25\n")

    print(f"Query: \"{args.query}\"\n")

    vec_results = vector_search(client, model, args.collection, args.query, args.candidate_k)
    bm25_results = bm25_search(bm25, chunks, args.query, args.candidate_k)

    merged = reciprocal_rank_fusion(vec_results, bm25_results)

    print(f"--- Hybrid results (RRF merge, top {args.top_k}) ---")
    print_results(merged, args.top_k)


if __name__ == "__main__":
    main()
