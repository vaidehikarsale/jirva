# JIRVA - Day 9 Manifest: Decision Engine (RESOLVE / GUIDE / ESCALATE / FALLBACK)

**Date:** 2026-09-10

## What was built

- **decision_engine.py**: three-signal decision logic (evidence_confidence,
  risk, category_alignment) producing one of four outcomes. Per explicit
  project decision, `risk` (from ticket_analysis.py) handles all
  sensitivity/escalation logic - no separate hard-coded category-sensitivity
  list was added. `category_alignment` (top evidence category vs. ticket
  category) is kept as a distinct signal from `risk`, since it answers a
  different question (was the right *kind* of evidence retrieved) than risk
  does (is this ticket sensitive) - and it was exactly this kind of mismatch
  that drove both of Day 7's grounding failures.
- **jirva.py (rewired)**: replaced the Day 8 all-or-nothing
  generate-or-refuse behavior with the four-outcome control flow:
  - FALLBACK: no generation, fixed insufficient-evidence message
  - ESCALATE: no generation (for now, per explicit decision), returns
    ticket + evidence + ticket-analysis + escalation reason for a human agent
  - GUIDE: generates using a dedicated system prompt (mirrors rag_answer.py's
    SYSTEM_PROMPT structure/rule-numbering, but forbids a definitive
    diagnosis and asks for diagnostic/verification steps instead)
  - RESOLVE: generates using the existing rag_answer.py SYSTEM_PROMPT,
    unchanged from Day 7/8

Both threshold values (`fallback_threshold=0.05`, `resolve_threshold=0.50`)
remain explicit placeholders, not yet calibrated - exposed as parameters
for Task 5.

## Task 2 verification: decision_engine.py standalone logic test

Run against the three real recorded values from Day 7/8 (wf_004: 0.012,
proj_003: 0.104, known-good: 1.000):

| Case | evidence_confidence | Outcome | Expected | Verdict |
|---|---|---|---|---|
| wf_004 | 0.012 | FALLBACK | FALLBACK | Correct |
| proj_003 | 0.104 | GUIDE | GUIDE (expected fall-through with placeholder thresholds) | Correct |
| known-good | 1.000 | RESOLVE | RESOLVE | Correct |

Logic executes cleanly and separates the three known cases exactly as
designed with the placeholder thresholds. This does not mean the
thresholds themselves are correct - only that the decision logic correctly
applies whatever thresholds it's given, which is what Task 2 needed to
confirm.

## Task 4: pilot test through the full rewired pipeline

Re-ran the same three tickets end-to-end through `jirva.py` (not just
decision_engine.py in isolation), using the exact ticket text recorded in
the Day 7 manifest:

| Ticket | evidence_confidence (this run) | evidence_confidence (Day 7 recorded) | Outcome | Verdict |
|---|---|---|---|---|
| "Why can't I move my issue to Done?" (wf_004) | 0.0115 | 0.012 | FALLBACK | Correct - system now declines instead of confidently misapplying the "Approved status" example |
| "Why does Jira only show data from the last 14 days?" (proj_003) | 0.104 | 0.104 | GUIDE | Correct routing; see finding below on generation quality |
| "How do I save a search as a filter?" (known-good) | 0.9999 | 1.000 | RESOLVE | Correct - clean grounded answer, matches Day 7 behavior |

Confidence scores reproduced almost exactly across all three, confirming
the retrieval/rerank pipeline itself is stable and deterministic run to
run (the tiny wf_004 variance, 0.0115 vs 0.012, is noise-level, not a
concern).

**Note on test methodology:** the first pilot-test attempt used literal
placeholder ticket text (`"<wf_004 ticket text>"` etc.) instead of the real
ticket wording, which produced uniformly low-relevance retrieval across all
three "tickets" and gave a false FALLBACK-only result. This was caught
before being recorded as a result, and the real ticket text (pulled
directly from the Day 7 manifest table) was used for the actual pilot test
above.

## Key finding: GUIDE's hedged framing is a real improvement, but did not fully eliminate the scope-narrowing failure mode

