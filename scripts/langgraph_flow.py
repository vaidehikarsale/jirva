"""
JIRVA - LangGraph Orchestration (Day 10, Task 2)
-------------------------------------------------------
Wires the existing pipeline (domain_guard + ticket_analysis, decision_engine,
generation) into a LangGraph state graph. This is an ORCHESTRATION layer only,
per explicit Day 10 scope: no new LLM calls, no new logic, no new components.
Every node below calls a function that already exists and was already
verified in Days 7-9 - this file does not reimplement any of it.

Node mapping, and why it differs slightly from the roadmap's literal diagram:

    Roadmap diagram:  Ticket Analysis -> Domain Check -> Risk Assessment ->
                       Retrieve -> Rerank -> Generate -> Validate -> Decision
    This graph:        ticket_analysis (domain+risk+retrieve+rerank, ONE
                       call to check_domain) -> decision -> conditional
                       (fallback | escalate | generate)

  - Domain Check + Risk Assessment are ONE node here, not two - they were
    already one combined LLM call before Day 10 (ticket_analysis.py's
    analyze_ticket returns category/risk/domain together). Splitting them
    into two graph nodes would either be cosmetic (same call, relabeled) or
    would silently add a second LLM call - neither was authorized.
  - Retrieve/Rerank are not separate nodes either: check_domain() already
    runs the real hybrid+rerank pipeline internally to compute its retrieval-
    confidence signal, and jirva.py has always reused that same evidence for
    generation rather than re-retrieving. Adding standalone Retrieve/Rerank
    nodes downstream would mean a real redundant second retrieval call -
    explicitly out of scope for today.
  - Decision runs BEFORE Generate, not after - this preserves Day 9's actual,
    calibrated control flow (FALLBACK/ESCALATE skip generation entirely).
    The roadmap's Generate-then-Validate-then-Decision order was treated as
    a diagram simplification, not a literal instruction to reverse Day 9's
    logic, per explicit confirmation.
  - There is no separate "Validate" node. Nothing in Days 1-9 implements a
    distinct grounding-validation step (Day 7 identified this gap and
    explicitly deferred it - it remains unimplemented). decision_engine.py's
    decide() is the closest existing analog and is not being expanded today.

New dependency: langgraph (free, open source - pip install langgraph).
No other new dependencies.

Usage (standalone test, mirrors jirva.py's CLI):
    python langgraph_flow.py "Why can't I move my issue to Done?" --chunks-dir ../data/chunks/400_variant --collection jirva_400
"""

import argparse
import os
from typing import TypedDict, Optional, List, Any

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer, CrossEncoder
from langgraph.graph import StateGraph, START, END

from bm25_search import build_bm25_index
from domain_guard import build_reference_embeddings, check_domain
from decision_engine import decide, RESOLVE, GUIDE, ESCALATE, FALLBACK, FALLBACK_MESSAGE
from rag_answer import SYSTEM_PROMPT, format_evidence, build_user_message
from openrouter_client import call_nemotron
# Reused, not duplicated - GUIDE_SYSTEM_PROMPT and OUT_OF_DOMAIN_MESSAGE
# already live in jirva.py (Day 9 Task 3). Importing rather than copying
# avoids two copies of the same prompt text drifting apart over time.
from jirva import GUIDE_SYSTEM_PROMPT, OUT_OF_DOMAIN_MESSAGE

EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"
RERANK_MODEL_NAME = "BAAI/bge-reranker-base"


class JirvaState(TypedDict, total=False):
    ticket: str
    domain: str
    ticket_analysis: Optional[dict]
    retrieval_top_score: float
    reference_similarity_score: float
    short_circuited: bool
    reranked_evidence: List[Any]
    evidence_confidence: float
    top_evidence_category: Optional[str]
    outcome: Optional[str]
    decision: Optional[dict]
    answer: Optional[str]
    evidence_used: List[dict]
    escalation_reason: Optional[str]


