"""
JIRVA - Ticket Analysis Component
--------------------------------------
Extracts a structured analysis (intent, category, severity, risk, domain)
from an incoming support ticket, using the LLM as ONE signal among several -
given the ticket text plus two independently-computed lightweight signals
(retrieval confidence, reference-example similarity) as context, rather than
asking "is this Jira-related?" in isolation.

This module does NOT compute the two signal scores itself, and does NOT
implement any short-circuit / threshold logic - it assumes scores are
already computed and passed in. See the domain guard module (Task 3) for
the combination logic and any configurable threshold.

Day 11 update: temperature changed from 0.1 to 0. Day 9 calibration and a
live Day 11 repro both showed classification (risk in particular) was not
fully stable at 0.1 - identical ticket text produced different risk values
across repeated runs, which could cause the ESCALATE safety net to
silently miss a sensitive ticket. Lowering to 0 minimizes (does not
guarantee-eliminate) this sampling randomness. Thresholds and
decision_engine.py logic are unchanged.

Usage (as a library):
    from ticket_analysis import analyze_ticket
    result = analyze_ticket(
        ticket="Why can't I move my issue to Done?",
        retrieval_top_score=0.42,
        reference_similarity_score=0.71,
        top_evidence=[{"title": "...", "category": "01_Workflows"}, ...],
    )
"""

import json
import re

from openrouter_client import call_nemotron

VALID_CATEGORIES = [
    "01_Workflows", "02_Permissions", "03_Issues", "04_Projects", "05_Fields",
    "06_Search", "07_Boards", "08_Notifications", "09_Jira_Service_Management",
    "10_Troubleshooting", "Out-of-Domain",
]

VALID_INTENTS = ["Troubleshooting", "How-to", "Configuration", "Informational", "Other"]
VALID_LEVELS = ["Low", "Medium", "High"]
VALID_DOMAINS = ["Jira", "Out-of-Domain"]

# Day 11 addition: deterministic High-risk backstop for clearly dangerous
# permission/security cases. Runs AFTER the LLM classification, as a floor,
# not a replacement - if the LLM already said High, nothing changes; if a
# rule matches, risk is forced to High regardless of what the LLM said.
# This exists because Day 9 calibration and live Day 11 testing both showed
# the LLM's risk classification is not fully stable across repeated runs of
# the identical ticket (see DAY9_MANIFEST.md and DAY11 notes) - for a small,
# well-defined set of unambiguously dangerous cases, we don't want ESCALATE
# to depend on LLM sampling variance at all.
#
# Each rule is a list of keyword GROUPS. A rule matches only if AT LEAST ONE
# keyword from EVERY group is present (substring, case-insensitive) in the
# ticket text. Using independent groups instead of fixed phrases makes
# matching robust to words in between (e.g. "api key WAS leaked" still
# matches a ["api key"] + ["leaked"] group pair, whereas a fixed phrase
# "api key leaked" would not). Deliberately simple substring matching, no
# second LLM call, no fuzzy/embedding matching - fully auditable.
HIGH_RISK_BACKSTOP_RULES = [
    {
        "name": "former_employee_retains_access",
        "groups": [
            ["access"],
            ["former employee", "ex-employee", "ex employee",
             "no longer works", "left the company", "employee left"],
        ],
    },
    {
        "name": "unauthorized_access",
        "groups": [
            ["unauthorized access", "without authorization", "without permission"],
        ],
    },
    {
        "name": "credential_exposure",
        "groups": [
            ["password", "credential", "credentials", "api key", "token", "secret", "account"],
            ["leaked", "exposed", "compromised", "hacked", "stolen", "breach", "breached"],
        ],
    },
    {
        "name": "urgent_access_revocation",
        "groups": [
            ["access"],
            ["revoke", "disable", "remove access immediately", "still has access"],
        ],
    },
]


def _high_risk_backstop_triggered(ticket_text):
    """Returns (triggered: bool, matched_rule_name: str or None). A rule
    matches if every one of its keyword groups has at least one keyword
    present in the (lowercased) ticket text."""
    text = ticket_text.lower()
    for rule in HIGH_RISK_BACKSTOP_RULES:
        if all(any(keyword in text for keyword in group) for group in rule["groups"]):
            return True, rule["name"]
    return False, None


