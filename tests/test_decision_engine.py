"""
Regression suite for decision_engine.decide(), built directly from the
Day 9 calibration data (logs/decision_engine_calibration_v2.csv) that
locked in DEFAULT_RESOLVE_THRESHOLD=0.65.

decide() is a pure function of its four inputs, so given the exact
signals recorded for each calibration ticket, it must always reproduce
the exact outcome recorded in the log - including the one remaining
known-bad row (a FALLBACK/ESCALATE misclassification caused by upstream
ticket_analysis risk instability, not by decide() itself - see
DAY9_MANIFEST.md's "permanently delete a project" finding). That row is
asserted separately below so a future change to decide()'s own logic
can't accidentally "fix" it for the wrong reason (masking the real,
still-open bug in ticket_analysis.py's risk classification instead).

The former-employee ESCALATE row that used to be the second known
failure was fixed by the Day 11 high-risk keyword backstop
(ticket_analysis.HIGH_RISK_BACKSTOP_RULES) and re-verified live on
2026-09-23 - see DAY9_MANIFEST.md's "Update" section. Its calibration row
was corrected in place (risk Medium -> High, ESCALATE now predicted
correctly) rather than left stale, since this same CSV backs the
Evaluation page's live calibration-accuracy display.
"""
import pytest

from decision_engine import decide, RESOLVE, GUIDE, ESCALATE, FALLBACK
from conftest import load_calibration_csv

CALIBRATION_ROWS = load_calibration_csv("decision_engine_calibration_v2.csv")


def _id(row):
    return f"{row['predicted_outcome']}:{row['ticket'][:40]}"


@pytest.mark.parametrize("row", CALIBRATION_ROWS, ids=_id)
def test_decide_matches_recorded_calibration_outcome(row):
    """Given the exact signals recorded at calibration time, decide() must
    reproduce the exact outcome that was recorded - this is the contract
    that locked in the 0.65 resolve threshold."""
    result = decide(
        evidence_confidence=float(row["evidence_confidence"]),
        risk=row["risk"],
        ticket_category=row["ticket_category"],
        top_evidence_category=row["top_evidence_category"],
    )
    assert result["outcome"] == row["predicted_outcome"]
    assert result["category_aligned"] == (row["category_aligned"] == "True")


def test_calibration_data_has_known_failure_case_still_present():
    """Sanity check on the fixture itself: the one remaining known
    upstream-risk-instability failure (see DAY9_MANIFEST.md) must still be
    in the data set decide() is tested against, otherwise this suite
    silently stops covering it."""
    failing = [row for row in CALIBRATION_ROWS if row["correct"] == "False"]
    assert len(failing) == 1
    assert failing[0]["ticket"] == "How do I permanently delete a project and all its issues?"


def test_former_employee_case_now_correctly_escalates():
    """Regression guard for the fix itself: this ticket used to be the
    second known failure (risk misclassified as Medium, predicted GUIDE
    instead of ESCALATE). The Day 11 high-risk keyword backstop fixes it
    deterministically - if this ever regresses back to a non-ESCALATE
    outcome, decide() would be reproducing the pre-fix bug again."""
    row = next(
        r for r in CALIBRATION_ROWS
        if "former employee" in r["ticket"]
    )
    assert row["risk"] == "High"
    assert row["correct"] == "True"
    result = decide(
        evidence_confidence=float(row["evidence_confidence"]),
        risk=row["risk"],
        ticket_category=row["ticket_category"],
        top_evidence_category=row["top_evidence_category"],
    )
    assert result["outcome"] == ESCALATE


class TestThresholdBoundaries:
    """Exact-boundary behavior, not covered by the calibration log itself
    (which only has real-world samples, not edge values)."""

    def test_evidence_exactly_at_fallback_threshold_is_not_fallback(self):
        result = decide(evidence_confidence=0.05, risk="Low",
                         ticket_category="01_Workflows", top_evidence_category="01_Workflows")
        assert result["outcome"] != FALLBACK

    def test_evidence_just_below_fallback_threshold_is_fallback(self):
        result = decide(evidence_confidence=0.0499, risk="Low",
                         ticket_category="01_Workflows", top_evidence_category="01_Workflows")
        assert result["outcome"] == FALLBACK

    def test_evidence_exactly_at_resolve_threshold_with_aligned_category_resolves(self):
        result = decide(evidence_confidence=0.65, risk="Low",
                         ticket_category="01_Workflows", top_evidence_category="01_Workflows")
        assert result["outcome"] == RESOLVE

    def test_high_confidence_but_misaligned_category_guides_not_resolves(self):
        result = decide(evidence_confidence=0.95, risk="Low",
                         ticket_category="01_Workflows", top_evidence_category="02_Permissions")
        assert result["outcome"] == GUIDE

    def test_high_risk_always_escalates_regardless_of_confidence(self):
        result = decide(evidence_confidence=0.99, risk="High",
                         ticket_category="01_Workflows", top_evidence_category="01_Workflows")
        assert result["outcome"] == ESCALATE

    def test_high_risk_escalates_even_below_fallback_threshold(self):
        """FALLBACK is checked first in decide(), so very low evidence
        confidence takes priority over a High risk classification - this
        pins down that ordering explicitly, since it's a real behavioral
        choice (a High-risk ticket with zero evidence still gets the fixed
        FALLBACK message, not an escalation)."""
        result = decide(evidence_confidence=0.01, risk="High",
                         ticket_category="01_Workflows", top_evidence_category="01_Workflows")
        assert result["outcome"] == FALLBACK
