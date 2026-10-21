"""
Regression suite for ticket_analysis's HIGH_RISK_BACKSTOP_RULES - the
deterministic safety net added specifically because the LLM's own risk
classification was shown (Day 9 calibration + live Day 11 repro) to be
unstable across repeated calls of the identical ticket. These rules must
never depend on the LLM, so they are fully unit-testable offline.

The "former employee retains access" case is taken directly from the
known-failure row in logs/decision_engine_calibration_v2.csv, where the
LLM classified risk as Medium instead of the expected High - this is the
exact scenario the backstop exists to catch.
"""
import pytest

from ticket_analysis import _high_risk_backstop_triggered


KNOWN_FAILURE_TICKET = (
    "A former employee still has access to all our projects. "
    "How do I revoke that access immediately?"
)


@pytest.mark.parametrize("ticket,expected_rule", [
    (KNOWN_FAILURE_TICKET, "former_employee_retains_access"),
    ("An ex-employee still has access to the finance project.", "former_employee_retains_access"),
    ("Someone gained unauthorized access to our admin project.", "unauthorized_access"),
    ("A teammate's API key was leaked in a public repo.", "credential_exposure"),
    ("Our admin password got exposed in a Slack channel.", "credential_exposure"),
    ("Please revoke access for this account right away, it may still have access.", "urgent_access_revocation"),
])
def test_backstop_triggers_on_known_dangerous_phrasing(ticket, expected_rule):
    triggered, rule = _high_risk_backstop_triggered(ticket)
    assert triggered is True
    assert rule == expected_rule


@pytest.mark.parametrize("ticket", [
    "Why can't I move my issue to Done?",
    "How do I bulk edit multiple issues at once?",
    "How do I permanently delete a project and all its issues?",  # destructive, but not a backstop-covered phrasing
    "What is a queue in Jira Service Management?",
])
def test_backstop_does_not_trigger_on_ordinary_tickets(ticket):
    triggered, rule = _high_risk_backstop_triggered(ticket)
    assert triggered is False
    assert rule is None


def test_backstop_is_case_insensitive():
    triggered, rule = _high_risk_backstop_triggered(
        "AN EX-EMPLOYEE STILL HAS ACCESS TO EVERYTHING."
    )
    assert triggered is True
    assert rule == "former_employee_retains_access"
