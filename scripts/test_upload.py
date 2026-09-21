import requests

# --- Step 1: upload a ticket ---
upload_response = requests.post(
    "http://127.0.0.1:8000/ticket/upload",
    json={
        "title": "Saving a search",
        "description": "How do I save a search as a filter?",
    },
)

print("=== UPLOAD ===")
print("Status code:", upload_response.status_code)
upload_data = upload_response.json()
print(upload_data)

ticket_id = upload_data.get("ticket_id")
print("\nAssigned ticket_id:", ticket_id)

if not ticket_id:
    print("No ticket_id returned - stopping before the GET test.")
else:
    # --- Step 2: retrieve it back by id ---
    get_response = requests.get(f"http://127.0.0.1:8000/ticket/{ticket_id}")
    print("\n=== GET BY ID ===")
    print("Status code:", get_response.status_code)
    print(get_response.json())
