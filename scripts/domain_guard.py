"""
JIRVA - Domain Guard
-------------------------
Combines three signals to classify an incoming ticket, per the roadmap's
explicit instruction NOT to just ask the LLM "is this Jira-related?" and
trust it blindly:

  Signal 1: retrieval confidence (top rerank score from the real KB pipeline)
  Signal 2: reference-example similarity (max cosine similarity to a small
            curated set of example in-domain tickets)
  Signal 3: constrained LLM classification (ticket_analysis.py), given
            both signals above as context - NOT asked in isolation

Short-circuit: if BOTH Signal 1 and Signal 2 independently indicate
out-of-domain (below their respective thresholds), return OUT_OF_DOMAIN
immediately without calling the LLM. Otherwise, call the full LLM-based
ticket analysis.

IMPORTANT: threshold values below are PLACEHOLDERS, not calibrated. They
are exposed as parameters specifically so Task 5's broader test set can
determine appropriate values empirically, rather than being locked in from
today's small sample - per explicit project decision.

Usage:
    python domain_guard.py "Why can't I move my issue to Done?" --chunks-dir ../data/chunks/400_variant --collection jirva_400
"""

import argparse
import os

import numpy as np
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer, CrossEncoder

from bm25_search import build_bm25_index
from hybrid_search import vector_search, bm25_search, reciprocal_rank_fusion
from rerank_search import rerank
from ticket_analysis import analyze_ticket

EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"
RERANK_MODEL_NAME = "BAAI/bge-reranker-base"

# PLACEHOLDER thresholds - NOT calibrated. To be determined empirically in Task 5.
DEFAULT_RETRIEVAL_THRESHOLD = 0.10
DEFAULT_REFERENCE_THRESHOLD = 0.50

# Small curated reference set: 2 example tickets per KB category, hand-written
# to sound like realistic support tickets (not just category names).
REFERENCE_TICKETS = {
    "01_Workflows": [
        "Why can't I transition my issue to a different status?",
        "How do I add a new status to our workflow?",
    ],
    "02_Permissions": [
        "Why can't my teammate see this project?",
        "How do I give someone edit access to issues?",
    ],
    "03_Issues": [
        "How do I create a subtask under an existing issue?",
        "Can I change an issue's type after creating it?",
    ],
    "04_Projects": [
        "What's the difference between a team-managed and company-managed project?",
        "How do I find out what type of project I'm working in?",
    ],
    "05_Fields": [
        "How do I add a custom field to my issue form?",
        "Why isn't a field showing up on my screen?",
    ],
    "06_Search": [
        "How do I write a JQL query to find my assigned issues?",
        "How do I save a search so I can reuse it later?",
    ],
    "07_Boards": [
        "How do I set up a Kanban board for my team?",
        "Why aren't my issues showing up on the board?",
    ],
    "08_Notifications": [
        "Why am I not getting emails when issues are updated?",
        "How do I turn off notifications for a specific project?",
    ],
    "09_Jira_Service_Management": [
        "What is a queue and how do I set one up?",
        "How do I configure SLA goals for support requests?",
    ],
    "10_Troubleshooting": [
        "My browser shows a blank page when I open Jira.",
        "Customers aren't getting notified when their ticket updates.",
    ],
}


def build_reference_embeddings(embed_model):
    """Flatten and embed all reference tickets once. Returns (texts, embeddings)."""
    texts = []
    for category, tickets in REFERENCE_TICKETS.items():
        texts.extend(tickets)
    embeddings = embed_model.encode(texts, normalize_embeddings=True)
    return texts, embeddings


def compute_reference_similarity(embed_model, ticket, ref_texts, ref_embeddings):
    """Returns the max cosine similarity between the ticket and any reference example."""
    ticket_embedding = embed_model.encode(ticket, normalize_embeddings=True)
    similarities = np.dot(ref_embeddings, ticket_embedding)  # embeddings are normalized, so dot = cosine
    max_idx = int(np.argmax(similarities))
    return float(similarities[max_idx]), ref_texts[max_idx]


