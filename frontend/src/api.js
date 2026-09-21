// Single source of truth for the backend URL. Change this one line when
// deploying (Day 15) rather than hunting through every fetch call.
export const API_BASE_URL = "http://localhost:8000";

export async function uploadTicket(title, description) {
  const response = await fetch(`${API_BASE_URL}/ticket/upload`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, description }),
  });

  if (!response.ok) {
    let detail = "";
    try {
      const errBody = await response.json();
      detail = errBody.detail || JSON.stringify(errBody);
    } catch {
      // response wasn't JSON - fall through with empty detail
    }
    throw new Error(`Upload failed (${response.status})${detail ? ": " + detail : ""}`);
  }

  return response.json();
}

export async function getTicket(ticketId) {
  const response = await fetch(`${API_BASE_URL}/ticket/${ticketId}`);
  if (!response.ok) {
    throw new Error(`Could not load ticket (${response.status})`);
  }
  return response.json();
}

export async function getTickets() {
  const response = await fetch(`${API_BASE_URL}/tickets`);
  if (!response.ok) {
    throw new Error(`Could not load ticket history (${response.status})`);
  }
  return response.json();
}

export async function deleteTicket(ticketId) {
  const response = await fetch(`${API_BASE_URL}/ticket/${ticketId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`Could not delete ticket (${response.status})`);
  }
  return response.json();
}

export async function getKnowledgeBase() {
  const response = await fetch(`${API_BASE_URL}/knowledge-base`);
  if (!response.ok) {
    throw new Error(`Could not load knowledge base (${response.status})`);
  }
  return response.json();
}

