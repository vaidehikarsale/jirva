import requests

ticket = "How do I give someone edit access to issues?"

print(f"Running a normal low-risk ticket through /ticket/analyze:\n\"{ticket}\"\n")

for i in range(1, 4):
    response = requests.post(
        "http://127.0.0.1:8000/ticket/analyze",
        json={"ticket": ticket},
    )
    data = response.json()
    ta = data.get("ticket_analysis", {})
    decision = data.get("decision", {})

    print(f"Run {i}: evidence_confidence={data.get('evidence_confidence')} | "
          f"risk={ta.get('risk')} | category={ta.get('category')} | "
          f"outcome={decision.get('outcome')}")
