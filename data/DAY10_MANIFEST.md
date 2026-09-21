# JIRVA - Day 10 Manifest: LangGraph + Complete Backend

**Date:** 2026-09-11

## What was built

- **langgraph_flow.py**: LangGraph orchestration wrapping the existing
  pipeline. New dependency: `langgraph` (free, open source).
- **api.py**: FastAPI backend exposing the pipeline over HTTP. New
  dependencies: `fastapi`, `uvicorn` (both free, open source).
- **test_analyze.py / test_resolve.py / test_upload.py**: standalone
  verification scripts for each endpoint, written as `.py` files rather
  than inline shell one-liners after PowerShell's quote-escaping repeatedly
  broke on ticket text containing apostrophes/nested quotes.

Per the roadmap's Day 10 framing, this was explicitly an **orchestration and
backend integration task, not new AI logic** - every node and endpoint
calls a function already built and verified in Days 7-9. No new LLM calls,
no new decision logic, no new grounding-validation component were added
today.

## Design decisions: reconciling the roadmap's diagram with what's actually built

The roadmap's LangGraph diagram (`Ticket Analysis -> Domain Check -> Risk
Assessment -> Retrieve -> Rerank -> Generate -> Validate -> Decision ->
Resolve/Guide/Escalate`) does not literally match the existing codebase in
three ways. Per explicit project decision, resolved as follows rather than
built literally node-for-node:

1. **Domain Check + Risk Assessment are ONE node, not two.**
   `ticket_analysis.py`'s `analyze_ticket()` already returns
   category/risk/domain from a single LLM call (established Day 8).
   Splitting this into two graph nodes would either be cosmetic (same call,
   relabeled) or would silently add a second LLM call - neither authorized.
2. **Retrieve/Rerank are not separate nodes.** `check_domain()` already runs
   the real hybrid+rerank pipeline internally to compute its retrieval-
   confidence signal (established Day 8), and the pipeline has always reused
   that same evidence for generation rather than re-retrieving (established
   Day 9). Building literal separate Retrieve/Rerank nodes downstream would
   mean a real redundant second retrieval call - out of scope today.
3. **Decision runs BEFORE Generate, not after**, preserving Day 9's actual
   calibrated control flow (FALLBACK/ESCALATE skip generation entirely).
   The roadmap's Generate-then-Validate-then-Decision order was treated as
   a diagram simplification, not an instruction to reverse Day 9's logic.
   There is no separate "Validate" node - nothing in Days 1-9 implements a
   distinct grounding-validation step (Day 7 identified this gap and
   explicitly deferred it; it remains unimplemented as of Day 10).

**Actual graph shape built:**
```
START -> ticket_analysis -> (out_of_domain | decision)
decision -> (fallback | escalate | generate) -> END
```

## FastAPI endpoint design

The roadmap listed four endpoints as an example ("you don't need 25
endpoints, keep it simple") without specifying request/response contracts,
so the following was designed and confirmed before building:

| Endpoint | Behavior | Generation? | Persisted? |
|---|---|---|---|
| `POST /ticket/analyze` | Calls `check_domain()` + `decide()` directly (NOT via the graph) - classification only | No | No |
| `POST /ticket/resolve` | Full LangGraph app invocation | Yes, if RESOLVE/GUIDE | No |
| `POST /ticket/upload` | Takes `title` + `description`, runs full pipeline, assigns a `ticket_id`, stores result | Yes, if RESOLVE/GUIDE | Yes (in-memory dict) |
| `GET /ticket/{id}` | Retrieves a previously uploaded ticket's stored result | No | Reads storage |

`/ticket/analyze` deliberately bypasses the graph rather than calling the
full pipeline and hiding the answer, to avoid wasting a Nemotron call on
callers who only want classification.

**Storage is an in-memory Python dict, not a database.** Uploaded tickets
are lost on server restart. This is an accepted limitation for today's MVP
scope, consistent with the roadmap's explicit "keep it simple" instruction
and its list of things not to build yet (a real DB was never in scope).

**Image upload is explicitly out of scope today** - `/ticket/upload`
accepts text fields only. Image handling is Day 12's multimodal work.

**CORS is wide open** (`allow_origins=["*"]`) for local development with
the upcoming Day 11 React frontend. Flagged as an intentional placeholder -
Day 14's own checklist lists CORS as something to check before deployment.

## One incidental fix made during Task 4

`evidence_used`'s `score` field could be a `numpy.float32` (from the
reranker), which prints fine in a CLI but is not JSON-serializable and
would crash any HTTP response returning it. Cast to native `float` in
`langgraph_flow.py`'s `decision_node`. This is a type-safety fix, not a
logic change - the value itself is unchanged, only its Python type.

## Task-by-task verification results

**Task 2 (build the graph):** Confirmed via `python langgraph_flow.py`
on `wf_004` - reproduced Day 9's exact result (`evidence_confidence=0.0115`,
`OUTCOME: FALLBACK`, correct fixed message, no generation attempted).
First attempt failed on OpenRouter's daily free-tier rate limit (50
requests/day - already exhausted from Day 9's testing); confirmed working
after the daily reset.

**Task 3 (pilot test vs. known outcomes):** Confirmed on the remaining two
known cases:
- `proj_003` ("14 days" ticket): `evidence_confidence=0.104`, `OUTCOME:
  GUIDE`, matching Day 9. Category classified as `03_Issues` this run
  (vs. `06_Search`/`07_Boards`/`04_Projects` in various prior runs of the
  identical ticket) - consistent with the already-documented Day 9 finding
  on `ticket_analysis.py` classification instability, not a new issue. The
  GUIDE answer again conflated "Kanban-style" with "team-managed" when
  describing the 14-day clearing rule's condition - the same residual
  scope-narrowing finding from Day 9, carried over faithfully by the graph
  rewiring rather than masked or newly introduced.
- Known-good ("save search as filter"): `evidence_confidence=0.9999`,
  `OUTCOME: RESOLVE`, identical evidence and answer quality to every prior
  run.

**Task 4 (FastAPI backend):** Server startup confirmed clean (model
loading, BM25 index, reference embeddings, graph build, all completed
without error). Health check (`GET /`) confirmed the app serves requests
independent of the pipeline.

**Task 5 (endpoint tests):**
- `POST /ticket/analyze` on `wf_004`: exact match to expected values
  (`category=01_Workflows`, `evidence_confidence≈0.0115`,
  `outcome=FALLBACK`).
- `POST /ticket/resolve` on the known-good ticket: exact match
  (`outcome=RESOLVE`, `evidence_confidence≈0.9999`, correct evidence order,
  clean cited answer). Confirmed the numpy-to-float fix works correctly
  through an actual HTTP response.
- `POST /ticket/upload` + `GET /ticket/{id}`: persistence confirmed working
  correctly on both attempts (GET returned byte-for-byte the same object
  upload produced, `ticket_id` round-tripped correctly). Generation failed
  on the FIRST attempt - see finding below - and succeeded cleanly on
  an immediate retry with identical input.

## Key finding: degenerate LLM output is not caught by any existing safeguard

On the first `/ticket/upload` test, Nemotron's generation call returned
degenerate output - repeated punctuation and a long run of `<unk>` tokens,
not a real answer - while every other part of the pipeline (retrieval,
evidence scores, `ticket_analysis`, decision routing to RESOLVE) behaved
completely normally. An immediate retry with identical input produced a
normal, correctly-cited answer. This points to a transient failure on the
free-tier Nemotron endpoint itself, not a bug in any code built this
project.

**This is a genuine residual reliability gap, not investigated or patched
today, per Day 10's explicit "orchestration only" scope:** the decision to
RESOLVE is made in `decision_engine.py` BEFORE generation happens, based
purely on evidence confidence/risk/category-alignment. Nothing in the
current pipeline checks whether the generation call actually succeeded
before returning `outcome: RESOLVE` to the caller. A user could receive a
response that says "RESOLVE" (implying a confident, trustworthy answer)
paired with literal garbage text. Candidate future mitigations (not
implemented or evaluated): a basic sanity check on generated output (e.g.
minimum length, absence of repeated-token degeneration patterns) before
returning a RESOLVE/GUIDE response, or a retry-on-garbage-output policy
similar to `openrouter_client.py`'s existing retry-on-transient-error logic.

## Deliverable status

Per the roadmap's Day 10 hard MVP deadline: submitting a ticket and getting
Ticket -> JIRVA -> Analysis -> Retrieval -> RAG -> Guardrails -> Decision
is confirmed working end-to-end, both via direct LangGraph invocation and
via all four FastAPI endpoints. All four endpoints individually tested
against known-correct values. Two residual findings carried forward from
Day 9 confirmed to persist faithfully through the new orchestration layer
(not newly introduced, not fixed). One new residual finding recorded
(degenerate generation output, uncaught by any current safeguard) -
documented, not patched, consistent with today's explicit scope.