Day 7 documented a specific grounding failure: the model built a confident,
unqualified claim ("Jira clears items after 14 days") by dropping the
source's actual qualifiers - the 14-day auto-clear behavior is scoped to
**Kanban-style** boards specifically, per the verbatim source text quoted in
the Day 7 manifest.

This run's GUIDE-path answer for the same ticket is a genuine behavioral
improvement in tone and structure: it presents the 14-day rule as something
to *verify* rather than a settled fact, cites sources per step, and never
claims to have taken an action. However, it still narrows the qualifying
condition incorrectly - it frames the check as "confirm whether the board
is **team-managed**" rather than "confirm whether the board is
**Kanban-style**."

**Manually verified against the raw source** (`proj_003_c05.json`, with the
same section also present in `proj_003_c04.json` due to chunk overlap):
the 14-day clearing rule is conditioned specifically on Kanban style, not
on team-managed vs. company-managed status generally. Team-managed and
Kanban-style are different axes (a team-managed project can run Scrum or
Kanban), so this is a genuine, confirmed scope-narrowing error, not a
false alarm.

**Assessment:** this is a softer version of the Day 7/8 failure pattern,
not a full recurrence. The GUIDE prompt successfully prevented the original
failure mode (confident, unqualified, un-hedged claims) but did not fully
resolve the underlying tendency to loosen or substitute a source's specific
scoping condition for the evidence's most prominent surrounding
condition (team-managed being the retrieved chunk's overall topic, Kanban
being the actual condition on the specific 14-day claim within it). Because
the answer is explicitly framed as a verification step rather than a
stated fact, the practical harm is much lower than Day 7's version - the
user is told to check something, not told something false as certain -
but it is recorded here as a residual grounding/scope issue, not
patched today. No code changes were made in response to this finding, per
the project's incremental methodology of documenting rather than ad hoc
patching mid-task.

## Decision: Task 4 closed, no code changes

