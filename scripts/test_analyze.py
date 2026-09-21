import requests

ticket = "Why can't I move my issue to Done?"

response = requests.post(
    "http://127.0.0.1:8000/ticket/analyze",
    json={"ticket": ticket},
)

print("Status code:", response.status_code)
print(response.json())
