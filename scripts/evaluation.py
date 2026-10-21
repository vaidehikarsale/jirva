"""
JIRVA - Evaluation Metrics
--------------------------------
Two genuinely different kinds of "evaluation", kept honestly separate
rather than blended into one fabricated "accuracy" number:

1. Calibration accuracy (calibration_summary) - real, labeled accuracy from
   the Day 5/9 hand-labeled calibration sets (logs/domain_guard_calibration.csv,
   logs/decision_engine_calibration_v2.csv). Those logs already carry an
   `expected_*` column and a `correct` column recorded at calibration time;
   this module only aggregates what's already there into a confusion matrix
   and accuracy score. It does NOT re-run the pipeline live - the labels are
   frozen historical ground truth, not something to recompute.

2. Live operational metrics (live_summary) - outcome/category/risk
   distribution plus recent latency/error rate, computed from whatever
   tickets and events actually exist right now (ticket_store.py,
   event_log.py). There is no ground truth for live traffic, so no
   "accuracy" or "faithfulness" number is claimed here - only distribution
   and volume, which is what's honestly knowable without a human labeling
   every live ticket. (Faithfulness/grounding validation remains an
   acknowledged gap - see langgraph_flow.py's docstring - and isn't
   fabricated here just to fill in the Evaluation page.)

Usage (as a library):
    from evaluation import calibration_summary, live_summary
"""
from collections import Counter

from calibration_data import load_calibration_csv
from decision_engine import DEFAULT_RESOLVE_THRESHOLD, DEFAULT_FALLBACK_THRESHOLD


def _confusion_matrix(rows, expected_key, predicted_key):
    matrix = {}
    for row in rows:
        expected = row[expected_key]
        predicted = row[predicted_key]
        matrix.setdefault(expected, Counter())[predicted] += 1
    return {expected: dict(counter) for expected, counter in matrix.items()}


def _accuracy(rows):
    if not rows:
        return None
    correct = sum(1 for row in rows if row["correct"] == "True")
    return correct / len(rows)


def decision_engine_calibration():
    rows = load_calibration_csv("decision_engine_calibration_v2.csv")
    return {
        "name": "Decision Engine",
        "description": "RESOLVE / GUIDE / ESCALATE / FALLBACK outcome classification",
        "total_cases": len(rows),
        "accuracy": _accuracy(rows),
        "confusion_matrix": _confusion_matrix(rows, "expected_outcome", "predicted_outcome"),
        "resolve_threshold": DEFAULT_RESOLVE_THRESHOLD,
        "fallback_threshold": DEFAULT_FALLBACK_THRESHOLD,
        "source": "logs/decision_engine_calibration_v2.csv",
    }


def domain_guard_calibration():
    rows = load_calibration_csv("domain_guard_calibration.csv")
    return {
        "name": "Domain Guard",
        "description": "Jira vs. Out-of-Domain classification",
        "total_cases": len(rows),
        "accuracy": _accuracy(rows),
        "confusion_matrix": _confusion_matrix(rows, "expected_domain", "predicted_domain"),
        "note": ("Retrieval/reference thresholds are still uncalibrated placeholders "
                 "(see domain_guard.py) - this accuracy reflects the current placeholder "
                 "values, not a tuned configuration."),
        "source": "logs/domain_guard_calibration.csv",
    }


def calibration_summary():
    return {
        "decision_engine": decision_engine_calibration(),
        "domain_guard": domain_guard_calibration(),
    }


def live_summary(ticket_summaries, recent_events):
    """ticket_summaries: list of dicts from TicketStore.list_summaries().
    recent_events: list of dicts from EventLog.list_recent()."""
    outcome_counts = Counter(t["outcome"] for t in ticket_summaries if t["outcome"])
    category_counts = Counter(t["category"] for t in ticket_summaries if t["category"])
    risk_counts = Counter(t["risk"] for t in ticket_summaries if t["risk"])

    error_events = [e for e in recent_events if e["status"] == "error"]
    latencies = [e["latency_ms"] for e in recent_events if e["latency_ms"] is not None]

    return {
        "total_tickets": len(ticket_summaries),
        "outcome_distribution": dict(outcome_counts),
        "category_distribution": dict(category_counts),
        "risk_distribution": dict(risk_counts),
        "recent_events_considered": len(recent_events),
        "recent_error_count": len(error_events),
        "recent_error_rate": (len(error_events) / len(recent_events)) if recent_events else None,
        "avg_latency_ms": (sum(latencies) / len(latencies)) if latencies else None,
    }