def build_graph(qdrant_client, embed_model, cross_encoder, bm25, chunks,
                ref_texts, ref_embeddings, collection):
    """Returns a compiled LangGraph app. All shared pipeline resources
    (models, index, reference embeddings) are captured via closure, the
    same resources jirva.py already loads once per run - not reloaded
    per-node, not reloaded per-request."""

    def ticket_analysis_node(state: JirvaState) -> dict:
        guard_result = check_domain(
            state["ticket"], qdrant_client, embed_model, cross_encoder, bm25, chunks,
            ref_texts, ref_embeddings, collection,
        )
        return {
            "domain": guard_result["domain"],
            "ticket_analysis": guard_result["analysis"],
            "retrieval_top_score": guard_result["retrieval_top_score"],
            "reference_similarity_score": guard_result["reference_similarity_score"],
            "short_circuited": guard_result["short_circuited"],
            "reranked_evidence": guard_result["reranked_evidence"],
        }

    def route_after_analysis(state: JirvaState) -> str:
        return "out_of_domain" if state["domain"] == "Out-of-Domain" else "decision"

    def out_of_domain_node(state: JirvaState) -> dict:
        return {"outcome": None, "answer": OUT_OF_DOMAIN_MESSAGE, "evidence_used": []}

    def decision_node(state: JirvaState) -> dict:
        reranked = state.get("reranked_evidence") or []
        ta = state["ticket_analysis"]
        evidence_confidence = reranked[0][1] if reranked else 0.0
        top_evidence_category = reranked[0][0]["category"] if reranked else None

        decision = decide(
            evidence_confidence=evidence_confidence,
            risk=ta["risk"],
            ticket_category=ta["category"],
            top_evidence_category=top_evidence_category,
        )
        evidence_used = [
            {"title": c["document_title"], "url": c["source_url"], "score": float(s)}
            for c, s, vr, br in reranked
        ]
        return {
            "evidence_confidence": evidence_confidence,
            "top_evidence_category": top_evidence_category,
            "decision": decision,
            "outcome": decision["outcome"],
            "evidence_used": evidence_used,
        }

    def route_after_decision(state: JirvaState) -> str:
        outcome = state["outcome"]
        if outcome == FALLBACK:
            return "fallback"
        if outcome == ESCALATE:
            return "escalate"
        return "generate"  # RESOLVE or GUIDE

    def fallback_node(state: JirvaState) -> dict:
        return {"answer": FALLBACK_MESSAGE}

    def escalate_node(state: JirvaState) -> dict:
        # No generation call, per Day 9 explicit decision - unchanged today.
        return {"answer": None, "escalation_reason": state["decision"]["reason"]}

    def generate_node(state: JirvaState) -> dict:
        reranked = state["reranked_evidence"]
        evidence_block = format_evidence(reranked)
        user_message = build_user_message(state["ticket"], evidence_block)
        system_prompt = GUIDE_SYSTEM_PROMPT if state["outcome"] == GUIDE else SYSTEM_PROMPT

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        answer = call_nemotron(messages)
        return {"answer": answer}

    graph = StateGraph(JirvaState)
    graph.add_node("ticket_analysis", ticket_analysis_node)
    graph.add_node("out_of_domain", out_of_domain_node)
    graph.add_node("decision", decision_node)
    graph.add_node("fallback", fallback_node)
    graph.add_node("escalate", escalate_node)
    graph.add_node("generate", generate_node)

    graph.add_edge(START, "ticket_analysis")
    graph.add_conditional_edges(
        "ticket_analysis", route_after_analysis,
        {"out_of_domain": "out_of_domain", "decision": "decision"},
    )
    graph.add_edge("out_of_domain", END)
    graph.add_conditional_edges(
        "decision", route_after_decision,
        {"fallback": "fallback", "escalate": "escalate", "generate": "generate"},
    )
    graph.add_edge("fallback", END)
    graph.add_edge("escalate", END)
    graph.add_edge("generate", END)

    return graph.compile()


def main():
    """Standalone test - mirrors jirva.py's CLI and output format exactly,
    so results can be directly diffed against jirva.py's known-good output
    for the same ticket (this IS Task 3 - see langgraph_flow.py docstring)."""
    parser = argparse.ArgumentParser(description="JIRVA - LangGraph orchestration test")
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

    print("Building LangGraph app ...")
    app = build_graph(
        qdrant_client, embed_model, cross_encoder, bm25, chunks,
        ref_texts, ref_embeddings, args.collection,
    )

    print(f"\nTicket: \"{args.ticket}\"\n")
    result = app.invoke({"ticket": args.ticket})

    print("=" * 70)
    print(f"DOMAIN: {result['domain']}")
    if result.get("ticket_analysis"):
        ta = result["ticket_analysis"]
        print(f"Intent: {ta['intent']} | Category: {ta['category']} | "
              f"Severity: {ta['severity']} | Risk: {ta['risk']}")
    if result.get("outcome"):
        print(f"OUTCOME: {result['outcome']}")
        print(f"Reason: {result['decision']['reason']}")
    print("=" * 70)

    if result.get("outcome") == ESCALATE:
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