def compute_retrieval_signal(qdrant_client, embed_model, cross_encoder, bm25, chunks,
                              collection, ticket, candidate_k=25):
    """Runs the real hybrid + rerank pipeline and returns (top_score, top_evidence_list, reranked_full)."""
    vec_results = vector_search(qdrant_client, embed_model, collection, ticket, candidate_k)
    bm25_results = bm25_search(bm25, chunks, ticket, candidate_k)
    hybrid_candidates = reciprocal_rank_fusion(vec_results, bm25_results)
    reranked = rerank(cross_encoder, ticket, hybrid_candidates[:candidate_k], final_k=5)

    top_score = reranked[0][1] if reranked else 0.0
    top_evidence = [
        {"title": chunk["document_title"], "category": chunk["category"]}
        for chunk, score, vr, br in reranked
    ]
    return top_score, top_evidence, reranked


def check_domain(ticket, qdrant_client, embed_model, cross_encoder, bm25, chunks,
                  ref_texts, ref_embeddings, collection,
                  retrieval_threshold=DEFAULT_RETRIEVAL_THRESHOLD,
                  reference_threshold=DEFAULT_REFERENCE_THRESHOLD):
    """
    Returns a dict with the full decision trail:
    {
      "domain": "Jira" | "Out-of-Domain",
      "short_circuited": bool,
      "retrieval_top_score": float,
      "reference_similarity_score": float,
      "closest_reference_ticket": str,
      "analysis": dict or None   # full ticket_analysis result if LLM was called
    }
    """
    retrieval_score, top_evidence, reranked_full = compute_retrieval_signal(
        qdrant_client, embed_model, cross_encoder, bm25, chunks, collection, ticket
    )
    reference_score, closest_ref = compute_reference_similarity(
        embed_model, ticket, ref_texts, ref_embeddings
    )

    both_signals_low = (retrieval_score < retrieval_threshold) and (reference_score < reference_threshold)

    result = {
        "retrieval_top_score": retrieval_score,
        "reference_similarity_score": reference_score,
        "closest_reference_ticket": closest_ref,
        "reranked_evidence": reranked_full,
    }

    if both_signals_low:
        result["domain"] = "Out-of-Domain"
        result["short_circuited"] = True
        result["analysis"] = None
        return result

    analysis = analyze_ticket(ticket, retrieval_score, reference_score, top_evidence)
    result["domain"] = analysis["domain"]
    result["short_circuited"] = False
    result["analysis"] = analysis
    return result


def main():
    parser = argparse.ArgumentParser(description="JIRVA domain guard - test the 3-signal domain check")
    parser.add_argument("ticket", help="The ticket text to check")
    parser.add_argument("--chunks-dir", required=True)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--retrieval-threshold", type=float, default=DEFAULT_RETRIEVAL_THRESHOLD,
                         help=f"PLACEHOLDER, not calibrated (default {DEFAULT_RETRIEVAL_THRESHOLD})")
    parser.add_argument("--reference-threshold", type=float, default=DEFAULT_REFERENCE_THRESHOLD,
                         help=f"PLACEHOLDER, not calibrated (default {DEFAULT_REFERENCE_THRESHOLD})")
    args = parser.parse_args()

    load_dotenv()
    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")

    print("Loading models ...")
    embed_model = SentenceTransformer(EMBED_MODEL_NAME)
    cross_encoder = CrossEncoder(RERANK_MODEL_NAME)
    qdrant_client = QdrantClient(url=url, api_key=api_key)

    print(f"Building BM25 index from {args.chunks_dir} ...")
    bm25, chunks = build_bm25_index(args.chunks_dir)

    print("Embedding reference ticket set ...")
    ref_texts, ref_embeddings = build_reference_embeddings(embed_model)
    print(f"Reference set: {len(ref_texts)} example tickets\n")

    print(f"Ticket: \"{args.ticket}\"\n")
    result = check_domain(
        args.ticket, qdrant_client, embed_model, cross_encoder, bm25, chunks,
        ref_texts, ref_embeddings, args.collection,
        args.retrieval_threshold, args.reference_threshold,
    )

    print("--- Domain Guard Result ---")
    print(f"Retrieval top score:      {result['retrieval_top_score']:.4f} (threshold: {args.retrieval_threshold})")
    print(f"Reference similarity:     {result['reference_similarity_score']:.4f} (threshold: {args.reference_threshold})")
    print(f"Closest reference ticket: \"{result['closest_reference_ticket']}\"")
    print(f"Short-circuited:          {result['short_circuited']}")
    print(f"Domain:                   {result['domain']}")
    if result["analysis"]:
        print("\nFull ticket analysis:")
        for k, v in result["analysis"].items():
            if k not in ("raw_llm_output",):
                print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
