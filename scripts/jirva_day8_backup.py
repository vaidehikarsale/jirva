"""
JIRVA - Complete Pipeline Entry Point
-------------------------------------------
The full system, Day 8 deliverable: Ticket -> Domain Guard + Ticket Analysis
-> (if in-domain) Retrieval + Reranking + Generation -> Answer
                  (if out-of-domain) -> OUT_OF_DOMAIN fallback message

This is the first script that represents "JIRVA" as a whole, rather than
a single pipeline stage. It reuses domain_guard.py's already-computed
retrieval evidence for generation (no redundant re-retrieval).

Usage:
    python jirva.py "Why can't I move my issue to Done?" --chunks-dir ../data/chunks/400_variant --collection jirva_400
"""

import argparse
import os

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer, CrossEncoder

from bm25_search import build_bm25_index
from domain_guard import build_reference_embeddings, check_domain
from rag_answer import SYSTEM_PROMPT, format_evidence, build_user_message
from openrouter_client import call_nemotron

EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"
RERANK_MODEL_NAME = "BAAI/bge-reranker-base"

OUT_OF_DOMAIN_MESSAGE = (
    "This query appears to be outside JIRVA's supported Jira support domain. "
    "JIRVA can help with Jira Cloud administration and usage questions - "
    "workflows, permissions, issues, projects, fields, search, boards, "
    "notifications, service management, and troubleshooting."
)


def process_ticket(ticket, qdrant_client, embed_model, cross_encoder, bm25, chunks,
                    ref_texts, ref_embeddings, collection):
    """Runs the complete pipeline and returns a result dict with everything
    needed to inspect the decision trail, not just the final answer."""
    guard_result = check_domain(
        ticket, qdrant_client, embed_model, cross_encoder, bm25, chunks,
        ref_texts, ref_embeddings, collection,
    )

    if guard_result["domain"] == "Out-of-Domain":
        return {
            "ticket": ticket,
            "domain": "Out-of-Domain",
            "answer": OUT_OF_DOMAIN_MESSAGE,
            "ticket_analysis": guard_result["analysis"],
            "domain_guard_signals": {
                "retrieval_top_score": guard_result["retrieval_top_score"],
                "reference_similarity_score": guard_result["reference_similarity_score"],
                "short_circuited": guard_result["short_circuited"],
            },
        }

    # In-domain: reuse the retrieval evidence already computed by the domain guard
    reranked = guard_result["reranked_evidence"]
    evidence_block = format_evidence(reranked)
    user_message = build_user_message(ticket, evidence_block)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    answer = call_nemotron(messages)

    return {
        "ticket": ticket,
        "domain": "Jira",
        "answer": answer,
        "ticket_analysis": guard_result["analysis"],
        "domain_guard_signals": {
            "retrieval_top_score": guard_result["retrieval_top_score"],
            "reference_similarity_score": guard_result["reference_similarity_score"],
            "short_circuited": guard_result["short_circuited"],
        },
        "evidence_used": [
            {"title": c["document_title"], "url": c["source_url"], "score": s}
            for c, s, vr, br in reranked
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="JIRVA - complete pipeline")
    parser.add_argument("ticket", help="The support ticket text")
    parser.add_argument("--chunks-dir", required=True)
    parser.add_argument("--collection", required=True)
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

    print(f"\nTicket: \"{args.ticket}\"\n")
    result = process_ticket(
        args.ticket, qdrant_client, embed_model, cross_encoder, bm25, chunks,
        ref_texts, ref_embeddings, args.collection,
    )

    print("=" * 70)
    print(f"DOMAIN: {result['domain']}")
    if result["ticket_analysis"]:
        ta = result["ticket_analysis"]
        print(f"Intent: {ta['intent']} | Category: {ta['category']} | "
              f"Severity: {ta['severity']} | Risk: {ta['risk']}")
    print("=" * 70)
    print("\nANSWER")
    print("-" * 70)
    print(result["answer"])

    if "evidence_used" in result:
        print("\n" + "-" * 70)
        print("EVIDENCE USED")
        print("-" * 70)
        for i, e in enumerate(result["evidence_used"], start=1):
            print(f"[{i}] score={e['score']:.3f} | {e['title']} | {e['url']}")


if __name__ == "__main__":
    main()
