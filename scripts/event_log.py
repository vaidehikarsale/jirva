"""
JIRVA - Event Log (System Logs backend)
------------------------------------------------
Structured, queryable log of every pipeline request the API handles:
timestamp, endpoint, ticket domain/outcome, latency, and success/error
status. Backs the "System Logs" frontend page (previously a stub) and the
live error-rate/latency figures in evaluation.py's live_summary().

Deliberately separate from uvicorn's stdout logging (logs/backend.log):
that's unstructured text meant for a human tailing a terminal (and is lost
on restart unless redirected); this is structured rows in the same SQLite
file ticket_store.py already uses (data/jirva.db, different table) -
queryable, persistent, and directly renderable as a table in the frontend.

Usage (as a library):
    from event_log import EventLog, timed_event

    log = EventLog("../data/jirva.db")

    with timed_event(log, "/ticket/resolve", ticket_text) as rec:
        result = do_the_work(ticket_text)
        rec.domain = result["domain"]
        rec.outcome = result.get("outcome")
        return result
    # success/error + latency_ms recorded automatically either way
"""
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      TEXT NOT NULL,
    endpoint       TEXT NOT NULL,
    ticket_preview TEXT,
    domain         TEXT,
    outcome        TEXT,
    status         TEXT NOT NULL,
    latency_ms     REAL,
    error_message  TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_id ON events (id);
"""

MAX_TICKET_PREVIEW_CHARS = 160


class EventLog:
    def __init__(self, db_path):
        self.db_path = db_path
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def record(self, endpoint, ticket_preview, domain, outcome, status, latency_ms, error_message=None):
        preview = (ticket_preview or "")[:MAX_TICKET_PREVIEW_CHARS]
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO events
                   (timestamp, endpoint, ticket_preview, domain, outcome, status, latency_ms, error_message)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    endpoint, preview, domain, outcome, status, latency_ms, error_message,
                ),
            )

    def list_recent(self, limit=200, offset=0, status=None):
        """Newest first. `limit` is required (unlike ticket_store's
        list_summaries) - System Logs is a live tail, not a full audit
        export with an unpaginated "everything" mode, so there's no caller
        that needs an unbounded query here."""
        where = " WHERE status = ?" if status else ""
        params = [status] if status else []
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT id, timestamp, endpoint, ticket_preview, domain, outcome,
                          status, latency_ms, error_message
                   FROM events{where} ORDER BY id DESC LIMIT ? OFFSET ?""",
                (*params, limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]

    def count(self, status=None):
        where = " WHERE status = ?" if status else ""
        params = [status] if status else []
        with self._connect() as conn:
            return conn.execute(f"SELECT COUNT(*) FROM events{where}", params).fetchone()[0]

    def clear(self):
        """Used by tests / manual cleanup - not exposed over the API."""
        with self._connect() as conn:
            conn.execute("DELETE FROM events")


class _EventRecorder:
    """Mutable holder the caller fills in inside the `with timed_event(...)`
    block, since the final domain/outcome usually aren't known until partway
    through the work being timed."""

    def __init__(self):
        self.domain = None
        self.outcome = None


@contextmanager
def timed_event(log, endpoint, ticket_preview):
    """Times the wrapped block and records exactly one event row: success
    (with whatever rec.domain/rec.outcome were set to) if the block
    completes normally, or error (with the exception message, domain/
    outcome left as whatever was set before the failure) if it raises.
    The exception is always re-raised unchanged - this only observes."""
    start = time.monotonic()
    rec = _EventRecorder()
    try:
        yield rec
    except Exception as exc:
        latency_ms = (time.monotonic() - start) * 1000
        log.record(endpoint, ticket_preview, rec.domain, rec.outcome,
                    "error", latency_ms, error_message=str(exc))
        raise
    else:
        latency_ms = (time.monotonic() - start) * 1000
        log.record(endpoint, ticket_preview, rec.domain, rec.outcome,
                    "success", latency_ms, error_message=None)
