# JIRVA - Day 6 Manifest: Reranking

**Date:** 2026-09-07

## What was built

- **Reranking script** (`scripts/rerank_search.py`): adds a cross-encoder
  reranking stage on top of Day 5's hybrid retrieval (vector + BM25 + RRF).
- **Reranker model:** `BAAI/bge-reranker-base`, run locally via
  sentence-transformers' `CrossEncoder` class (no new package install - part
  of the already-installed sentence-transformers library). Chosen for
  consistency with the BGE family already used for embeddings/tokenization,
  and because a larger reranker (bge-reranker-large) would be unjustified
  overhead at this collection's scale.
- **Pipeline:** Hybrid retrieval widens the candidate pool (default 25 per
  method) -> cross-encoder scores each (query, chunk) pair directly (unlike
  vector/BM25, which score query and chunk independently) -> top 5 returned.
- The script prints BEFORE (hybrid RRF top 5) and AFTER (post-rerank top 5)
  side by side for every query, to make direct comparison straightforward.

## Validation approach

Re-tested against queries already tracked across Day 4 (vector-only baseline)
and Day 5 (hybrid retrieval), rather than testing in isolation, to build a
complete three-stage comparison.

## Results: reranking vs. hybrid baseline

| Query | Day 4 (vector) | Day 5 (hybrid) | Day 6 (reranked) | Verdict |
|---|---|---|---|---|
| 1. Why can't I move my issue to Done? | NO | NO | NO - confirmed unfixable (wf_004 absent from candidate pool at k=30, both methods) | Reranking correctly reflects "nothing good found" - rerank scores dropped to 0.0008-0.0115, dramatically lower than genuine matches (0.9+), suggesting rerank confidence could serve as an insufficient-evidence signal in a later stage |
| 7. How do I add a custom field to my issue type? | NO (0/7 correct category) | YES (fld_005 at rank 4) | YES, improved further - fld_001 climbed from hybrid rank 5 to reranked rank 3 | Genuine partial improvement; correct content still not ranked #1 (incorrect iss_003 chunks still outscore it) |
| 10. How do I link a subtask to a parent issue? | PARTIAL/NO | YES (iss_004 at rank 4) | Unchanged rank (#4), but low relative confidence (0.78 vs 0.99 for incorrect neighbors) | No real improvement from reranking on this query |
| 13. How do I save a search as a filter? | YES, clean (best score of all 15 Day-4 queries) | YES, clean, all 5 results relevant | **REGRESSED** - two irrelevant results (fld_002 "Edit a custom field's options", srch_003 "JQL functions") entered the top 5, displacing genuinely relevant results | Real, demonstrated cost of reranking over a widened candidate pool |

## Key finding: reranking is not a strict improvement

Unlike the roadmap's implicit framing (reranker as a clear upgrade step),
empirical testing shows a mixed picture:
- Genuine improvements: 1 of 4 tracked queries (Query 7)
- No meaningful change: 2 of 4 (Queries 1, 10)
- Genuine regression: 1 of 4 (Query 13)

**Root cause of the Query 13 regression:** reranking operates over a WIDER
candidate pool (25 per method) than hybrid retrieval's own top-5 cut. This
width is deliberately necessary to let the reranker rescue genuinely relevant
but under-ranked chunks (as it did for Query 7's fld_001, originally buried
at vector rank 17). The same width that enables rescues also exposes the
reranker to noisier candidates it can occasionally score higher than it
should (e.g., fld_002 and srch_003 for Query 13, both scoring well above
where a human would place them, though still measurably lower than genuine
high-confidence matches: 0.55 and 0.30 vs 0.99+ for real matches).

## Decision: defer the fix, do not patch reranking today

Discussed three options (narrowing the candidate pool, adding a score
threshold gate, or deferring): decided to defer. Rationale, tied directly to
the project's own architecture (master prompt section 3, "Evidence/Grounding
Validation" and "Decision" as later, distinct pipeline stages): no single
retrieval-stage component is expected to be perfect standalone. The planned
Day 9 grounding-validation stage is architecturally the correct place to
catch exactly this kind of low-confidence noise - using a score-based
confidence check (an idea directly motivated by today's observation that
genuine matches scored 0.9+ while both Query 1's non-matches and Query 13's
intruding false positives scored meaningfully lower, 0.0008-0.55).

**No changes made to rerank_search.py's candidate pool size or score
thresholding today, per this decision.** This regression is intentionally
left visible and unpatched, to be addressed systematically (not query-by-
query) when the grounding-validation stage is built.

## Carried-forward findings for Day 9 (grounding validation) and Day 11 (evaluation)

- Rerank confidence scores show a wide, seemingly meaningful gap between
  genuine matches (roughly 0.6-0.99 observed) and non-matches/noise (roughly
  0.0008-0.55 observed) - worth testing formally as a confidence-threshold
  signal when building Day 9's insufficient-evidence safeguard.
- Reranking's value is real but narrower than assumed: it helps recover
  under-ranked-but-relevant content (Query 7) but does not reliably improve
  already-adequate results and can introduce new noise (Query 13).
- Query 1's failure remains the clearest evidence that some queries need a
  fundamentally different fix (query rewriting/expansion) that is outside
  the current retrieval + reranking architecture entirely - not addressed
  today, carried forward as a documented limitation.

## Full pipeline status

Hybrid Retrieval -> Reranking -> Top-K evidence is now functionally complete,
per the Day 6 roadmap deliverable. Known limitations are documented above
rather than silently patched, to be addressed by the grounding-validation
and evaluation stages later in the roadmap.
