"""
JIRVA - Decision Engine Calibration Test Set (Day 9, Task 5)
----------------------------------------------------------------
Runs a curated set of tickets through the full domain guard + decision
engine and logs full signal scores for each, specifically to calibrate the
two placeholder thresholds (fallback_threshold, resolve_threshold)
empirically - same approach as Day 8's calibrate_domain_guard.py: run the
real pipeline, log everything, report min/max score distributions per
expected outcome so thresholds can be read off real data rather than
invented or swept automatically.

Test set composition (per explicit project decision):
  - 5 "anchor" tickets: real cases already hand-graded in Day 7/8, reused
    here as fixed reference points. Their expected_outcome, ticket_category,
    and risk are NOT hard-coded from memory - every signal is pulled live
    from check_domain()/decide() on each run, so a stale assumption can
    never silently contaminate calibration.
  - 9 new tickets targeting the ambiguous 0.10-0.50 confidence range
    (plus one aimed at a High-risk/ESCALATE regression check). These start
    with expected_outcome=None ("TBD") - correctness can't be hand-labeled
    until the actual retrieved evidence has been reviewed, unlike Day 8's
    in/out-of-domain calls which were usually obvious upfront. For TBD
    tickets, this script prints the full evidence block (title, score,
    content) instead of scoring correctness, so a human can label it from
    real evidence, not from the ticket text alone.

ESCALATE is excluded from the confidence-distribution stats (it's driven
by the fixed risk=="High" rule, not a threshold) but is still tracked as a
correctness check for any ticket expected to escalate.

Day 9 Task 6 update: testing a candidate resolve_threshold of 0.65 (up from
the 0.50 placeholder), per data read from the first calibration run - GUIDE's
confirmed max was 0.5731, above the old 0.50 threshold. This is passed
explicitly to decide() below; decision_engine.py's own default is untouched,
so this script is testing a candidate value, not silently changing the
system's behavior elsewhere. fallback_threshold stays at 0.05, unchanged -
the data supported it as-is.

Also added two ESCALATE anchors (former-employee access revocation, permanent
project deletion). Both were initially ambiguous - risk/category classification
proved unstable across repeated runs for these two tickets specifically (see
Day 9 manifest for the full finding) - but across 5 total observations each,
both settled on risk="High" in the majority of runs, and ESCALATE is the
correct target outcome for both on safety grounds regardless. The
known_failure flag/reporting path remains in this script as reusable
infrastructure but has no active entries as of this test set version.

Usage:
    python calibrate_decision_engine.py --chunks-dir ../data/chunks/400_variant --collection jirva_400 --log ../logs/decision_engine_calibration.csv
"""

import argparse
import csv
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer, CrossEncoder

from bm25_search import build_bm25_index
from domain_guard import build_reference_embeddings, check_domain
from decision_engine import decide, RESOLVE, GUIDE, ESCALATE, FALLBACK

EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"
RERANK_MODEL_NAME = "BAAI/bge-reranker-base"

# Day 9 Task 6: DEFAULT_RESOLVE_THRESHOLD is now locked at 0.65 in
# decision_engine.py itself (was tested here as a candidate override in the
# prior run; now confirmed and locked). This script no longer passes explicit
# threshold overrides to decide() - it validates the actual production
# defaults, not a script-local candidate value.

