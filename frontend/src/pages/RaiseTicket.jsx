import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { uploadTicket } from "../api";
import PageHeader from "../components/PageHeader";
import FaqPanel from "../components/FaqPanel";
import "./RaiseTicket.css";

export default function RaiseTicket() {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const navigate = useNavigate();
  const descriptionRef = useRef(null);

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
      setError(err.message || "Something went wrong while submitting your question.");
      setSubmitting(false);
    }
  }

  function handleQuestionSelect(sample) {
    setTitle(sample.title);
    setDescription(sample.question);
    descriptionRef.current?.focus();
  }

  return (
    <div className="raise-ticket-page">
      <PageHeader
        title="Ask JIRVA"
        description="Describe your Jira-related issue or question."
      />

      <div className="raise-ticket-layout">
        <div className="panel raise-ticket-panel">
          <form onSubmit={handleSubmit}>
            <label htmlFor="title">Query title</label>
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
              ref={descriptionRef}
              rows={13}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe what's happening in detail"
              disabled={submitting}
            />

            {error && <div className="form-error">{error}</div>}

            <button type="submit" className="btn-primary" disabled={!canSubmit}>
              {submitting ? "Analyzing your question..." : "Ask JIRVA"}
            </button>

            {submitting && (
              <p className="submitting-note">
                This can take up to a minute - JIRVA is retrieving evidence and
                generating a response.
              </p>
            )}
          </form>
        </div>

        <FaqPanel onSelect={handleQuestionSelect} disabled={submitting} />
      </div>
    </div>
  );
}
