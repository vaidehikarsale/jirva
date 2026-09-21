# JIRVA - Day 4 Manifest: Embeddings + Vector Database + Query Evaluation

**Date:** 2026-09-07

## Embedding setup

- **Model:** BAAI/bge-small-en-v1.5, run locally via sentence-transformers (free, no API cost)
- **Vector size:** 384 dimensions, cosine distance
- **Query embedding:** uses BGE's recommended asymmetric-retrieval instruction prefix
  ("Represent this sentence for searching relevant passages: ") - passages embedded as-is
- **Vector database:** Qdrant Cloud (free tier)
- **Collections:** two, to support a real chunk-size comparison rather than an assumption
  - jirva_400 (400-token chunk variant): 223 chunks embedded
  - jirva_600 (600-token chunk variant): 156 chunks embedded

## Source quality audit (triggered by query testing findings)

During manual query testing, two Server/Data-Center-flavored sources were noticed
in result sets. This triggered a full audit rather than a one-off fix:

- Upgraded scripts/check_platform_scope.py to detect Server/DC Confluence URL
  patterns (e.g. "server", "/datacenter/", "data-center" in the URL), not just
  in-content platform-notice banners (which is all it checked as of Day 3).
- Built a new reusable tool, scripts/remove_document.py, which cleanly removes
  a document from data/documents, both chunk variants, and both Qdrant
  collections by document_id in one step.

**Documents removed and replaced (Server/DC URL pattern, not Cloud-accurate):**
| Old document | Old URL pattern | Cloud replacement |
|---|---|---|
| iss_001 - Associating issue types with projects | confluence.../ADMINJIRASERVER/... | Associate work types with spaces (jira-cloud-administration) |
| srch_002 - Advanced searching fields reference | confluence.../JIRASOFTWARESERVER/... | JQL fields reference (jira-service-desk-cloud) |
| jsm_006 - Service Level Agreements overview | confluence.../servicemanagementserver.../... | (see below - required a second pass) |

**Second-pass catch:** the first SLA replacement (jsm_009, "Create service level
agreements SLAs to manage goals") passed the Cloud-URL check but turned out to be
a link-hub page with only 2 generic sentences of actual body content (same failure
mode as ts_001 on Day 3, caught here despite passing the platform-scope check,
since that check only screens for wrong-platform content, not thin/hub content).
Removed and replaced again with jsm_010 ("Set up service level agreement SLA
goals"), verified to contain genuine step-by-step instructions.

**Final state:** 57 documents (unchanged count from end of Day 3, since each
removal was matched by a verified replacement).

## Manual query evaluation (15 queries, both chunk-size variants)

| # | Query | jirva_400 | jirva_600 | Finding |
|---|---|---|---|---|
| 1 | Why can't I move my issue to Done? | NO | NO | Relevant content (wf_004) buried under a dense condition-name reference table |
| 2 | How do I create a permission scheme for a new project? | YES | YES | Strong match, high confidence (0.78) |
| 3 | Why can't I see a project in my Jira site? | NO (relevant at #2) | PARTIAL | Same table-dilution pattern; noise chunk also appeared |
| 4 | How do I set up a Kanban board? | YES | YES | Clean match, high confidence (0.81) |
| 5 | Difference between team-managed and company-managed projects? | YES | YES | Clean match, identical top-3 both variants |
| 6 | How do I write a JQL query to find issues assigned to me? | NO (buried) | NO (buried) | currentUser() exists in KB but buried in srch_003 among unrelated function definitions - confirmed retrieval issue, not content gap (initial "gap" call was corrected after checking) |
| 7 | How do I add a custom field to my issue type? | NO (0/7 from correct category) | NO (relevant doc at rank 7 only) | Lexical confusion: "issue type" overlaps between issue-type-schemes (03_Issues) and custom fields (05_Fields); 600-token variant meaningfully outperformed 400 here |
| 8 | Why am I not receiving email notifications for issue updates? | YES | YES | Excellent match, specific and actionable |
| 9 | What is a queue in Jira Service Management? | YES | YES | Clean, high-confidence match |
| 10 | How do I link a subtask to a parent issue? | PARTIAL | NO (correct doc at #3) | Exact-title-match document under-ranked in both, worse in 600 |
| 11 | How do I configure an SLA for support requests? | YES (source later flagged/replaced) | YES (source later flagged/replaced) | Triggered the source-quality audit described above |
| 12 | Why does my browser show a blank Jira page? | YES | NO | 400-token variant clearly outperformed 600 here |
| 13 | How do I save a search as a filter? | YES | YES | Best confidence score of all queries (0.84), identical results |
| 14 | What's the fastest sports car in the world? (deliberately out-of-domain) | N/A (correctly low-relevance) | N/A (correctly low-relevance) | Scores dropped to ~0.39-0.42 vs 0.6-0.84 for in-domain queries - a usable signal for a future similarity-threshold-based domain guard |
| 15 | How do I bulk edit multiple issues at once? | NO | NO | Likely genuine content gap - no document covers multi-select/bulk operations |

**Score summary (excluding the deliberate out-of-domain query):** jirva_400: 7/14
clearly relevant top-1 results (50%). jirva_600: 6/14 (43%). Neither variant
dominates - 400 won outright once (Q12), 600 won outright once (Q7); most
failures affected both variants equally, meaning the failure mode is usually
about ranking/content, not chunk size specifically.

## Key findings for later pipeline stages

1. **Reference-table dilution** (Queries 1, 3, 6): chunks containing dense
   enumerated tables (condition lists, JQL function catalogs) produce embeddings
   that under-represent any single relevant sentence buried inside them. This is
   the single most common failure mode observed today. Directly motivates hybrid
   retrieval (BM25 keyword matching would likely catch these via literal term
   overlap) and reranking (a cross-encoder reading full query+chunk pairs) -
   both already planned on the roadmap, not new work.

2. **Lexical/semantic confusion between similarly-worded concepts** (Query 7,
   partially 10): vector search sometimes matches surface phrase overlap
   ("issue type") over actual intent (issue type schemes vs. custom fields).
   Reranking is the most direct planned fix.

3. **Similarity-score gap as a domain-guard signal** (Query 14): in-domain
   queries scored 0.6-0.84; the deliberately out-of-domain query scored
   0.39-0.42. This gives a concrete, evidence-based starting point for a
   similarity-threshold heuristic in the Day 8 domain guard, rather than
   guessing at a cutoff.

4. **Genuine content gaps exist** (Query 15, bulk editing; possibly others
   not yet tested): distinct from ranking failures, these need either a
   targeted source addition or an honest documented limitation - not a
   retrieval-pipeline fix.

## Known limitations carried forward

- No document in the collection appears to cover bulk/multi-select issue
  operations (Query 15).
- 10_Troubleshooting remains thin (2 documents, per Day 3), unchanged today.
- The chunk-size question (400 vs 600) remains genuinely open - today's small
  manual sample (14 in-domain queries) shows a near-even split, not a clear
  winner. A decision should wait for Day 11's fuller, more rigorous evaluation
  rather than being locked in now based on this sample.