# expected_outcome: "RESOLVE" | "GUIDE" | "ESCALATE" | "FALLBACK" | None (TBD - not yet hand-labeled)
TEST_TICKETS = [
    # --- Anchors: real, previously-graded Day 7/8 cases ---
    ("Why can't I move my issue to Done?", "FALLBACK", False),                    # wf_004, Day 7 top score 0.012
    ("Why does Jira only show data from the last 14 days?", "GUIDE", False),      # proj_003, Day 7 top score 0.104
    # NOTE: Day 7 originally recorded this as "state insufficient evidence" under
    # the old binary refuse/answer model, which mapped to FALLBACK in an earlier
    # version of this test set. Re-derived under the actual four-outcome schema:
    # confidence 0.4655 with category-aligned evidence is "present but not strong
    # enough for a definitive answer" - that's what GUIDE exists for. FALLBACK
    # should mean "essentially no relevant evidence," not "imperfect evidence."
    ("How do I bulk edit multiple issues at once?", "GUIDE", False),              # Day 7 Test 2, top score 0.465 - corrected label, see note above
    ("What is a queue in Jira Service Management?", "RESOLVE", False),            # Day 7 Test 1, top score 0.893
    ("Can you create a new permission scheme for my project?", "RESOLVE", False), # Day 7 Test 3, top score 0.983

    # --- New: targeting the ambiguous 0.10-0.50 confidence range, hand-labeled
    # from actual retrieved evidence after the first calibration run ---
    ("Why don't I get email notifications when someone comments on my issue?", "GUIDE", False),
    ("How do I search for issues by a custom field's value?", "RESOLVE", False),
    ("Can I move an issue between two different boards?", "FALLBACK", False),
    ("Why did the priority field disappear after I changed the issue type?", "GUIDE", False),   # borderline - thin but non-zero relevant evidence
    ("What happens to my saved filters if I leave the project?", "GUIDE", False),
    ("Why can't I see the Epic field on my issue screen?", "FALLBACK", False),
    # Validates category_alignment as a necessary signal, not a redundant one:
    # top-scoring evidence (0.5731, above resolve_threshold) is the wrong document
    # (subtask creation, 03_Issues); the actually-relevant workflow-transition
    # content scores far lower (0.0282/0.0142) but is present in the top-5.
    # Without category_alignment, confidence alone would wrongly RESOLVE here.
    ("How do I restrict who can transition an issue to Done?", "GUIDE", False),
    ("How do I link an epic to issues in a different project?", "GUIDE", False),  # low-confidence label - evidence never squarely answers the question asked

    # --- ESCALATE anchors, both confirmed across 5 total observations each
    # (calibration v1, calibration v2, plus 3 fresh standalone domain_guard.py
    # runs). risk landed on "High" in the majority of runs for both tickets;
    # ESCALATE is the correct target outcome for both, not FALLBACK - these are
    # sensitive, irreversible/security-relevant admin actions where routing to
    # a human with a clear reason is the right behavior, not a generic
    # insufficient-evidence message. See Day 9 manifest for the full
    # risk/category instability finding across all 5 runs per ticket. ---
    ("A former employee still has access to all our projects. How do I revoke that access immediately?", "ESCALATE", False),

    # NOTE: this ticket's category also drifted between invocation contexts -
    # "03_Issues" in both calibration-script runs, "04_Projects" in all 3
    # standalone domain_guard.py runs - but risk landed on "High" in all 3 of
    # the standalone runs, correctly producing ESCALATE regardless of the
    # category drift (ESCALATE is risk-driven, not category-driven). Recorded
    # as a residual reliability finding in the Day 9 manifest, not patched.
    ("How do I permanently delete a project and all its issues?", "ESCALATE", False),
]


def log_row(log_path, row):
    file_exists = os.path.isfile(log_path)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "timestamp", "ticket", "expected_outcome", "evidence_confidence",
                "risk", "ticket_category", "top_evidence_category", "category_aligned",
                "predicted_outcome", "correct", "decision_reason",
            ])
        writer.writerow(row)


def print_evidence_for_labeling(ticket, reranked):
    """For TBD tickets: print full evidence so the outcome can be hand-labeled
    from what was actually retrieved, not guessed from the ticket text alone."""
    print(f"    [TBD - review evidence below and assign an expected_outcome]")
    if not reranked:
        print("    (no evidence retrieved)")
        return
    for i, (chunk, score, vec_rank, bm25_rank) in enumerate(reranked, start=1):
        content_preview = chunk["content"][:300].replace("\n", " ")
        print(f"    [{i}] score={score:.4f} | category={chunk['category']} | {chunk['document_title']}")
        print(f"        {content_preview}...")


