"""
Regression suite for domain_guard.is_short_circuited(), built from the
Day 5 calibration data (logs/domain_guard_calibration.csv).

This only tests the pure threshold gate, not the full check_domain()
pipeline - check_domain() also calls the LLM (ticket_analysis.analyze_ticket)
for anything that isn't short-circuited, which is not deterministic /
not something this offline suite can call. The gate itself, however, is a
pure function of the two recorded signal scores and is fully testable
without models, Qdrant, or network access.

Known gap this suite intentionally does NOT cover (see DOMAIN_GUARD
thresholds being explicitly uncalibrated placeholders, per domain_guard.py's
own docstring): the "How do I configure a GitHub Actions workflow?" row in
the calibration log is a real misclassification (LLM said Jira, expected
Out-of-Domain) that happens *after* the gate - it is not a gate failure and
is correctly excluded from these assertions.
"""
import pytest

from domain_guard import is_short_circuited, DEFAULT_RETRIEVAL_THRESHOLD, DEFAULT_REFERENCE_THRESHOLD
from conftest import load_calibration_csv

CALIBRATION_ROWS = load_calibration_csv("domain_guard_calibration.csv")


def _id(row):
    return f"{row['short_circuited']}:{row['ticket'][:40]}"


@pytest.mark.parametrize("row", CALIBRATION_ROWS, ids=_id)
def test_gate_matches_recorded_short_circuit_decision(row):
    """The short-circuit gate is a pure function of the two recorded scores
    plus the (currently default, placeholder) thresholds - it must reproduce
    the exact short_circuited flag recorded at calibration time."""
    result = is_short_circuited(
        retrieval_score=float(row["retrieval_top_score"]),
        reference_score=float(row["reference_similarity_score"]),
    )
    assert result == (row["short_circuited"] == "True")


def test_short_circuited_rows_were_all_correctly_out_of_domain():
    """Whenever the gate short-circuits, the ticket was always genuinely
    out-of-domain in the calibration set - i.e. no false short-circuit of an
    actual in-domain ticket has been observed yet. If this ever fails, the
    placeholder thresholds are cutting off real Jira tickets before the LLM
    even sees them."""
    for row in CALIBRATION_ROWS:
        if row["short_circuited"] == "True":
            assert row["expected_domain"] == "Out-of-Domain"
            assert row["correct"] == "True"


class TestGateBoundaries:
    def test_both_signals_low_short_circuits(self):
        assert is_short_circuited(0.01, 0.01) is True

    def test_retrieval_signal_alone_high_enough_prevents_short_circuit(self):
        assert is_short_circuited(DEFAULT_RETRIEVAL_THRESHOLD, 0.01) is False

    def test_reference_signal_alone_high_enough_prevents_short_circuit(self):
        assert is_short_circuited(0.01, DEFAULT_REFERENCE_THRESHOLD) is False

    def test_both_signals_high_prevents_short_circuit(self):
        assert is_short_circuited(0.99, 0.99) is False
