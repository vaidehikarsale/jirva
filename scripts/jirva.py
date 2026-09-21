"""
JIRVA - Complete Pipeline Entry Point
-------------------------------------------
The full system, Day 9 deliverable: Ticket -> Domain Guard + Ticket Analysis
-> (if out-of-domain) -> OUT_OF_DOMAIN fallback message
-> (if in-domain) -> Retrieval + Reranking (already done by domain guard)
                   -> Decision Engine (RESOLVE / GUIDE / ESCALATE / FALLBACK)
                   -> RESOLVE: generate grounded answer
                   -> GUIDE:   generate diagnostic-steps answer (dedicated prompt,
                               same Nemotron call - no new LLM call added)
                   -> ESCALATE: no generation - return evidence + reason for a human agent
                   -> FALLBACK: no generation - return the fixed insufficient-evidence message

This reuses domain_guard.py's already-computed retrieval evidence for both
the decision engine and generation (no redundant re-retrieval, no redundant
LLM calls beyond the single existing Nemotron call).

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
from decision_engine import decide, RESOLVE, GUIDE, ESCALATE, FALLBACK, FALLBACK_MESSAGE

EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"
RERANK_MODEL_NAME = "BAAI/bge-reranker-base"

OUT_OF_DOMAIN_MESSAGE = (
    "This query appears to be outside JIRVA's supported Jira support domain. "
    "JIRVA can help with Jira Cloud administration and usage questions - "
    "workflows, permissions, issues, projects, fields, search, boards, "
    "notifications, service management, and troubleshooting."
)

# Mirrors rag_answer.py's SYSTEM_PROMPT structure exactly (same rule numbering
# and grounding constraints), diverging only where GUIDE must behave differently
# from RESOLVE: no definitive diagnosis, diagnostic/verification steps instead.
GUIDE_SYSTEM_PROMPT = """You are JIRVA, an AI assistant that helps users troubleshoot Jira Cloud issues.

You will be given a user's support ticket and a set of evidence documents retrieved from official Atlassian documentation. In this case, the evidence's confidence and/or category alignment with the ticket is not strong enough to support a definitive answer - your job is to guide the user toward narrowing down or confirming the issue, not to resolve it outright.

Follow these rules strictly:
1. Base your answer ONLY on the provided evidence. Do not use outside knowledge about Jira, even if you believe it to be true.
2. Do NOT state or imply a definitive root cause or a guaranteed fix. Instead, provide clear, numbered diagnostic or verification steps the user can follow to narrow down or confirm the issue themselves.
3. Where the evidence only partially applies to the ticket, say so explicitly rather than overstating its relevance.
4. Cite which source document(s) each step comes from, using the source titles/URLs provided with the evidence.
5. You cannot perform any actions in Jira yourself. Never say or imply that you have changed a setting, moved an issue, or performed any action. You can only explain what the user should check or try.
6. If the evidence doesn't support any concrete diagnostic step, say so plainly rather than guessing.
"""


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
            "outcome": None,
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
    ta = guard_result["analysis"]

    evidence_confidence = reranked[0][1] if reranked else 0.0
    top_evidence_category = reranked[0][0]["category"] if reranked else None

    decision = decide(
        evidence_confidence=evidence_confidence,
        risk=ta["risk"],
        ticket_category=ta["category"],
        top_evidence_category=top_evidence_category,
    )
    outcome = decision["outcome"]

    result = {
        "ticket": ticket,
        "domain": "Jira",
        "outcome": outcome,
        "decision": decision,
        "ticket_analysis": ta,
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

    if outcome == FALLBACK:
        result["answer"] = FALLBACK_MESSAGE
        return result

    if outcome == ESCALATE:
        # No generation call - return evidence + reason for a human agent, per
        # explicit instruction: skip Nemotron entirely for ESCALATE, for now.
        result["answer"] = None
        result["escalation_reason"] = decision["reason"]
        return result

    # RESOLVE or GUIDE: both generate, using a different system prompt.
    # Same single Nemotron call either way - no new LLM call, no new architecture.
    evidence_block = format_evidence(reranked)
    user_message = build_user_message(ticket, evidence_block)
    system_prompt = GUIDE_SYSTEM_PROMPT if outcome == GUIDE else SYSTEM_PROMPT

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    result["answer"] = call_nemotron(messages)
    return result


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
    if result["outcome"]:
        print(f"OUTCOME: {result['outcome']}")
        print(f"Reason: {result['decision']['reason']}")
    print("=" * 70)

    if result["outcome"] == ESCALATE:
        print("\nESCALATED - no answer generated. Handing off to human agent.")
        print(f"Escalation reason: {result['escalation_reason']}")
    else:
        print("\nANSWER")
        print("-" * 70)
        print(result["answer"])

    if result.get("evidence_used"):
        print("\n" + "-" * 70)
        print("EVIDENCE USED")
        print("-" * 70)
        for i, e in enumerate(result["evidence_used"], start=1):
            print(f"[{i}] score={e['score']:.3f} | {e['title']} | {e['url']}")


if __name__ == "__main__":
    main()
