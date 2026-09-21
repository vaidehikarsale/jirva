import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { uploadTicket } from "../api";
import { PlusCircleIcon } from "../icons";
import "./RaiseTicket.css";

export default function RaiseTicket() {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  const canSubmit = title.trim().length > 0 && description.trim().length > 0 && !submitting;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!canSubmit) return;

    setSubmitting(true);
    setError(null);

    try {
      const result = await uploadTicket(title.trim(), description.trim());
      navigate(`/ticket/${result.ticket_id}`);
    } catch (err) {
      setError(err.message || "Something went wrong while submitting the ticket.");
      setSubmitting(false);
    }
  }

  return (
    <div className="panel raise-ticket-panel">
      <div className="raise-ticket-icon"><PlusCircleIcon width={20} height={20} /></div>
      <h1>Raise Ticket</h1>
      <p>Describe the issue and JIRVA will analyze it and respond.</p>

      <form onSubmit={handleSubmit}>
        <label htmlFor="title">Ticket title</label>
        <input
          id="title"
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Short summary of the issue"
          disabled={submitting}
        />

        <label htmlFor="description">Problem description</label>
        <textarea
          id="description"
          rows={6}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Describe what's happening in detail"
          disabled={submitting}
        />

        {error && <div className="form-error">{error}</div>}

        <button type="submit" className="btn-primary" disabled={!canSubmit}>
          {submitting ? "Analyzing ticket..." : "Submit Ticket"}
        </button>

        {submitting && (
          <p className="submitting-note">
            This can take up to a minute - JIRVA is retrieving evidence and
            generating a response.
          </p>
        )}
      </form>
    </div>
  );
}
