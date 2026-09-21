import requests

ticket = "How do I save a search as a filter?"

response = requests.post(
    "http://127.0.0.1:8000/ticket/resolve",
    json={"ticket": ticket},
)

print("Status code:", response.status_code)
print(response.json())
