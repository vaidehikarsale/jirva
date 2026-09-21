"""
JIRVA - Reranking (Cross-Encoder on top of Hybrid Retrieval)
-----------------------------------------------------------------
Takes the wider candidate pool from hybrid retrieval (vector + BM25 via RRF)
and rescores each (query, chunk) pair directly using a cross-encoder, which
reads the query and chunk together rather than comparing separately-computed
vectors. This trades speed for precision, and is specifically meant to fix
cases where hybrid retrieval found the right chunk but ranked it too low
to make a small top-K cut.

IMPORTANT: reranking can only reorder candidates that hybrid retrieval
already returned. If a chunk isn't in the hybrid candidate pool at all,
reranking cannot recover it - this script also reports whether the
previously-identified difficult queries (vocabulary mismatch cases) behave
as expected under this constraint.

Usage:
    python rerank_search.py "your query" --chunks-dir ../data/chunks/400_variant --collection jirva_400
    python rerank_search.py "your query" --chunks-dir ../data/chunks/400_variant --collection jirva_400 --candidate-k 30 --final-k 5
"""

import argparse
import os

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer, CrossEncoder

from bm25_search import build_bm25_index
from hybrid_search import vector_search, bm25_search, reciprocal_rank_fusion

EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"
RERANK_MODEL_NAME = "BAAI/bge-reranker-base"


def rerank(cross_encoder, query, candidates, final_k):
    """candidates: list of (chunk_dict, rrf_score, vec_rank, bm25_rank) from hybrid retrieval.
    Returns the same tuples re-sorted by cross-encoder score, with the score added."""
    pairs = [(query, c[0]["content"]) for c in candidates]
    scores = cross_encoder.predict(pairs)

    reranked = [
        (candidates[i][0], scores[i], candidates[i][2], candidates[i][3])
        for i in range(len(candidates))
    ]
    reranked.sort(key=lambda x: x[1], reverse=True)
    return reranked[:final_k]


def print_results(results, label):
    print(f"\n--- {label} ---")
    for rank, (chunk, score, vec_rank, bm25_rank) in enumerate(results, start=1):
        origin = []
        if vec_rank is not None:
            origin.append(f"vector#{vec_rank}")
        if bm25_rank is not None:
            origin.append(f"bm25#{bm25_rank}")
        origin_str = " + ".join(origin) if origin else "n/a"

        snippet = chunk["content"][:200].replace("\n", " ")
        print(f"  #{rank} | rerank_score={score:.4f} | originally found by: {origin_str}")
        print(f"      {chunk['document_title']} [{chunk['category']}]")
        print(f"      chunk_id: {chunk['chunk_id']}")
        print(f"      snippet: {snippet}...")


def main():
    parser = argparse.ArgumentParser(description="JIRVA reranking on top of hybrid retrieval")
    parser.add_argument("query", help="The query text to search for")
    parser.add_argument("--chunks-dir", required=True, help="Path to a chunk variant folder")
    parser.add_argument("--collection", required=True, help="Qdrant collection name")
    parser.add_argument("--candidate-k", type=int, default=25,
                         help="Candidates to pull from each retrieval method before reranking (default 25)")
    parser.add_argument("--final-k", type=int, default=5, help="Final results to show after reranking (default 5)")
    args = parser.parse_args()

    load_dotenv()
    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")

    print(f"Loading embedding model: {EMBED_MODEL_NAME} ...")
    embed_model = SentenceTransformer(EMBED_MODEL_NAME)
    print(f"Loading reranker model: {RERANK_MODEL_NAME} (first run downloads it) ...")
    cross_encoder = CrossEncoder(RERANK_MODEL_NAME)

    client = QdrantClient(url=url, api_key=api_key)

    print(f"Building BM25 index from {args.chunks_dir} ...")
    bm25, chunks = build_bm25_index(args.chunks_dir)
    print(f"Indexed {len(chunks)} chunks\n")

    print(f"Query: \"{args.query}\"")

    vec_results = vector_search(client, embed_model, args.collection, args.query, args.candidate_k)
    bm25_results = bm25_search(bm25, chunks, args.query, args.candidate_k)
    hybrid_candidates = reciprocal_rank_fusion(vec_results, bm25_results)

    # Show hybrid's own top-K (pre-rerank) for direct before/after comparison
    print_results(hybrid_candidates[:args.final_k], f"BEFORE reranking (hybrid RRF top {args.final_k})")

    # Rerank the WIDER candidate pool, not just hybrid's already-truncated top-K
    reranked = rerank(cross_encoder, args.query, hybrid_candidates[:args.candidate_k], args.final_k)
    print_results(reranked, f"AFTER reranking (top {args.final_k} of {min(args.candidate_k, len(hybrid_candidates))} candidates)")


if __name__ == "__main__":
    main()
