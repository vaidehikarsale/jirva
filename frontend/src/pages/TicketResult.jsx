import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { getTicket, deleteTicket } from "../api";
import { getOutcomeBadge } from "../outcomeBadge";
import { CheckCircleIcon, CompassIcon, AlertTriangleIcon, HelpCircleIcon, GlobeIcon } from "../icons";
import "./TicketResult.css";

const OUTCOME_ICONS = {
  RESOLVE: CheckCircleIcon,
  GUIDE: CompassIcon,
  ESCALATE: AlertTriangleIcon,
  FALLBACK: HelpCircleIcon,
  OUT_OF_DOMAIN: GlobeIcon,
};

function OutcomeBadge({ outcomeKey, badge }) {
  const Icon = OUTCOME_ICONS[outcomeKey] || HelpCircleIcon;
  return (
    <span className={`badge badge-with-icon ${badge.badgeClass}`}>
      <Icon width={13} height={13} />
      {badge.text}
    </span>
  );
}

function AnalysisSection({ ticket, ticketAnalysis }) {
  return (
    <div className="panel section">
      <h2>Ticket Analysis</h2>
      <div className="analysis-grid">
        <div>
          <span className="field-label">Ticket ID</span>
          <span className="field-value mono">{ticket.ticket_id || "-"}</span>
        </div>
        <div>
          <span className="field-label">Customer problem</span>
          <span className="field-value">{ticket.description || ticket.ticket}</span>
        </div>
        {ticketAnalysis ? (
          <>
            <div>
              <span className="field-label">Category</span>
              <span className="field-value">{ticketAnalysis.category}</span>
            </div>
            <div>
              <span className="field-label">Intent</span>
              <span className="field-value">{ticketAnalysis.intent}</span>
            </div>
            <div>
              <span className="field-label">Severity</span>
              <span className="field-value">{ticketAnalysis.severity}</span>
            </div>
            <div>
              <span className="field-label">Risk level</span>
              <span className="field-value">{ticketAnalysis.risk}</span>
            </div>
          </>
        ) : (
          <div>
            <span className="field-label">Out-of-domain status</span>
            <span className="field-value">
              This ticket was classified as outside JIRVA's supported domain
              before detailed analysis - category, intent, severity, and
              risk were not assessed.
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

function ResolutionSection({ ticket }) {
  const badge = getOutcomeBadge(ticket.outcome);
  return (
    <div className="panel section">
      <div className="section-header">
        <h2>Resolution</h2>
        <OutcomeBadge outcomeKey={ticket.outcome} badge={badge} />
      </div>

      <span className="field-label">Confidence / evidence quality</span>
      <p className="decision-reason">{ticket.decision?.reason}</p>

      <span className="field-label">JIRVA response</span>
      <div className="answer-panel">{ticket.answer}</div>

      {ticket.evidence_used?.length > 0 && (
        <>
          <span className="field-label">Sources</span>
          <ul className="sources-list">
            {ticket.evidence_used.map((e, i) => (
              <li key={i}>
                <a href={e.url} target="_blank" rel="noreferrer">{e.title}</a>
                <span className="source-score"> (score {e.score.toFixed(3)})</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function NonResolutionSection({ ticket }) {
  // Shared layout for ESCALATE, FALLBACK, and Out-of-Domain - banner text
  // and heading stay honest to what the decision engine actually decided,
  // per the confirmed Day 11 design decision (never mislabel FALLBACK/
  // Out-of-Domain as "ESCALATED"). Badge color/text comes from the shared
  // outcomeBadge helper (also used by TicketsList) so the two views can't
  // drift; heading text stays local since it's worded slightly differently
  // from the badge ("Fallback" heading vs "INSUFFICIENT EVIDENCE" badge).
  const outcomeKey = ticket.domain === "Out-of-Domain" ? "OUT_OF_DOMAIN" : ticket.outcome;
  const banner = getOutcomeBadge(outcomeKey);

  let heading = "Escalation";
  let reason = ticket.escalation_reason || ticket.decision?.reason;

  if (ticket.domain === "Out-of-Domain") {
    heading = "Out of Domain";
    reason = "This request is outside JIRVA's supported Jira support domain.";
  } else if (ticket.outcome === "FALLBACK") {
    heading = "Fallback";
  }

  return (
    <div className="panel section">
      <div className="section-header">
        <h2>{heading}</h2>
        <OutcomeBadge outcomeKey={outcomeKey} badge={banner} />
      </div>

      <span className="field-label">Reason</span>
      <p className="decision-reason">{reason}</p>

      {ticket.ticket_analysis && (
        <>
          <span className="field-label">Risk level</span>
          <p className="decision-reason">{ticket.ticket_analysis.risk}</p>
        </>
      )}

      <span className="field-label">Issue summary</span>
      <p className="decision-reason">{ticket.description || ticket.ticket}</p>

      {ticket.evidence_used?.length > 0 && (
        <>
          <span className="field-label">Relevant evidence</span>
          <ul className="sources-list">
            {ticket.evidence_used.map((e, i) => (
              <li key={i}>
                <a href={e.url} target="_blank" rel="noreferrer">{e.title}</a>
                <span className="source-score"> (score {e.score.toFixed(3)})</span>
              </li>
            ))}
          </ul>
        </>
      )}

      <span className="field-label">Suggested next steps</span>
      <p className="decision-reason">
        A human support agent should review this ticket directly - JIRVA did
        not generate an automated response for this case.
      </p>
    </div>
  );
}

export default function TicketResult() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [ticket, setTicket] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getTicket(id)
      .then((data) => {
        if (!cancelled) setTicket(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || "Could not load this ticket.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [id]);

  async function handleDelete() {
    const confirmed = window.confirm("Delete this ticket? This cannot be undone.");
    if (!confirmed) return;

    setDeleting(true);
    try {
      await deleteTicket(id);
      navigate("/tickets");
    } catch (err) {
      setError(err.message || "Could not delete this ticket.");
      setDeleting(false);
    }
  }

  if (loading) {
    return <div className="panel"><p>Loading ticket...</p></div>;
  }

  if (error) {
    return (
      <div className="panel">
        <h1>Ticket not found</h1>
        <p className="form-error">{error}</p>
        <Link to="/raise">Raise a new ticket</Link>
      </div>
    );
  }

  const isOutOfDomain = ticket.domain === "Out-of-Domain";
  const isResolutionPath = !isOutOfDomain && (ticket.outcome === "RESOLVE" || ticket.outcome === "GUIDE");

  return (
    <div className="ticket-result">
      <div className="ticket-result-toolbar">
        <button className="delete-link" onClick={handleDelete} disabled={deleting}>
          {deleting ? "Deleting..." : "Delete ticket"}
        </button>
      </div>
      <AnalysisSection ticket={ticket} ticketAnalysis={ticket.ticket_analysis} />
      {isResolutionPath ? (
        <ResolutionSection ticket={ticket} />
      ) : (
        <NonResolutionSection ticket={ticket} />
      )}
    </div>
  );
}
