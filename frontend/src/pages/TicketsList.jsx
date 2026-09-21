import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { getTickets, deleteTicket } from "../api";
import { getOutcomeBadge } from "../outcomeBadge";
import "./TicketsList.css";

function formatDate(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleString();
}

export default function TicketsList() {
  const [searchParams] = useSearchParams();
  const outcomeFilter = searchParams.get("outcome");

  const [tickets, setTickets] = useState(null);
  const [error, setError] = useState(null);
  const [deletingId, setDeletingId] = useState(null);

  useEffect(() => {
    getTickets()
      .then(setTickets)
      .catch((err) => setError(err.message || "Could not load ticket history."));
  }, []);

  async function handleDelete(ticketId, title) {
    const confirmed = window.confirm(
      `Delete this ticket${title ? ` ("${title}")` : ""}? This cannot be undone.`
    );
    if (!confirmed) return;

    setDeletingId(ticketId);
    try {
      await deleteTicket(ticketId);
      setTickets((prev) => prev.filter((t) => t.ticket_id !== ticketId));
    } catch (err) {
      setError(err.message || "Could not delete this ticket.");
    } finally {
      setDeletingId(null);
    }
  }

  if (error) {
    return (
      <div className="panel">
        <h1>Tickets</h1>
        <p className="form-error">{error}</p>
      </div>
    );
  }

  const filtered = outcomeFilter
    ? (tickets || []).filter((t) => t.outcome === outcomeFilter)
    : tickets;

  return (
    <div className="panel">
      <h1>Tickets</h1>
      {outcomeFilter && (
        <p>
          Showing tickets with outcome: <strong>{getOutcomeBadge(outcomeFilter).text}</strong>
          {" - "}
          <Link to="/tickets">clear filter</Link>
        </p>
      )}

      {!tickets && <p>Loading...</p>}

      {tickets && filtered.length === 0 && <p>No tickets found.</p>}

      {tickets && filtered.length > 0 && (
        <table className="tickets-table">
          <thead>
            <tr>
              <th>Ticket ID</th>
              <th>Title</th>
              <th>Category</th>
              <th>Decision</th>
              <th>Risk</th>
              <th>Date</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((t) => {
              const badge = getOutcomeBadge(t.outcome);
              return (
                <tr key={t.ticket_id}>
                  <td className="mono">
                    <Link to={`/ticket/${t.ticket_id}`}>{t.ticket_id.slice(0, 8)}</Link>
                  </td>
                  <td>{t.title || "-"}</td>
                  <td>{t.category || "-"}</td>
                  <td>
                    <span className={`badge ${badge.badgeClass}`}>{badge.text}</span>
                  </td>
                  <td>{t.risk || "-"}</td>
                  <td>{formatDate(t.created_at)}</td>
                  <td>
                    <button
                      className="delete-link"
                      onClick={() => handleDelete(t.ticket_id, t.title)}
                      disabled={deletingId === t.ticket_id}
                    >
                      {deletingId === t.ticket_id ? "..." : "Delete"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
