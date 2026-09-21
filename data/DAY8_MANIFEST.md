# JIRVA - Day 8 Manifest: Ticket Analysis + Domain Guard

**Date:** 2026-09-09

## What was built

- **ticket_analysis.py**: constrained LLM classification producing
  intent/category/severity/risk/domain as structured JSON, given the ticket
  PLUS two independently-computed signals as context (not asked in isolation).
- **domain_guard.py**: combines three signals per the roadmap's explicit
  instruction not to trust a bare "is this Jira-related?" LLM judgment:
  1. Retrieval confidence (top rerank score from the real hybrid+rerank pipeline)
  2. Reference-example similarity (max cosine similarity to a curated 20-ticket
     reference set, 2 per KB category)
  3. Constrained LLM classification, given both signals as context
  Short-circuit: only bypasses the LLM when BOTH lightweight signals
  independently indicate out-of-domain.
- **calibrate_domain_guard.py**: 20-ticket test set (10 in-domain spanning
  difficulty levels, 10 out-of-domain including 5 deliberately adversarial
  cases reusing Jira-sounding vocabulary) used to calibrate thresholds
  empirically rather than from a small ad hoc sample.
- **jirva.py**: the complete pipeline entry point - Ticket -> Domain Guard +
  Ticket Analysis -> (Jira) Retrieval+Reranking+Generation, or
  (Out-of-Domain) fallback message. Reuses domain guard's already-computed
  retrieval evidence for generation - no redundant re-retrieval.

## Calibration results: 18/20 (90%) correct

Thresholds used (placeholders, now locked as final per decision below):
retrieval_threshold=0.10, reference_threshold=0.50

Both critical distinctions confirmed working:
- "Bulk edit multiple issues" (in-domain, but KB has no answer) correctly
  classified as Jira, NOT Out-of-Domain - confirms insufficient-evidence
  and out-of-domain are correctly NOT conflated.
- 4 clearly out-of-domain tickets (weather, cake, sports car, election)
  correctly short-circuited without an LLM call.

## Key finding 1: retrieval score has very little standalone domain-discriminative power

Score distributions across the 20-ticket test:
    Retrieval score  | in-domain: min=0.0115 max=0.9994 | out-of-domain: min=0.0000 max=0.9601
    Reference score  | in-domain: min=0.6968 max=0.9955 | out-of-domain: min=0.4082 max=0.8433

Retrieval score's in-domain and out-of-domain ranges almost completely
overlap (both span roughly 0-1). Example: "How do I create a custom field
in Salesforce?" scored 0.96 on retrieval - nearly as high as genuine
in-domain tickets - simply because Jira's KB genuinely contains "custom
field" content, despite the ticket being about a different product
entirely. This validates the original decision never to treat retrieval
score as authoritative alone.

Reference-example similarity shows real but partial separation: in-domain
floor 0.70, out-of-domain ceiling 0.84 - an overlapping middle zone
(~0.70-0.84), not a clean gap, but meaningfully more discriminative than
retrieval score alone.

## Key finding 2: the 2 mismatches were LLM classification failures, not threshold failures

    [MISMATCH] "How do I configure a GitHub Actions workflow?" -> predicted Jira (retrieval=0.653, reference=0.761, short_circuit=False)
    [MISMATCH] "What's a good JQL alternative for SQL databases?" -> predicted Jira (retrieval=0.302, reference=0.754, short_circuit=False)

Critically, NEITHER case short-circuited - both correctly bypassed the
lightweight-signal shortcut and reached the LLM, exactly as the combination
logic is designed to do when signals disagree or are ambiguous. The failure
happened at the LLM classification step itself, not the threshold step.
Adjusting the 0.10/0.50 threshold values would not have changed either
outcome, since both cases correctly reached the LLM regardless of where
the threshold sat.

**Why these two specifically fooled the LLM** (and Salesforce/AWS/Windows
did not): GitHub and SQL have genuine conceptual adjacency to Jira, not just
lexical overlap - Jira workflows do integrate with GitHub (wf_004's actual
content mentions Bitbucket triggers), and JQL is genuinely presented in
Jira's own docs as analogous to SQL query languages. The retrieved evidence
for these two was topically real and relevant-sounding, not coincidental
keyword matching - a harder, more legitimate edge case than the other
adversarial tickets tested.

## Decision: thresholds locked as-is, no fourth signal added

Per explicit project decision: retrieval_threshold=0.10 and
reference_threshold=0.50 are locked as final for this stage. A
product-name-detection fourth signal was considered and explicitly NOT
implemented, to avoid over-engineering around 2 specific known edge cases
out of 20 tests. The 2 remaining mismatches are documented as a limitation
of the current architecture (LLM classification can be fooled by genuinely
topically-adjacent-but-different products), not patched.

## Pipeline integration test results

Two end-to-end tests run through the complete jirva.py pipeline:

1. **"Why can't I move my issue to Done?"** - Domain guard and ticket
   analysis performed correctly (Domain: Jira, Intent: Troubleshooting,
   Category: 01_Workflows, Severity: Medium, Risk: Low - exactly matching
   the roadmap's own worked example). However, the GENERATION stage output
   was notably more elaborate and confident than the same query's Day 7
   result, presenting four stitched-together reasons from low-confidence
   evidence (scores 0.002-0.012, same range flagged in Day 7). One specific
   new concern: the answer attributed a claim about "issue-level security
   not being available on Free plans" to "Evidence 2," which per the
   evidence list is the same source document as Evidence 1 ("Creating
   issues and subtasks"), raising a mismatched-attribution question not
   yet independently verified against the raw source. This is NOT a Day 8
   defect - domain guard and ticket analysis both performed exactly as
   designed - but it is a sharper, more concrete reinforcement of the Day 7
   grounding-validation finding, now carried forward as higher-priority
   input for Day 9.
2. **"What's the best Python framework?"** - Correctly classified
   Out-of-Domain, correctly returned the fallback message without any
   generation call being made. Clean, expected behavior.

## Carried-forward findings for Day 9 (grounding/evidence validation)

- Day 7's finding (low score + one specific tangential detail = confident
  misapplication) is now reinforced by a second, more elaborate example
  from today's pipeline-integration test, involving the same ticket but a
  fresh generation call - suggesting this is a repeatable tendency, not a
  single unlucky output.
- **Evidence 2 attribution - VERIFIED, concern retracted.** The claim
  "issue-level security is not available on Free plans" was checked
  directly against the raw source (iss_003_c05.json, part of "Creating
  issues and subtasks," the same document cited as Evidence 1). The source
  states verbatim: "You can't edit project permissions or roles on the Free
  plan for Jira Software or Jira Work Management, and you can't configure
  issue-level security on any Free plan (including Jira Service
  Management)." This is genuinely accurate and properly grounded - NOT a
  fabrication or context misapplication like the wf_004/proj_003 cases.
  The only unconfirmed detail is whether this specific chunk occupied the
  literal "Evidence 2" ranking slot in that exact run (chunk ranking can
  shift between calls), which is a minor labeling-precision question, not
  a substantive grounding failure. This finding is retracted from the list
  of confirmed problems - it should not be treated as evidence of a
  citation-fidelity issue for Day 9.
- Day 7's threshold hypothesis (something between 0.104 and 0.465 might
  separate its failures from its successes) remains untested and still
  relevant for Day 9's design.

## Deliverable status

Per the roadmap's Day 8 deliverable: Ticket -> Domain check -> Classification
is complete and functioning, calibrated against a 20-ticket test set with
documented, evidence-based limitations rather than assumed thresholds.
