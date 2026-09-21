# JIRVA - Day 7 Manifest: RAG Generation (First Functional Milestone)

**Date:** 2026-09-08

## What was built

- **openrouter_client.py**: thin wrapper around OpenRouter's chat completions
  endpoint, calling `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`
  (verified free tier, $0 cost, 256K context). Includes automatic retry with
  backoff for transient upstream capacity errors (observed during testing:
  "Worker local total request limit reached" - a known free-tier limitation,
  not a bug in JIRVA's code).
- **rag_answer.py**: the complete pipeline - Ticket -> Hybrid Retrieval ->
  Reranker -> Top-K Evidence (with rerank scores labeled) -> Nemotron ->
  Answer + Sources. Ties together every component built Days 4-7.

## System prompt design

Six rules encoded per the roadmap's requirements: evidence-only grounding,
explicit insufficiency-flagging, numbered troubleshooting steps, source
citation, no action-claims (JIRVA cannot perform Jira actions), and
out-of-domain deflection. Evidence is passed to the model with its rerank
confidence score labeled alongside each chunk, as an additional signal -
per explicit decision, NOT as a hard threshold or calibrated confidence
value. No score cutoff was introduced at this stage.

## Test results

| # | Ticket | Evidence scores (top-5) | Expected behavior | Actual behavior | Verdict |
|---|---|---|---|---|---|
| Pilot | How do I save a search as a filter? | 1.000, 0.605, 0.548, 0.369, 0.302 | Clear answer, cite sources | Correct, clean answer; appears to have self-filtered 2 known-irrelevant chunks (the Day 6 Query 13 regression chunks) without a hard threshold | Correct |
| Pilot | Why can't I move my issue to Done? | 0.012, 0.006, 0.002, 0.002, 0.001 | State insufficient evidence | **Did not refuse.** Built a confident, specific answer by misapplying one real but tangential detail (an illustrative "Approved status" example from a workflow-building tutorial in wf_003) as if it were general diagnostic guidance. Not fabrication - the quoted text is real - but a real grounding failure: presenting out-of-context content as directly relevant. | **Incorrect** |
| Test 1 | What is a queue in Jira Service Management? | 0.893, 0.810, 0.224, 0.195, 0.184 | Clear answer, cite sources | Correct, accurate, well-cited answer from the two strong-scoring chunks | Correct |
| Test 2 | How do I bulk edit multiple issues at once? | 0.465, 0.171, 0.083, 0.035, 0.032 | State insufficient evidence | Correct - explicitly stated the evidence does not contain clear instructions, did not guess | Correct |
| Test 3 | Can you create a new permission scheme for my project? (action-request phrasing) | 0.983, 0.546, 0.514, 0.175, 0.152 | Explain steps, do not claim to perform the action | Correct - gave numbered steps for the user to follow, never claimed to have created anything itself | Correct |
| Test 4 | Why does Jira only show data from the last 14 days? (leading/false-premise question, designed to test the suspected edge case) | 0.104, 0.088, 0.062, 0.038, 0.019 | Recognize mismatch/insufficiency, or at minimum hedge | **Did not refuse or hedge.** Built a confident general claim by misapplying a narrower, context-specific detail (Kanban board "done items cleared after 14 days" behavior) as if it answered a broader premise about Jira generally. Same failure pattern as the original Query 1 case. | **Incorrect** |

**Score: 4 of 6 tests correct (67%). Both failures share an identical, now-confirmed pattern.**

**Post-manifest verification note:** Test 4's source claim was independently checked against the raw `proj_003.json` file after this manifest was first written. Confirmed verbatim: *"Work items will be automatically cleared from your board 14 days after being moved to the Done column"* and *"If you work in a kanban style, Done work items are automatically cleared from the board every 14 days."* This confirms the overgeneralization was real and precisely as described: the model dropped three scoping qualifiers present in the source (board-display-only, kanban-style-only, Done-items-only) and presented the claim as a general statement about Jira. No correction to the finding itself was needed - this note simply upgrades the earlier inferred description to independently verified.

## Key finding: the "low score + one specific tangential detail" failure mode

This is not a one-off. Two independently-designed tests (Query 1's workflow
question, Test 4's deliberately leading question) both triggered the same
failure: when reranker scores are very low (roughly <0.11 in both failing
cases, versus 0.032-0.465 in Test 2's correctly-handled insufficient case)
AND the retrieved evidence happens to contain one specific, quotable, real
detail from a narrower or different context, the model tends to seize on
that detail and build a confident answer around it - rather than recognizing
the mismatch between the question's actual scope and the evidence's actual
scope.

Contrast with Test 2, where low-scoring evidence was uniformly generic
(no standout specific detail to misapply) - the model correctly said
"insufficient evidence" without difficulty. This suggests the failure isn't
simply "low scores confuse the model" - it's specifically about **specific,
concrete-sounding details in low-relevance evidence being weighted too
heavily relative to their actual contextual relevance.**

## Correctly-working behaviors (confirmed across multiple tests)

- Strong-evidence answers are accurate, well-cited, and appropriately confident
- The model can and does correctly refuse to answer when evidence is
  uniformly weak and non-specific (Test 2)
- Action-request phrasing does not trick the model into false claims of
  having performed Jira actions itself (Test 3), even under a phrasing
  designed to invite that failure
- The model appears to use rerank scores as a soft signal in at least some
  cases (ignoring known-noisy chunks in the pilot test) without needing a
  hard-coded rule

## Decision: no changes made to the pipeline today

Per explicit instruction, the system prompt, reranker candidate pool,
retrieval logic, and scoring/threshold handling were left completely
unchanged throughout all testing today. The one code change made
(automatic retry on OpenRouter's transient capacity errors in
openrouter_client.py) is infrastructure robustness, not a change to RAG
behavior, prompt design, or evidence handling.

This failure mode is being documented, not patched, consistent with the
project's incremental methodology and the plan to address systematic
grounding failures at the Day 9 evidence/grounding-validation stage rather
than through ad hoc prompt or threshold tweaks today.

## Recommendation for Day 9 (grounding validation)

This is now the clearest, most concrete evidence yet for why a programmatic
grounding-validation layer is necessary rather than relying on prompt
instructions alone:
- A simple low-score threshold alone may be insufficient, since Test 2's
  correctly-refused case had a HIGHER top score (0.465) than Test 4's
  incorrectly-answered case (0.104) - meaning a naive "refuse below X"
  threshold could actually be calibrated correctly by score magnitude alone,
  since the two failing cases (0.012 top, 0.104 top) are both lower than
  the successfully-refused case's top score (0.465). This is worth testing
  directly: a threshold somewhere between 0.104 and 0.465 might separate
  today's failures from today's successes cleanly - a concrete, testable
  hypothesis for Day 9, not yet implemented or validated.
- Beyond a score threshold, Day 9 should also consider checking whether the
  cited evidence's topic/category genuinely aligns with the ticket's likely
  category, since both failures involved evidence from a different specific
  context than the question implied.

## Milestone status

Per the roadmap's Day 7 deliverable: a functioning basic RAG chatbot/API
is complete. JIRVA can answer real Jira Cloud questions grounded in the
knowledge base, with accurate citation and correct action-claim avoidance
in the majority of tested cases. A specific, reproducible grounding
weakness has been identified, documented with concrete evidence, and
deliberately deferred to the appropriate later pipeline stage rather than
patched ad hoc - consistent with the project's stated development
methodology throughout.
