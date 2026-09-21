import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { getTickets } from "../api";
import { getOutcomeBadge } from "../outcomeBadge";
import { useCountUp } from "../hooks/useCountUp";
import DonutChart from "../components/DonutChart";
import {
  ListIcon, CheckCircleIcon, CompassIcon, AlertTriangleIcon,
  HelpCircleIcon, GlobeIcon, ClockIcon,
} from "../icons";
import "./Dashboard.css";

const CARD_DEFS = [
  { key: "total", label: "Total Tickets", outcome: null, icon: ListIcon },
  { key: "RESOLVE", label: "Resolved", outcome: "RESOLVE", icon: CheckCircleIcon },
  { key: "GUIDE", label: "Guided", outcome: "GUIDE", icon: CompassIcon },
  { key: "ESCALATE", label: "Escalated", outcome: "ESCALATE", icon: AlertTriangleIcon },
  { key: "FALLBACK", label: "Insufficient Evidence", outcome: "FALLBACK", icon: HelpCircleIcon },
  { key: "OUT_OF_DOMAIN", label: "Out of Domain", outcome: "OUT_OF_DOMAIN", icon: GlobeIcon },
];

const CHART_COLORS = {
  RESOLVE: "#15803D",
  GUIDE: "#2563EB",
  ESCALATE: "#B91C1C",
  FALLBACK: "#B45309",
  OUT_OF_DOMAIN: "#9CA3AF",
};

function MetricCard({ def, count, onClick }) {
  const animated = useCountUp(count);
  const Icon = def.icon;
  return (
    <button className="metric-card" onClick={onClick}>
      <div className="metric-icon"><Icon width={18} height={18} /></div>
      <span className="metric-count">{animated}</span>
      <span className="metric-label">{def.label}</span>
    </button>
  );
}

function formatDate(iso) {
  if (!iso) return "-";
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function Dashboard() {
  const [tickets, setTickets] = useState(null);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    getTickets()
      .then(setTickets)
      .catch((err) => setError(err.message || "Could not load ticket history."));
  }, []);

  const counts = { total: tickets?.length ?? 0 };
  if (tickets) {
    for (const def of CARD_DEFS) {
      if (def.outcome) {
        counts[def.key] = tickets.filter((t) => t.outcome === def.outcome).length;
      }
    }
  }

  const chartSegments = Object.keys(CHART_COLORS).map((outcome) => ({
    label: getOutcomeBadge(outcome).text,
    value: counts[outcome] || 0,
    color: CHART_COLORS[outcome],
  }));

  const recentTickets = (tickets || [])
    .slice()
    .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""))
    .slice(0, 5);

  return (
    <div className="dashboard">
      <div className="panel dashboard-hero">
        <p className="dashboard-eyebrow">Overview</p>
        <h1>Welcome back</h1>
        <p>
          JIRVA analyzes incoming support tickets, retrieves relevant
          documentation, and either resolves the issue directly, guides the
          user through troubleshooting, or escalates to a human agent when
          evidence is insufficient or risk is high.
        </p>
        <Link to="/raise" className="btn-primary dashboard-cta">
          Raise Ticket
        </Link>
      </div>

      {error && <div className="form-error">{error}</div>}

      {tickets && (
        <div className="card-grid">
          {CARD_DEFS.map((def) => (
            <MetricCard
              key={def.key}
              def={def}
              count={counts[def.key]}
              onClick={() => navigate(def.outcome ? `/tickets?outcome=${def.outcome}` : "/tickets")}
            />
          ))}
        </div>
      )}

      {tickets && tickets.length === 0 && (
        <div className="panel dashboard-note">
          <p>No tickets raised yet. Submit one to see it reflected here.</p>
        </div>
      )}

      {tickets && tickets.length > 0 && (
        <div className="dashboard-row">
          <div className="panel dashboard-distribution">
            <h2>Ticket Outcome Distribution</h2>
            <div className="distribution-body">
              <DonutChart segments={chartSegments} />
              <ul className="distribution-legend">
                {chartSegments.filter((s) => s.value > 0).map((s) => (
                  <li key={s.label}>
                    <span className="legend-dot" style={{ background: s.color }} />
                    <span className="legend-label">{s.label}</span>
                    <span className="legend-value">{s.value}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div className="panel dashboard-recent">
            <h2>Recent Tickets</h2>
            <ul className="recent-list">
              {recentTickets.map((t) => {
                const badge = getOutcomeBadge(t.outcome);
                return (
                  <li key={t.ticket_id}>
                    <Link to={`/ticket/${t.ticket_id}`} className="recent-link">
                      <span className="recent-title">{t.title || "Untitled"}</span>
                      <span className={`badge ${badge.badgeClass}`}>{badge.text}</span>
                    </Link>
                    <div className="recent-meta">
                      <ClockIcon width={12} height={12} />
                      <span>{formatDate(t.created_at)}</span>
                      <span className="recent-category">{t.category || "-"}</span>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
