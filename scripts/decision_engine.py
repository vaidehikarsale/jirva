"""
JIRVA - Decision Engine
----------------------------
Determines the final outcome for a ticket: RESOLVE, GUIDE, ESCALATE, or
FALLBACK (insufficient evidence). Uses three signals, all already computed
by earlier pipeline stages:

  1. evidence_confidence - top rerank score (from domain_guard/retrieval)
  2. risk - from ticket_analysis (Low/Medium/High) - handles ALL
     sensitivity/account-specific/admin escalation logic, per project
     decision to avoid a separate hard-coded category-sensitivity rule
  3. category_alignment - whether the top evidence's category matches the
     ticket analysis's own category classification

Day 9 Task 6 update: DEFAULT_RESOLVE_THRESHOLD locked at 0.65 (was 0.50),
per calibrate_decision_engine.py's empirical results. GUIDE's confirmed
max confidence was 0.5731 and RESOLVE's confirmed min was 0.8468 across
13/13 correctly-classified hand-labeled calibration cases - 0.65 sits with
real margin on both sides of that gap. DEFAULT_FALLBACK_THRESHOLD (0.05)
was left unchanged - FALLBACK's confirmed max (0.0362) and GUIDE's
confirmed min (0.0793) already showed a clean gap around 0.05, so the
data did not indicate a change was needed. See DAY9_MANIFEST.md for the
full calibration data and the residual reliability finding (risk/category
classification instability in ticket_analysis.py) that was recorded but
deliberately not addressed by a threshold or logic change.

Usage (as a library):
    from decision_engine import decide
    result = decide(evidence_confidence=0.42, risk="Low", ticket_category="01_Workflows",
                     top_evidence_category="01_Workflows")
"""

# Calibrated per Day 9 Task 6 (calibrate_decision_engine.py). fallback_threshold
# unchanged; resolve_threshold locked at 0.65 (was a 0.50 placeholder).
DEFAULT_FALLBACK_THRESHOLD = 0.05
DEFAULT_RESOLVE_THRESHOLD = 0.65

FALLBACK_MESSAGE = (
    "I couldn't find sufficient information in the available Jira knowledge base "
    "to provide a reliable answer. This case should be reviewed by a support agent."
)

RESOLVE = "RESOLVE"
GUIDE = "GUIDE"
ESCALATE = "ESCALATE"
FALLBACK = "FALLBACK"


def decide(evidence_confidence, risk, ticket_category, top_evidence_category,
           fallback_threshold=DEFAULT_FALLBACK_THRESHOLD,
           resolve_threshold=DEFAULT_RESOLVE_THRESHOLD):
    """
    Returns a dict:
    {
      "outcome": "RESOLVE" | "GUIDE" | "ESCALATE" | "FALLBACK",
      "reason": short human-readable explanation of which rule fired,
      "category_aligned": bool,
      "signals_used": {...}   # for auditability - every decision should be traceable
    }
    """
    category_aligned = (ticket_category == top_evidence_category)

    signals_used = {
        "evidence_confidence": evidence_confidence,
        "risk": risk,
        "ticket_category": ticket_category,
        "top_evidence_category": top_evidence_category,
        "category_aligned": category_aligned,
        "fallback_threshold": fallback_threshold,
        "resolve_threshold": resolve_threshold,
    }

    if evidence_confidence < fallback_threshold:
        return {
            "outcome": FALLBACK,
            "reason": f"evidence_confidence ({evidence_confidence:.4f}) below fallback_threshold ({fallback_threshold})",
            "category_aligned": category_aligned,
            "signals_used": signals_used,
        }

    if risk == "High":
        return {
            "outcome": ESCALATE,
            "reason": "risk classified as High by ticket analysis",
            "category_aligned": category_aligned,
            "signals_used": signals_used,
        }

    if evidence_confidence >= resolve_threshold and category_aligned:
        return {
            "outcome": RESOLVE,
            "reason": (f"evidence_confidence ({evidence_confidence:.4f}) >= resolve_threshold "
                       f"({resolve_threshold}) and evidence category matches ticket category"),
            "category_aligned": category_aligned,
            "signals_used": signals_used,
        }

    return {
        "outcome": GUIDE,
        "reason": "evidence present and risk not High, but confidence/alignment insufficient for a definitive RESOLVE",
        "category_aligned": category_aligned,
        "signals_used": signals_used,
    }


def main():
    """Standalone test using the two known Day 7/8 failure cases plus one
    known-good case, with their real recorded evidence_confidence values."""
    test_cases = [
        {
            "name": "Known failure: wf_004 misapplication case",
            "evidence_confidence": 0.012,
            "risk": "Low",
            "ticket_category": "01_Workflows",
            "top_evidence_category": "01_Workflows",
        },
        {
            "name": "Known failure: proj_003 overgeneralization case",
            "evidence_confidence": 0.104,
            "risk": "Low",
            "ticket_category": "04_Projects",
            "top_evidence_category": "04_Projects",
        },
        {
            "name": "Known good: save search as filter",
            "evidence_confidence": 1.000,
            "risk": "Low",
            "ticket_category": "06_Search",
            "top_evidence_category": "06_Search",
        },
    ]

    for case in test_cases:
        print(f"\n{case['name']}")
        result = decide(
            case["evidence_confidence"], case["risk"],
            case["ticket_category"], case["top_evidence_category"],
        )
        print(f"  Outcome: {result['outcome']}")
        print(f"  Reason: {result['reason']}")


if __name__ == "__main__":
    main()
