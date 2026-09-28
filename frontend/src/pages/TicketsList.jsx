import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { getTickets, deleteTicket } from "../api";
import { getOutcomeBadge } from "../outcomeBadge";
import { OUTCOME_STAT_DEFS } from "../outcomeStats";
import { ListIcon, SearchIcon } from "../icons";
import PageHeader from "../components/PageHeader";
import StatCard from "../components/StatCard";
import "./TicketsList.css";

// Smaller than System Logs' page size (20) - this page has the stat-card
// row above the table, so a page of the same row-count would make this
// page noticeably taller overall. 15 keeps the two pages closer in
// visual/scroll length instead.
const PAGE_SIZE = 15;
const SEARCH_DEBOUNCE_MS = 300;

function formatDate(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleString();
}

export default function TicketsList() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const outcomeFilter = searchParams.get("outcome");

  const [tickets, setTickets] = useState(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [error, setError] = useState(null);
  const [deletingId, setDeletingId] = useState(null);

  // Separate, unpaginated fetch just for the summary cards - they count
  // across the *entire* history, not one page of it, same reasoning as
  // Dashboard's card row.
  const [allTickets, setAllTickets] = useState(null);

  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");

  useEffect(() => {
    getTickets()
      .then(({ tickets: all }) => setAllTickets(all))
      .catch(() => {
        // Summary cards are a nice-to-have on this page - if this fetch
        // fails, the main paginated fetch below still surfaces the real
        // error to the user.
      });
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchInput.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Changing the outcome filter or search changes the underlying result
  // set, so any page position from before is meaningless - reset to 1
  // rather than stranding the user on an out-of-range page.
  useEffect(() => {
    setPage(1);
  }, [outcomeFilter, debouncedSearch]);

  useEffect(() => {
    // Guard against out-of-order responses: if the user types quickly, an
    // earlier (now-stale) request can resolve *after* a later one - without
    // this, its results would silently overwrite the correct, more recent
    // ones. This is what made the search box look broken.
    let cancelled = false;
    setTickets(null);
    getTickets({
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
      outcome: outcomeFilter || undefined,
      q: debouncedSearch || undefined,
    })
      .then(({ tickets: pageTickets, total: totalCount }) => {
        if (cancelled) return;
        setTickets(pageTickets);
        setTotal(totalCount);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || "Could not load query history.");
      });
    return () => { cancelled = true; };
  }, [page, outcomeFilter, debouncedSearch]);

  // If a delete empties the last page (and it isn't page 1), step back a
  // page instead of showing an empty table with tickets still on the
  // previous page.
  useEffect(() => {
    if (tickets && tickets.length === 0 && page > 1) {
      setPage((p) => p - 1);
    }
  }, [tickets, page]);

  async function handleDelete(ticketId, title) {
    const confirmed = window.confirm(
      `Delete this query${title ? ` ("${title}")` : ""}? This cannot be undone.`
    );
    if (!confirmed) return;

    setDeletingId(ticketId);
    try {
      await deleteTicket(ticketId);
      setTickets((prev) => prev.filter((t) => t.ticket_id !== ticketId));
      setTotal((prev) => prev - 1);
      setAllTickets((prev) => (prev ? prev.filter((t) => t.ticket_id !== ticketId) : prev));
    } catch (err) {
      setError(err.message || "Could not delete this query.");
    } finally {
      setDeletingId(null);
    }
  }

  const counts = { total: allTickets?.length ?? 0 };
  if (allTickets) {
    for (const def of OUTCOME_STAT_DEFS) {
      if (def.outcome) {
        counts[def.key] = allTickets.filter((t) => t.outcome === def.outcome).length;
      }
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="tickets-page">
      <PageHeader
        icon={ListIcon}
        title="Query History"
        description="Every query submitted to JIRVA, with its outcome and decision trail."
      />

      {error && <div className="form-error">{error}</div>}

      {allTickets && (
        <div className="card-grid">
          {OUTCOME_STAT_DEFS.map((def) => (
            <StatCard
              key={def.key}
              icon={def.icon}
              label={def.label}
              count={counts[def.key]}
              active={def.outcome ? def.outcome === outcomeFilter : !outcomeFilter}
              onClick={() => navigate(def.outcome ? `/tickets?outcome=${def.outcome}` : "/tickets")}
            />
          ))}
        </div>
      )}

      <div className="panel">
        <div className="tickets-toolbar">
          <div className="tickets-search-wrap">
            <SearchIcon width={15} height={15} className="tickets-search-icon" />
            <input
              type="text"
              placeholder="Search by title..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="tickets-search"
            />
          </div>
          {outcomeFilter && (
            <p className="tickets-filter-note">
              Outcome: <strong>{getOutcomeBadge(outcomeFilter).text}</strong>
              {" - "}
              <Link to="/tickets">clear filter</Link>
            </p>
          )}
        </div>

        {!tickets && !error && <p>Loading...</p>}

        {tickets && tickets.length === 0 && <p>No queries found.</p>}

        {tickets && tickets.length > 0 && (
          <table className="tickets-table">
            <thead>
              <tr>
                <th>Query ID</th>
                <th>Title</th>
                <th>Category</th>
                <th>Decision</th>
                <th>Risk</th>
                <th>Date</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {tickets.map((t) => {
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

        {tickets && tickets.length > 0 && totalPages > 1 && (
          <div className="pagination">
            <button
              className="pagination-btn"
              onClick={() => setPage((p) => p - 1)}
              disabled={page === 1}
            >
              Previous
            </button>
            <span className="pagination-status">
              Page {page} of {totalPages} ({total} quer{total === 1 ? "y" : "ies"})
            </span>
            <button
              className="pagination-btn"
              onClick={() => setPage((p) => p + 1)}
              disabled={page === totalPages}
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
