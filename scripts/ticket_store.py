"""
JIRVA - Ticket Store (SQLite)
-----------------------------------
Replaces the Day 11 JSON-file ticket store (data/tickets_store.json) with a
real SQLite database. Same single-file-on-disk simplicity (still zero extra
services to run), but fixes the concrete gaps the JSON approach had:

  - Concurrent writes: sqlite3's connection handles locking correctly;
    the JSON store rewrote the *entire* file on every save with no locking
    at all, so two near-simultaneous requests could corrupt it.
  - Listing tickets: GET /tickets used to deserialize and scan every
    ticket's full JSON blob on every request just to read 5 summary fields.
    Here those fields are real indexed columns, so listing is a single
    indexed query instead of an O(n) full-payload scan.
  - Partial corruption: a crash mid-write to a single JSON file could lose
    every ticket ever stored; SQLite's write-ahead behavior means a crash
    mid-write can't corrupt previously-committed rows.

Full per-ticket result (ticket_analysis, decision, answer, evidence_used,
etc.) is still stored as a single JSON blob in the `data` column - that
part of the shape is genuinely variable (RESOLVE/GUIDE/ESCALATE/FALLBACK/
Out-of-Domain results all have different keys) and isn't worth normalizing
into columns. Only the fields GET /tickets actually filters/sorts on
(title, category, outcome, risk, created_at) are promoted to real columns.

Usage (as a library):
    from ticket_store import TicketStore
    store = TicketStore("../data/jirva.db")
    store.save(ticket_id, result_dict)
    store.get(ticket_id)          # -> dict or None
    store.delete(ticket_id)       # -> bool (True if a row was deleted)
    store.list_summaries()        # -> list of summary dicts, newest first
"""

import json
import sqlite3
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id  TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    category   TEXT,
    outcome    TEXT,
    risk       TEXT,
    created_at TEXT NOT NULL,
    data       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tickets_created_at ON tickets (created_at);
"""


class TicketStore:
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

    @staticmethod
    def _summary_fields(result):
        """Mirrors api.py's list_tickets_endpoint field derivation exactly:
        Out-of-Domain tickets never reach ticket_analysis/decision, so they
        get the same OUT_OF_DOMAIN display sentinel."""
        if result.get("domain") == "Out-of-Domain":
            return "Out-of-Domain", "OUT_OF_DOMAIN", None
        category = result.get("ticket_analysis", {}).get("category")
        risk = result.get("ticket_analysis", {}).get("risk")
        outcome = result.get("outcome")
        return category, outcome, risk

    def save(self, ticket_id, result):
        """Insert or replace - same semantics as the old dict-then-dump-whole-
        file approach, just scoped to one row instead of the whole store."""
        category, outcome, risk = self._summary_fields(result)
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO tickets
                   (ticket_id, title, category, outcome, risk, created_at, data)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    ticket_id,
                    result.get("title", ""),
                    category,
                    outcome,
                    risk,
                    result.get("created_at"),
                    json.dumps(result),
                ),
            )

    def get(self, ticket_id):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data FROM tickets WHERE ticket_id = ?", (ticket_id,)
            ).fetchone()
        return json.loads(row["data"]) if row else None

    def delete(self, ticket_id):
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM tickets WHERE ticket_id = ?", (ticket_id,))
        return cursor.rowcount > 0

    @staticmethod
    def _where_clause(outcome, search):
        """Shared between list_summaries and count so the two can never
        drift into counting a different set of rows than they list."""
        conditions = []
        params = []
        if outcome is not None:
            conditions.append("outcome = ?")
            params.append(outcome)
        if search:
            conditions.append("LOWER(title) LIKE ?")
            params.append(f"%{search.lower()}%")
        clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        return clause, params

    def list_summaries(self, limit=None, offset=0, outcome=None, search=None):
        """Newest first, via an indexed SQL sort - no full-payload
        deserialization needed for the summary list.

        limit=None (the default) returns everything, unpaginated - this is
        what the Dashboard's outcome-count cards need (they count across
        the *entire* history, not one page of it), so that call site is
        unaffected by TicketsList's real pagination. Passing a limit is
        what makes a query paginated; offset/outcome/search are only
        meaningful together with it.

        `search` is a case-insensitive substring match against title only
        (not the full ticket text) - this is a lightweight "find a query I
        remember submitting" filter, not a search over ticket content.
        """
        where, params = self._where_clause(outcome, search)
        query = f"SELECT ticket_id, title, category, outcome, risk, created_at FROM tickets{where}"
        query += " ORDER BY created_at DESC"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params = params + [limit, offset]

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def count(self, outcome=None, search=None):
        where, params = self._where_clause(outcome, search)
        query = f"SELECT COUNT(*) FROM tickets{where}"
        with self._connect() as conn:
            return conn.execute(query, params).fetchone()[0]
