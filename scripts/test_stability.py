import requests

ticket = "A former employee still has access to all our projects. How do I revoke that access immediately?"

print(f"Running the same ticket 5 times through /ticket/analyze:\n\"{ticket}\"\n")

results = []
for i in range(1, 6):
    response = requests.post(
        "http://127.0.0.1:8000/ticket/analyze",
        json={"ticket": ticket},
    )
    data = response.json()
    ta = data.get("ticket_analysis", {})
    decision = data.get("decision", {})

    row = {
        "run": i,
        "evidence_confidence": data.get("evidence_confidence"),
        "risk": ta.get("risk"),
        "category": ta.get("category"),
        "outcome": decision.get("outcome"),
    }
    results.append(row)
    print(f"Run {i}: evidence_confidence={row['evidence_confidence']} | "
          f"risk={row['risk']} | category={row['category']} | outcome={row['outcome']}")

print("\n--- Stability check ---")
risks = set(r["risk"] for r in results)
categories = set(r["category"] for r in results)
outcomes = set(r["outcome"] for r in results)

print(f"Distinct risk values seen: {risks} {'(STABLE)' if len(risks) == 1 else '(UNSTABLE)'}")
print(f"Distinct category values seen: {categories} {'(STABLE)' if len(categories) == 1 else '(UNSTABLE)'}")
print(f"Distinct outcome values seen: {outcomes} {'(STABLE)' if len(outcomes) == 1 else '(UNSTABLE)'}")
