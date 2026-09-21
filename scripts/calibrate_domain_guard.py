"""
JIRVA - Domain Guard Calibration Test Set (Day 8, Task 5)
----------------------------------------------------------------
Runs a curated set of 20 tickets through the domain guard and logs full
signal scores for each, specifically to calibrate the two placeholder
thresholds empirically rather than guessing from a handful of ad hoc tests.

Includes deliberately adversarial "borderline" tickets - out-of-domain
questions that reuse Jira-sounding vocabulary ("workflow", "permissions",
"custom field") to stress-test whether the reference-similarity signal can
be fooled by surface lexical overlap, plus one deliberate "in-domain but
KB has no answer" case (bulk edit) to confirm the guard correctly
distinguishes OUT_OF_DOMAIN from IN_DOMAIN_INSUFFICIENT_EVIDENCE - these
are NOT the same thing and must not be conflated.

Usage:
    python calibrate_domain_guard.py --chunks-dir ../data/chunks/400_variant --collection jirva_400 --log ../logs/domain_guard_calibration.csv
"""

import argparse
import csv
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer, CrossEncoder

from bm25_search import build_bm25_index
from domain_guard import (
    build_reference_embeddings, check_domain,
    DEFAULT_RETRIEVAL_THRESHOLD, DEFAULT_REFERENCE_THRESHOLD,
)

EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"
RERANK_MODEL_NAME = "BAAI/bge-reranker-base"

# expected_domain: "Jira" or "Out-of-Domain" - our own ground truth for scoring
TEST_TICKETS = [
    # Clear in-domain, spanning categories and difficulty
    ("Why can't I move my issue to Done?", "Jira"),                          # hard vocabulary (Day 7 known case)
    ("How do I create a permission scheme?", "Jira"),
    ("How do I set up a Kanban board?", "Jira"),
    ("What's the difference between team-managed and company-managed projects?", "Jira"),
    ("How do I add a custom field to my issue type?", "Jira"),               # known lexical-confusion case
    ("Why am I not receiving email notifications?", "Jira"),
    ("What is a queue in Jira Service Management?", "Jira"),
    ("How do I link a subtask to a parent issue?", "Jira"),
    ("How do I export project data to Excel?", "Jira"),                     # adjacent, tested already
    ("How do I bulk edit multiple issues at once?", "Jira"),                # in-domain, but KB has no answer - must stay "Jira", NOT out-of-domain

    # Clear out-of-domain
    ("What's the weather like today?", "Out-of-Domain"),
    ("How do I bake a chocolate cake?", "Out-of-Domain"),
    ("What's the fastest sports car in the world?", "Out-of-Domain"),
    ("Who won the latest election?", "Out-of-Domain"),
    ("How do I reset my Windows password?", "Out-of-Domain"),

    # Adversarial: out-of-domain but reusing Jira-sounding vocabulary
    ("What is the best Python framework?", "Out-of-Domain"),                # tested already - borderline
    ("How do I configure a GitHub Actions workflow?", "Out-of-Domain"),     # "workflow" overlap
    ("How do I set up permissions in AWS S3?", "Out-of-Domain"),            # "permissions" overlap
    ("How do I create a custom field in Salesforce?", "Out-of-Domain"),     # "custom field" overlap
    ("What's a good JQL alternative for SQL databases?", "Out-of-Domain"),  # "JQL" mentioned, wrong context
]


def log_row(log_path, row):
    file_exists = os.path.isfile(log_path)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "timestamp", "ticket", "expected_domain", "retrieval_top_score",
                "reference_similarity_score", "short_circuited", "predicted_domain",
                "correct", "predicted_category", "closest_reference_ticket",
            ])
        writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description="Domain guard calibration test set")
    parser.add_argument("--chunks-dir", required=True)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--log", required=True)
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

    print(f"\nRunning {len(TEST_TICKETS)} test tickets through the domain guard "
          f"(using current placeholder thresholds: retrieval={DEFAULT_RETRIEVAL_THRESHOLD}, "
          f"reference={DEFAULT_REFERENCE_THRESHOLD})\n")

    correct_count = 0
    results = []

    for ticket, expected in TEST_TICKETS:
        result = check_domain(
            ticket, qdrant_client, embed_model, cross_encoder, bm25, chunks,
            ref_texts, ref_embeddings, args.collection,
        )
        predicted = result["domain"]
        is_correct = (predicted == expected)
        correct_count += int(is_correct)

        predicted_category = result["analysis"]["category"] if result["analysis"] else "N/A (short-circuited)"

        status = "OK" if is_correct else "MISMATCH"
        print(f"[{status}] \"{ticket[:60]}\"")
        print(f"    expected={expected} | predicted={predicted} | "
              f"retrieval={result['retrieval_top_score']:.4f} | reference={result['reference_similarity_score']:.4f} | "
              f"short_circuit={result['short_circuited']}")

        log_row(args.log, [
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ticket, expected, result["retrieval_top_score"], result["reference_similarity_score"],
            result["short_circuited"], predicted, is_correct, predicted_category,
            result["closest_reference_ticket"],
        ])

        results.append({
            "ticket": ticket, "expected": expected, "predicted": predicted,
            "retrieval": result["retrieval_top_score"], "reference": result["reference_similarity_score"],
        })

    print(f"\n--- Summary ---")
    print(f"Correct: {correct_count}/{len(TEST_TICKETS)} ({100*correct_count/len(TEST_TICKETS):.0f}%)")
    print(f"Log written to: {args.log}")

    # Score distributions by expected domain - useful for threshold calibration
    in_domain_retrieval = [r["retrieval"] for r in results if r["expected"] == "Jira"]
    ood_retrieval = [r["retrieval"] for r in results if r["expected"] == "Out-of-Domain"]
    in_domain_ref = [r["reference"] for r in results if r["expected"] == "Jira"]
    ood_ref = [r["reference"] for r in results if r["expected"] == "Out-of-Domain"]

    print("\n--- Score distributions (for threshold calibration) ---")
    print(f"Retrieval score  | in-domain: min={min(in_domain_retrieval):.4f} max={max(in_domain_retrieval):.4f} | "
          f"out-of-domain: min={min(ood_retrieval):.4f} max={max(ood_retrieval):.4f}")
    print(f"Reference score  | in-domain: min={min(in_domain_ref):.4f} max={max(in_domain_ref):.4f} | "
          f"out-of-domain: min={min(ood_ref):.4f} max={max(ood_ref):.4f}")


if __name__ == "__main__":
    main()
