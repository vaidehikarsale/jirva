import { useCallback, useEffect, useRef, useState } from "react";
import { getLogs } from "../api";
import { TerminalIcon } from "../icons";
import PageHeader from "../components/PageHeader";
import "./SystemLogs.css";

const PAGE_SIZE = 20;

function formatTimestamp(iso) {
  if (!iso) return "-";
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

export default function SystemLogs() {
  const [logs, setLogs] = useState(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState("all");

  // Changing the status filter changes the underlying result set, so any
  // page position from before is meaningless - reset to 1 rather than
  // stranding the user on an out-of-range page.
  useEffect(() => {
    setPage(1);
  }, [statusFilter]);

  // `load` is triggered both by page/filter effects below AND the manual
  // Refresh button, so an effect-cleanup guard alone wouldn't cover the
  // button path - a request counter does, whichever way `load` was called.
  const latestRequestId = useRef(0);

  const load = useCallback(() => {
    const requestId = ++latestRequestId.current;
    setLogs(null);
    getLogs({
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
      status: statusFilter === "all" ? undefined : statusFilter,
    })
      .then(({ logs: pageLogs, total: totalCount }) => {
        if (latestRequestId.current !== requestId) return;
        setLogs(pageLogs);
        setTotal(totalCount);
        setError(null);
      })
      .catch((err) => {
        if (latestRequestId.current === requestId) {
          setError(err.message || "Could not load system logs.");
        }
      });
  }, [page, statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  // If the current page ends up empty (e.g. new events arrived and pushed
  // this page's rows onto the next one), step back a page instead of
  // showing a blank table.
  useEffect(() => {
    if (logs && logs.length === 0 && page > 1) {
      setPage((p) => p - 1);
    }
  }, [logs, page]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="panel logs-panel">
      <PageHeader
        icon={TerminalIcon}
        title="System Logs"
        description="Recent query-processing events across every endpoint, newest first."
        action={<button className="logs-refresh" onClick={load}>Refresh</button>}
      />

      {error && <div className="form-error">{error}</div>}

      {!logs && !error && <p>Loading...</p>}

      {logs && (
        <>
          <div className="logs-controls">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="logs-filter"
            >
              <option value="all">All statuses</option>
              <option value="success">Success only</option>
              <option value="error">Errors only</option>
            </select>
            <p className="logs-count">
              {total} event{total === 1 ? "" : "s"}
            </p>
          </div>

          {logs.length === 0 && <p className="logs-empty">No events match this filter yet.</p>}

          {logs.length > 0 && (
            <table className="logs-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Endpoint</th>
                  <th>Query</th>
                  <th>Domain</th>
                  <th>Outcome</th>
                  <th>Status</th>
                  <th>Latency</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((e) => (
                  <tr key={e.id} className={e.status === "error" ? "logs-row-error" : ""}>
                    <td className="logs-cell-mono">{formatTimestamp(e.timestamp)}</td>
                    <td className="logs-cell-mono">{e.endpoint}</td>
                    <td className="logs-cell-ticket" title={e.ticket_preview || ""}>
                      {e.ticket_preview || "-"}
                    </td>
                    <td>{e.domain || "-"}</td>
                    <td>{e.outcome || "-"}</td>
                    <td>
                      <span className={`badge ${e.status === "error" ? "badge-danger" : "badge-success"}`}>
                        {e.status.toUpperCase()}
                      </span>
                      {e.error_message && (
                        <div className="logs-error-message">{e.error_message}</div>
                      )}
                    </td>
                    <td className="logs-cell-mono">
                      {e.latency_ms != null ? `${Math.round(e.latency_ms)} ms` : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {logs.length > 0 && totalPages > 1 && (
            <div className="pagination">
              <button
                className="pagination-btn"
                onClick={() => setPage((p) => p - 1)}
                disabled={page === 1}
              >
                Previous
              </button>
              <span className="pagination-status">
                Page {page} of {totalPages} ({total} event{total === 1 ? "" : "s"})
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
        </>
      )}
    </div>
  );
}
