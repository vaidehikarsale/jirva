# JIRVA - Day 5 Manifest: BM25 + Hybrid Retrieval

**Date:** 2026-09-07

## What was built

- **BM25 keyword index** (`scripts/bm25_search.py`): built fresh in-memory from
  chunk JSON files on every run using the `rank-bm25` library (BM25Okapi).
  No persisted index file - avoids stale-index bugs, and rebuild cost is
  negligible at this collection size (~223-380 chunks depending on variant).
  Tokenization: lowercase, alphanumeric-only splitting.
- **Hybrid retrieval script** (`scripts/hybrid_search.py`): runs vector search
  (Qdrant, existing from Day 4) and BM25 search independently, each returning
  a configurable number of candidates (default 15), then merges the two
  ranked lists using **Reciprocal Rank Fusion (RRF)**.

## Why RRF over score-blending

BM25 scores (unbounded, e.g. 8-16 in testing) and cosine similarity scores
(0-1 range) are not on a comparable scale. Naive normalization-and-average
approaches are fragile and sensitive to normalization choices. RRF instead
uses only rank position in each list:

    score = 1/(k + rank_in_vector) + 1/(k + rank_in_bm25)   (k = 60, standard damping constant)

A chunk ranking well in either method gets a meaningful boost; a chunk
ranking well in both rises further. This is a standard, well-established
method for combining heterogeneous rankers, appropriate for this project's
scale without introducing score-calibration complexity.

## Validation process (important methodological note)

An initial "success" test used a query rephrased to include the literal
term "currentUser" - this was later identified as an unfair test, since it
essentially gave BM25 the answer. All findings below use the **original,
unmodified Day 4 query phrasing** for a fair before/after comparison. One
exception is noted: the Search category's underlying documents changed
between Day 4 and Day 5 (due to the Day 4 Server/DC source audit replacing
srch_002 with srch_009), so Query 6's comparison is not perfectly clean -
this is flagged explicitly in the results below.

## Results: hybrid retrieval vs. Day 4 vector-only baseline

| # | Query | Day 4 (vector-only) | Day 5 (hybrid) | Outcome |
|---|---|---|---|---|
| 1 | Why can't I move my issue to Done? | NO | **NO** (absent even at candidate-k=30 from both methods) | Not fixed - see limitation below |
| 4 | How do I set up a Kanban board? (regression check) | YES | **YES**, unaffected, slightly broader correct coverage | No regression |
| 6 | How do I write a JQL query to find issues assigned to me? | NO (buried) | **NO** with real phrasing (only "fixed" under an artificial keyword-heavy rewrite of the query, which was an invalid test) | Not fixed - see limitation below; comparison also affected by source replacement (srch_002 -> srch_009) between Day 4 and Day 5 |
| 7 | How do I add a custom field to my issue type? | NO (0/7 correct category) | **YES** - correct document (fld_005) now appears at rank 4 | Fixed by hybrid retrieval |
| 10 | How do I link a subtask to a parent issue? | PARTIAL/NO | **YES** - correct document (iss_004) now consistently appears at rank 4 | Fixed by hybrid retrieval |

**Score: 2 of 4 originally-flagged failures fixed (Queries 7, 10). 2 remain
unresolved (Queries 1, 6). No regressions on previously-working queries.**

## Key limitation identified (important for Day 11 evaluation)

Queries 1 and 6 share a common root cause distinct from the failures hybrid
retrieval was designed to fix: **vocabulary mismatch between colloquial user
phrasing and technical documentation language.**

- Query 1 ("move my issue to Done") vs. the actual relevant content (wf_004,
  which discusses "conditions," "transitions," "permissions" - never using
  the words "move" or "Done" literally). Confirmed absent from both vector
  search and BM25's candidate pools even at 30 candidates each.
- Query 6 similarly fails under natural phrasing because BM25 tokenizes to
  generic words ("write," "find," "assigned") that don't literally match
  the technical term "currentUser()" - BM25 only succeeded in an artificial
  test where the query contained the literal answer term.

**Why this matters for later roadmap stages:** reranking (a planned future
stage) operates only on candidates that already made it into the retrieval
pool - it cannot promote a document that neither vector search nor BM25
retrieved in the first place. This means Queries 1 and 6's failure mode is
**not fixable by reranking alone**. A genuine fix would require query
expansion/rewriting (e.g., translating "can't move to Done" into
"transition blocked condition" before searching) - a technique not
currently on the roadmap, and worth raising as a considered addition or a
documented limitation in the final evaluation and future-scope sections.

## Carried-forward findings still relevant for Day 11

From Day 4, still valid:
- Reference-table dilution (partially mitigated by hybrid for some cases,
  not query 1/6's root cause)
- Similarity-score gap as a domain-guard signal (out-of-domain query scored
  ~0.39-0.42 vs. 0.6-0.84 for in-domain queries) - unaffected by today's work,
  still a valid design input for Day 8

New from Day 5:
- Hybrid retrieval measurably improves lexical-confusion cases (Query 7) and
  under-ranked exact-title-match cases (Query 10)
- Hybrid retrieval does not address vocabulary-mismatch cases (Queries 1, 6)
  - this is a distinct failure category requiring a different fix
- No regressions observed on previously-working queries

## Recommendation for Day 11's fuller evaluation

Test the full 15-query set (not just the 5 spot-checked today) through
hybrid retrieval, across both chunk-size variants, to get complete coverage
data rather than the partial re-test done here. Also worth testing whether
increasing candidate-k universally (not just for diagnostic purposes)
changes outcomes, and whether the vocabulary-mismatch limitation affects
other untested queries beyond 1 and 6.