ANALYSIS_SYSTEM_PROMPT = f"""You are JIRVA's ticket analysis component. Given a support ticket and supporting signals, classify the ticket.

You must respond with ONLY a JSON object, no other text, matching this exact schema:
{{
  "intent": one of {VALID_INTENTS},
  "category": one of {VALID_CATEGORIES},
  "severity": one of {VALID_LEVELS},
  "risk": one of {VALID_LEVELS},
  "domain": one of {VALID_DOMAINS}
}}

Use "Out-of-Domain" for category and domain if the ticket is not about Jira Cloud administration or usage.

Example:
Ticket: "Why can't I move my issue to Done?"
Retrieval top score: 0.42 (moderate - some relevant content found)
Reference similarity: 0.71 (high - sounds like a typical Jira support question)
Top evidence: workflow and transition documentation

Correct output:
{{"intent": "Troubleshooting", "category": "01_Workflows", "severity": "Medium", "risk": "Low", "domain": "Jira"}}

Base your classification on the ticket content AND the provided signals together - low retrieval/similarity scores are evidence the ticket may be out-of-domain or the KB may lack relevant content, but are not automatically decisive on their own.
"""


def _build_evidence_summary(top_evidence):
    if not top_evidence:
        return "(no evidence retrieved)"
    lines = []
    for item in top_evidence[:5]:
        lines.append(f"- {item.get('title', 'unknown')} [{item.get('category', 'unknown')}]")
    return "\n".join(lines)


def _extract_json(text):
    """Defensively extract a JSON object from the model's response, in case
    it added stray prose around the JSON despite instructions."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _validate_and_fill(parsed):
    """Checks each field is one of the allowed values; fills safe defaults
    for anything missing/invalid rather than silently trusting bad output."""
    result = {}
    result["intent"] = parsed.get("intent") if parsed.get("intent") in VALID_INTENTS else "Other"
    result["category"] = parsed.get("category") if parsed.get("category") in VALID_CATEGORIES else "Out-of-Domain"
    result["severity"] = parsed.get("severity") if parsed.get("severity") in VALID_LEVELS else "Medium"
    result["risk"] = parsed.get("risk") if parsed.get("risk") in VALID_LEVELS else "Medium"
    result["domain"] = parsed.get("domain") if parsed.get("domain") in VALID_DOMAINS else "Out-of-Domain"
    return result


def analyze_ticket(ticket, retrieval_top_score, reference_similarity_score, top_evidence=None):
    """
    Returns a dict:
    {
      "intent": ..., "category": ..., "severity": ..., "risk": ..., "domain": ...,
      "domain_confidence_signals": {
          "retrieval_top_score": ..., "reference_similarity_score": ...
      },
      "raw_llm_output": ...,   # for debugging/auditability
      "parse_error": bool      # True if JSON parsing failed and defaults were used
    }
    """
    evidence_summary = _build_evidence_summary(top_evidence)

    user_message = (
        f"Ticket: \"{ticket}\"\n"
        f"Retrieval top score: {retrieval_top_score:.3f}\n"
        f"Reference similarity: {reference_similarity_score:.3f}\n"
        f"Top evidence categories:\n{evidence_summary}\n\n"
        f"Classify this ticket. Respond with ONLY the JSON object."
    )

    messages = [
        {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    raw_output = call_nemotron(messages, max_tokens=200, temperature=0)
    parsed = _extract_json(raw_output)

    parse_error = parsed is None
    validated = _validate_and_fill(parsed if parsed else {})

    backstop_triggered, backstop_rule = _high_risk_backstop_triggered(ticket)
    if backstop_triggered:
        validated["risk"] = "High"
    validated["risk_backstop_triggered"] = backstop_triggered
    validated["risk_backstop_rule"] = backstop_rule

    validated["domain_confidence_signals"] = {
        "retrieval_top_score": retrieval_top_score,
        "reference_similarity_score": reference_similarity_score,
    }
    validated["raw_llm_output"] = raw_output
    validated["parse_error"] = parse_error

    return validated


def main():
    """Standalone test - uses placeholder signal scores since this module
    doesn't compute them itself (that's Task 3's job)."""
    test_ticket = "Why can't I move my issue to Done?"
    print(f"Testing ticket analysis on: \"{test_ticket}\"")
    print("(using placeholder signal scores for standalone testing)\n")

    result = analyze_ticket(
        ticket=test_ticket,
        retrieval_top_score=0.42,
        reference_similarity_score=0.71,
        top_evidence=[
            {"title": "Configure advanced work item workflows", "category": "01_Workflows"},
            {"title": "How to create workflows for business spaces", "category": "01_Workflows"},
        ],
    )

    print("Result:")
    for k, v in result.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