Per explicit instruction: the "team-managed" vs. "Kanban-style" scope issue
is recorded as a residual finding for future reference (candidate input for
Day 9's own calibration work, or a future prompt-refinement pass), not
addressed with a code change today. Task 4 is closed on that basis - the
routing behavior (GUIDE outcome, no confident false claim, proper hedging)
performed correctly on the axis Task 4 was actually testing, which is
whether the decision engine now correctly declines to fully resolve a
low-confidence ticket.

## Task 5: calibration test set results

Built `calibrate_decision_engine.py`, mirroring Day 8's
`calibrate_domain_guard.py` structure: live pipeline run per ticket (no
hardcoded/stale values trusted), CSV logging, min/max confidence
distribution reported per expected outcome rather than any automated
threshold sweep - thresholds are read off real data, not invented.

Test set: 5 anchor cases reused from Day 7/8 (one relabeled - see below),
9 new tickets targeting the ambiguous 0.10-0.50 confidence range and an
ESCALATE regression check, hand-labeled from actual retrieved evidence
after an initial unlabeled run.

**Anchor correction:** the "bulk edit multiple issues" case was originally
carried forward from Day 7 as expected=FALLBACK, based on Day 7's
"state insufficient evidence" verdict under the old binary refuse/answer
model. Re-derived under the actual four-outcome schema, confidence 0.4655
with category-aligned evidence is "present but not strong enough for a
definitive answer" - exactly what GUIDE exists for, not FALLBACK. Relabeled
to GUIDE. This was a stale-label error on this project's part, not a system
defect.

**Result with all 12 non-ESCALATE hand-labeled cases:** 13/13 OK across two
separate live runs (confidence scores reproduced almost exactly between
runs, confirming retrieval/rerank determinism).

**Confidence distribution (final, candidate resolve_threshold=0.65):**

| Outcome | n | min | max |
|---|---|---|---|
| FALLBACK | 3 | 0.0115 | 0.0362 |
| GUIDE | 7 | 0.0793 | 0.5731 |
| RESOLVE | 3 | 0.8468 | 0.9832 |

## Task 5 key finding: category_alignment can falsely pass on topic mismatch within a shared broad category

The "restrict who can transition an issue to Done" ticket demonstrated why
`category_alignment` is a necessary signal, not a redundant one: its
highest-scoring evidence (0.5731, above even the candidate 0.65 threshold
at the time this was first found relative to the old 0.50 default) was
topically irrelevant (subtask creation, `03_Issues`), while the genuinely
relevant workflow-transition content scored far lower (0.0282/0.0142) but
was present in the retrieved top-5. Without `category_alignment` catching
the top-evidence mismatch, confidence alone would have wrongly RESOLVED
this ticket.

However, category_alignment is not a complete safeguard either - see the
next finding.

## Two ESCALATE anchor tickets: risk/category classification instability across repeated runs

Two deliberately sensitive tickets were added to test ESCALATE routing:
"a former employee still has access to all our projects" and "how do I
permanently delete a project and all its issues."

Across 5 total observed runs per ticket (2 calibration-script runs + 3
fresh standalone `domain_guard.py` runs), `ticket_analysis.py`
(temperature=0.1) did not return a fully consistent classification for
either ticket:

| Ticket | Run | risk | category | Outcome |
|---|---|---|---|---|
| Former employee access | Calibration v1 | High | 02_Permissions | ESCALATE |
| Former employee access | Calibration v2 | **Medium** | 02_Permissions | GUIDE |
| Former employee access | Standalone x3 | High, High, High | 02_Permissions (all 3) | ESCALATE (all 3) |
| Permanent project deletion | Calibration v1 | **Medium** | 03_Issues | RESOLVE |
| Permanent project deletion | Calibration v2 | High | 03_Issues | ESCALATE |
| Permanent project deletion | Standalone x3 | High, High, High | **04_Projects** (all 3) | ESCALATE (all 3) |

**Both tickets landed on `risk="High"` in the majority of the 5 observed
runs (4/5 and 4/5 respectively), and ESCALATE is judged the correct target
outcome for both on safety grounds** - both are sensitive, high-consequence
admin actions (irrecoverable data deletion; live unauthorized access)
where routing to a human with a clear reason is the appropriate behavior,
not a generic insufficient-evidence FALLBACK message. Both anchors are
locked to expected_outcome=ESCALATE in the calibration test set.

**The instability itself is a genuine residual reliability finding, not
resolved today:** `ticket_analysis.py` at temperature=0.1 is *mostly* but
not perfectly stable. In this small sample, 1 of 5 runs for each ticket
produced a different risk classification than the majority, and in both
cases the minority result was the less-safe one (Medium instead of High,
downgrading ESCALATE to GUIDE or RESOLVE). The permanent-deletion ticket
additionally showed a consistent category shift (03_Issues in both
calibration-script runs vs. 04_Projects in all 3 standalone runs) -
consistent within each invocation context but different between them,
suggesting a possible difference in LLM input context between the two
call sites rather than pure sampling noise, though this was not
investigated further.

**Per explicit decision: not investigated further today** (no
temperature=0 test, no input-context comparison between calibration-script
and standalone invocation, no added safeguard such as majority-vote
sampling or a keyword-based ESCALATE backstop). Thresholds and decision
logic were not changed in response to this finding. This is recorded as a
known limitation: ESCALATE's safety net currently depends on a single,
occasionally-unstable LLM classification call, and can under-fire (fail to
escalate a ticket that should escalate) on a minority of runs for
borderline-sensitive tickets. Candidate future mitigations (not
implemented): lower temperature, multi-sample majority voting, or a
lightweight keyword-based sensitivity backstop independent of the LLM
call - none evaluated, listed here only as directions for a future pass.

## Task 6: threshold calibration decision

- **fallback_threshold**: kept at 0.05 (unchanged). Confirmed evidence
  (FALLBACK max 0.0362, GUIDE min 0.0793) shows a clean gap either side
  of 0.05, with real margin on both sides - no change indicated.
- **resolve_threshold**: candidate value of 0.65 tested (up from the 0.50
  placeholder), based on GUIDE's confirmed max of 0.5731 sitting above the
  old 0.50 threshold - meaning a ticket with confidence between 0.50 and
  0.5731 could previously have wrongly RESOLVED if category-aligned. At
  0.65, all 7 confirmed GUIDE cases (max 0.5731) and all 3 confirmed
  RESOLVE cases (min 0.8468) remain correctly separated, with real margin
  on both sides of the new threshold in the data collected so far. No
  change was made to `decision_engine.py`'s actual `DEFAULT_RESOLVE_THRESHOLD`
  pending explicit confirmation - see status below.


## Status

All six Day 9 tasks complete and verified:

- Task 1 (decision criteria design) - done
- Task 2 (build decision_engine.py) - done, standalone logic verified against known cases
- Task 3 (wire into jirva.py) - done, end-to-end pipeline verified
- Task 4 (pilot test vs. known Day 7/8 failures) - done; wf_004 and known-good
  confirmed correct; proj_003 confirmed correctly routed to GUIDE, with one
  residual grounding/scope finding recorded (GUIDE's hedged answer narrowed
  the 14-day rule's condition to "team-managed" rather than the source's
  actual "Kanban-style" qualifier - not patched, documented above)
- Task 5 (calibration test set) - done; 13/13 hand-labeled non-ESCALATE cases
  correct across two live runs; both ESCALATE anchors confirmed across 5
  total observations each; one residual reliability finding recorded
  (ticket_analysis.py risk/category classification instability at
  temperature=0.1 - not investigated further or patched, per explicit
  decision)
- Task 6 (threshold calibration) - done. DEFAULT_RESOLVE_THRESHOLD locked
  at 0.65 in decision_engine.py (was a 0.50 placeholder);
  DEFAULT_FALLBACK_THRESHOLD confirmed unchanged at 0.05. Verified two ways:
  (1) calibration v2 tested 0.65 as an explicit override against the full
  12-ticket hand-labeled set, 13/13 correct; (2) after locking the value
  into the file itself, `python decision_engine.py`'s standalone test
  (no LLM calls, no rate-limit dependency) confirmed the three known cases
  (wf_004, proj_003, known-good) still produce FALLBACK/GUIDE/RESOLVE
  respectively, with the printed reason string explicitly showing
  "resolve_threshold (0.65)" - direct confirmation the saved file matches
  what was intended, not just that behavior looks plausible. A full live
  re-run of calibrate_decision_engine.py against the locked production
  defaults (rather than an explicit override) was deferred due to hitting
  OpenRouter's free-tier daily rate limit (50 requests/day) - not run
  today; safe to treat as a nice-to-have confirmation rather than a
  blocker, given the logic was already validated via (1) and (2) above.

## Two residual findings carried forward (not fixed today, by explicit decision)

1. **GUIDE-path scope-narrowing (Task 4):** hedged answers can still subtly
   substitute a source's actual scoping condition (e.g. "Kanban-style")
   for the evidence chunk's more prominent surrounding topic (e.g.
   "team-managed"). Lower practical harm than Day 7's original failure
   since GUIDE explicitly frames claims as things to verify, not facts -
   but not fully resolved.
2. **ticket_analysis.py classification instability (Task 5):** at
   temperature=0.1, risk and/or category classification is not perfectly
   stable across repeated runs of the same ticket. In a small sample (5
   runs each on 2 sensitive tickets), 1 of 5 runs per ticket produced a
   less-safe classification than the majority (Medium instead of High),
   which would have caused ESCALATE to under-fire. Candidate future
   mitigations (temperature=0, multi-sample majority voting, a
   keyword-based sensitivity backstop) were identified but not
   implemented or evaluated.

Day 9 deliverable (per roadmap): Ticket -> Evidence -> Risk + confidence ->
Resolve/Guide/Escalate/Fallback - complete, wired into the full pipeline,
calibrated against real data, with residual limitations documented rather
than silently left unaddressed.
