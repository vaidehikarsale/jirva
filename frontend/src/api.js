// Single source of truth for the backend URL. Change this one line when
// deploying (Day 15) rather than hunting through every fetch call.
export const API_BASE_URL = "http://localhost:8000";

// Backs the sidebar's live system-status indicator. Deliberately just a
// boolean, not a thrown error - the caller polls this repeatedly and only
// cares "is the API reachable right now", not why a specific request failed.
export async function getHealth() {
  try {
    const response = await fetch(`${API_BASE_URL}/`);
    return response.ok;
  } catch {
    return false;
  }
}

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
    throw new Error(`Could not load query (${response.status})`);
  }
  return response.json();
}

// Omit `limit` for the full, unpaginated history (Dashboard's usage - it
// needs every ticket to count outcomes accurately). Pass `limit`/`offset`
// for one real page (TicketsList's usage); `total` in the return value
// reflects the current `outcome` filter, read from the X-Total-Count
// response header so no second request is needed to compute page count.
export async function getTickets({ limit, offset, outcome, q } = {}) {
  const params = new URLSearchParams();
  if (limit != null) params.set("limit", limit);
  if (offset != null) params.set("offset", offset);
  if (outcome) params.set("outcome", outcome);
  if (q) params.set("q", q);
  const qs = params.toString();

  const response = await fetch(`${API_BASE_URL}/tickets${qs ? `?${qs}` : ""}`);
  if (!response.ok) {
    throw new Error(`Could not load query history (${response.status})`);
  }
  const tickets = await response.json();
  const total = Number(response.headers.get("X-Total-Count") ?? tickets.length);
  return { tickets, total };
}

export async function deleteTicket(ticketId) {
  const response = await fetch(`${API_BASE_URL}/ticket/${ticketId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`Could not delete query (${response.status})`);
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

// Same real-pagination pattern as getTickets: `total` reflects the current
// `status` filter, read from the X-Total-Count response header.
export async function getLogs({ limit, offset, status } = {}) {
  const params = new URLSearchParams();
  if (limit != null) params.set("limit", limit);
  if (offset != null) params.set("offset", offset);
  if (status) params.set("status", status);
  const qs = params.toString();

  const response = await fetch(`${API_BASE_URL}/logs${qs ? `?${qs}` : ""}`);
  if (!response.ok) {
    throw new Error(`Could not load system logs (${response.status})`);
  }
  const logs = await response.json();
  const total = Number(response.headers.get("X-Total-Count") ?? logs.length);
  return { logs, total };
}

export async function getEvaluation() {
  const response = await fetch(`${API_BASE_URL}/evaluation`);
  if (!response.ok) {
    throw new Error(`Could not load evaluation metrics (${response.status})`);
  }
  return response.json();
}

