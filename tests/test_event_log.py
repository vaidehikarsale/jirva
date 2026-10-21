"""
Regression suite for event_log.EventLog - covers pagination and status
filtering (the logic behind GET /logs's limit/offset/status params),
against a real (temp-file) SQLite database.
"""
import pytest

from event_log import EventLog


@pytest.fixture
def log(tmp_path):
    return EventLog(str(tmp_path / "test_events.db"))


def _seed(log, n, status="success"):
    for i in range(n):
        log.record(
            endpoint="/ticket/analyze", ticket_preview=f"ticket {i}",
            domain="Jira", outcome="RESOLVE", status=status, latency_ms=100.0 + i,
        )


def test_list_recent_newest_first(log):
    log.record("/ticket/analyze", "older", "Jira", "RESOLVE", "success", 100.0)
    log.record("/ticket/analyze", "newer", "Jira", "GUIDE", "success", 100.0)
    rows = log.list_recent(limit=10)
    assert [r["ticket_preview"] for r in rows] == ["newer", "older"]


class TestPagination:
    def test_limit_returns_requested_page_size(self, log):
        _seed(log, 5)
        assert len(log.list_recent(limit=2, offset=0)) == 2

    def test_offset_advances_through_pages_without_overlap(self, log):
        _seed(log, 5)
        page1 = {r["id"] for r in log.list_recent(limit=2, offset=0)}
        page2 = {r["id"] for r in log.list_recent(limit=2, offset=2)}
        assert page1.isdisjoint(page2)

    def test_count_matches_total_regardless_of_limit(self, log):
        _seed(log, 5)
        assert log.count() == 5
        assert len(log.list_recent(limit=2, offset=0)) == 2


class TestStatusFilter:
    def test_status_filter_narrows_list_and_count_consistently(self, log):
        _seed(log, 3, status="success")
        _seed(log, 2, status="error")
        errors = log.list_recent(limit=10, status="error")
        assert len(errors) == 2
        assert log.count(status="error") == 2
        assert all(r["status"] == "error" for r in errors)

    def test_no_status_filter_returns_everything(self, log):
        _seed(log, 3, status="success")
        _seed(log, 2, status="error")
        assert log.count() == 5
