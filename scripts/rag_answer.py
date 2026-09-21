"""
JIRVA - RAG Generation (full pipeline)
-------------------------------------------
Ticket -> Hybrid Retrieval -> Reranker -> Top-K Evidence -> Nemotron -> Answer + Sources

This is JIRVA's first real end-to-end milestone: a working RAG system that
answers Jira support questions grounded in the collected knowledge base.

Usage:
    python rag_answer.py "Why can't I move my issue to Done?" --chunks-dir ../data/chunks/400_variant --collection jirva_400
"""

import argparse
import os

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer, CrossEncoder

from bm25_search import build_bm25_index
from hybrid_search import vector_search, bm25_search, reciprocal_rank_fusion
from rerank_search import rerank
from openrouter_client import call_nemotron

EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"
RERANK_MODEL_NAME = "BAAI/bge-reranker-base"

SYSTEM_PROMPT = """You are JIRVA, an AI assistant that helps users troubleshoot Jira Cloud issues.

You will be given a user's support ticket and a set of evidence documents retrieved from official Atlassian documentation. Each piece of evidence includes a relevance score - higher scores indicate stronger confidence the content is actually relevant to the question. Use this as one signal among others, not as a hard rule.

Follow these rules strictly:
1. Base your answer ONLY on the provided evidence. Do not use outside knowledge about Jira, even if you believe it to be true.
2. If the evidence does not clearly answer the ticket, say so explicitly. Do not guess or fill gaps with plausible-sounding information.
3. When you do have sufficient evidence, provide clear, numbered troubleshooting steps the user can follow themselves.
4. Cite which source document(s) each part of your answer comes from, using the source titles/URLs provided with the evidence.
5. You cannot perform any actions in Jira yourself. Never say or imply that you have changed a setting, moved an issue, or performed any action. You can only explain what the user should do.
6. If asked about something outside Jira Cloud administration/usage, or if no evidence is provided, say this is outside what you can help with rather than attempting an answer.
"""


def format_evidence(reranked_results):
    """Turns reranked (chunk, score, vec_rank, bm25_rank) tuples into a
    numbered evidence block for the prompt, including each chunk's rerank
    score as a labeled signal."""
    blocks = []
    for i, (chunk, score, vec_rank, bm25_rank) in enumerate(reranked_results, start=1):
        blocks.append(
            f"[Evidence {i}] (relevance score: {score:.3f})\n"
            f"Source: {chunk['document_title']}\n"
            f"URL: {chunk['source_url']}\n"
            f"Content: {chunk['content']}\n"
        )
    return "\n".join(blocks)


def build_user_message(ticket, evidence_block):
    return (
        f"User's support ticket:\n\"{ticket}\"\n\n"
        f"Retrieved evidence:\n\n{evidence_block}\n\n"
        f"Based only on the evidence above, answer the user's ticket following all the rules you were given."
    )


def answer_ticket(ticket, embed_model, cross_encoder, qdrant_client, bm25, chunks,
                   collection, candidate_k=25, final_k=5):
    vec_results = vector_search(qdrant_client, embed_model, collection, ticket, candidate_k)
    bm25_results = bm25_search(bm25, chunks, ticket, candidate_k)
    hybrid_candidates = reciprocal_rank_fusion(vec_results, bm25_results)
    reranked = rerank(cross_encoder, ticket, hybrid_candidates[:candidate_k], final_k)

    evidence_block = format_evidence(reranked)
    user_message = build_user_message(ticket, evidence_block)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    answer = call_nemotron(messages)
    return answer, reranked


def main():
    parser = argparse.ArgumentParser(description="JIRVA full RAG pipeline: retrieval + reranking + generation")
    parser.add_argument("ticket", help="The support ticket / question text")
    parser.add_argument("--chunks-dir", required=True, help="Path to a chunk variant folder")
    parser.add_argument("--collection", required=True, help="Qdrant collection name")
    parser.add_argument("--candidate-k", type=int, default=25, help="Candidates per retrieval method (default 25)")
    parser.add_argument("--final-k", type=int, default=5, help="Evidence chunks passed to the LLM (default 5)")
    args = parser.parse_args()

    load_dotenv()
    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")

    print("Loading models (embedding + reranker) ...")
    embed_model = SentenceTransformer(EMBED_MODEL_NAME)
    cross_encoder = CrossEncoder(RERANK_MODEL_NAME)
    qdrant_client = QdrantClient(url=url, api_key=api_key)

    print(f"Building BM25 index from {args.chunks_dir} ...")
    bm25, chunks = build_bm25_index(args.chunks_dir)
    print(f"Indexed {len(chunks)} chunks\n")

    print(f"Ticket: \"{args.ticket}\"\n")
    print("Retrieving evidence and generating answer ...\n")

    answer, reranked = answer_ticket(
        args.ticket, embed_model, cross_encoder, qdrant_client, bm25, chunks,
        args.collection, args.candidate_k, args.final_k
    )

    print("=" * 70)
    print("ANSWER")
    print("=" * 70)
    print(answer)

    print("\n" + "=" * 70)
    print("EVIDENCE USED (for reference/verification)")
    print("=" * 70)
    for i, (chunk, score, vec_rank, bm25_rank) in enumerate(reranked, start=1):
        print(f"[{i}] score={score:.3f} | {chunk['document_title']} | {chunk['source_url']}")


if __name__ == "__main__":
    main()