def main():
    parser = argparse.ArgumentParser(description="Decision engine calibration test set")
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

    print(f"\nRunning {len(TEST_TICKETS)} test tickets through domain guard + decision engine")
    print("Using decision_engine.py's actual DEFAULT_FALLBACK_THRESHOLD / "
          "DEFAULT_RESOLVE_THRESHOLD (no overrides passed) - this run validates "
          "the locked-in production thresholds.\n")

    correct_count = 0
    scored_count = 0        # excludes TBD rows and known-failure rows
    known_failure_count = 0
    results = []  # for distribution stats, excludes TBD, ESCALATE, and known-failure rows

    for entry in TEST_TICKETS:
        ticket, expected, known_failure = entry

        guard_result = check_domain(
            ticket, qdrant_client, embed_model, cross_encoder, bm25, chunks,
            ref_texts, ref_embeddings, args.collection,
        )

        if guard_result["domain"] == "Out-of-Domain":
            # Should not happen for this curated set, but don't silently skip -
            # log it plainly so a genuinely mis-designed test ticket is visible.
            print(f"[OUT-OF-DOMAIN] \"{ticket[:60]}\" - unexpected for this test set, check the ticket wording")
            log_row(args.log, [
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ticket, expected, "", "", "", "", "", "Out-of-Domain", "", "domain guard short-circuited",
            ])
            continue

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
        predicted = decision["outcome"]

        print(f"\nTicket: \"{ticket}\"")
        print(f"    evidence_confidence={evidence_confidence:.4f} | risk={ta['risk']} | "
              f"ticket_category={ta['category']} | top_evidence_category={top_evidence_category} | "
              f"category_aligned={decision['category_aligned']}")
        print(f"    predicted_outcome={predicted}")

        if expected is None:
            print_evidence_for_labeling(ticket, reranked)
            is_correct = ""  # not scored yet
        elif known_failure:
            # Tracked deliberately, not counted as a pass/fail case and not folded
            # into the distribution stats - this is a documented limitation, not
            # a calibration data point.
            is_correct = (predicted == expected)
            known_failure_count += 1
            status = "MATCHES KNOWN LIMITATION (still fails)" if not is_correct else "NO LONGER FAILS - re-examine why"
            print(f"    [KNOWN FAILURE] expected={expected} | {status}")
        else:
            is_correct = (predicted == expected)
            scored_count += 1
            correct_count += int(is_correct)
            status = "OK" if is_correct else "MISMATCH"
            print(f"    [{status}] expected={expected}")

            # ESCALATE excluded from confidence-distribution stats (fixed rule, not threshold-driven)
            if expected != ESCALATE:
                results.append({"expected": expected, "evidence_confidence": evidence_confidence})

        log_row(args.log, [
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ticket, expected if expected else "TBD", evidence_confidence, ta["risk"],
            ta["category"], top_evidence_category, decision["category_aligned"],
            predicted, is_correct, decision["reason"],
        ])

    print(f"\n--- Summary ---")
    if scored_count:
        print(f"Correct: {correct_count}/{scored_count} scored cases ({100*correct_count/scored_count:.0f}%)")
    print(f"Known-failure cases (tracked separately, not in scored total): {known_failure_count}")
    print(f"TBD (needs hand-labeling from printed evidence above): "
          f"{len(TEST_TICKETS) - scored_count - known_failure_count}")
    print(f"Log written to: {args.log}")

    if results:
        print("\n--- evidence_confidence distribution by expected outcome (for threshold calibration) ---")
        for outcome in (FALLBACK, GUIDE, RESOLVE):
            vals = [r["evidence_confidence"] for r in results if r["expected"] == outcome]
            if vals:
                print(f"{outcome:9s} | n={len(vals):2d} | min={min(vals):.4f} | max={max(vals):.4f}")
            else:
                print(f"{outcome:9s} | n=0 (no scored cases yet)")


if __name__ == "__main__":
    main()
