import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { getTickets } from "../api";
import { getOutcomeBadge } from "../outcomeBadge";
import { OUTCOME_STAT_DEFS } from "../outcomeStats";
import DonutChart from "../components/DonutChart";
import StatCard from "../components/StatCard";
import DistributionList from "../components/DistributionList";
import { ClockIcon } from "../icons";
import "./Dashboard.css";

const CHART_COLORS = {
  RESOLVE: "#15803D",
  GUIDE: "#2563EB",
  ESCALATE: "#B91C1C",
  FALLBACK: "#B45309",
  OUT_OF_DOMAIN: "#9CA3AF",
};

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
      .then(({ tickets }) => setTickets(tickets))
      .catch((err) => setError(err.message || "Could not load query history."));
  }, []);

  const counts = { total: tickets?.length ?? 0 };
  const categoryCounts = {};
  if (tickets) {
    for (const def of OUTCOME_STAT_DEFS) {
      if (def.outcome) {
        counts[def.key] = tickets.filter((t) => t.outcome === def.outcome).length;
      }
    }
    for (const t of tickets) {
      if (t.category) categoryCounts[t.category] = (categoryCounts[t.category] || 0) + 1;
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
          JIRVA (Jira Intelligent Resolution Virtual Assistant) analyzes
          incoming support queries, retrieves relevant
          documentation, and either resolves the issue directly, guides the
          user through troubleshooting, or escalates to a human agent when
          evidence is insufficient or risk is high.
        </p>
        <Link to="/raise" className="btn-primary dashboard-cta">
          Ask JIRVA
        </Link>
      </div>

      {error && <div className="form-error">{error}</div>}

      {tickets && (
        <div className="card-grid">
          {OUTCOME_STAT_DEFS.map((def) => (
            <StatCard
              key={def.key}
              icon={def.icon}
              label={def.label}
              count={counts[def.key]}
              onClick={() => navigate(def.outcome ? `/tickets?outcome=${def.outcome}` : "/tickets")}
            />
          ))}
        </div>
      )}

      {tickets && tickets.length === 0 && (
        <div className="panel dashboard-note">
          <p>No queries submitted yet. Ask JIRVA a question to see it reflected here.</p>
        </div>
      )}

      {tickets && tickets.length > 0 && (
        <>
          <div className="dashboard-row">
            <div className="panel dashboard-distribution">
              <h2>Query Outcome Distribution</h2>
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
              <div className="dashboard-recent-header">
                <h2>Recent Queries</h2>
                <Link to="/tickets" className="dashboard-view-all">View all</Link>
              </div>
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

          <div className="panel dashboard-category">
            <h2>Category Breakdown</h2>
            <p className="dashboard-category-note">Which Jira topics are being asked about most.</p>
            <DistributionList distribution={categoryCounts} />
          </div>
        </>
      )}
    </div>
  );
}
