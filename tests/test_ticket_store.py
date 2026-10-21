"""
Regression suite for ticket_store.TicketStore - covers pagination, outcome
filtering, and title search (the logic behind GET /tickets's limit/offset/
outcome/q params), against a real (temp-file) SQLite database. No mocking:
sqlite3 is fast enough to exercise directly, and this is the one place a
mock would risk hiding a real SQL bug.
"""
import pytest

from ticket_store import TicketStore


def _ticket(title, outcome, category="01_Workflows", risk="Low", created_at="2026-01-01T00:00:00+00:00"):
    return {
        "title": title,
        "outcome": outcome,
        "domain": "Jira",
        "ticket_analysis": {"category": category, "risk": risk},
        "created_at": created_at,
    }


@pytest.fixture
def store(tmp_path):
    return TicketStore(str(tmp_path / "test.db"))


def test_save_and_get_roundtrip(store):
    store.save("t1", _ticket("Kanban board setup", "RESOLVE"))
    result = store.get("t1")
    assert result["title"] == "Kanban board setup"
    assert result["outcome"] == "RESOLVE"


def test_get_missing_ticket_returns_none(store):
    assert store.get("does-not-exist") is None


def test_delete_returns_true_only_when_a_row_existed(store):
    store.save("t1", _ticket("A", "RESOLVE"))
    assert store.delete("t1") is True
    assert store.delete("t1") is False
    assert store.get("t1") is None


def test_list_summaries_newest_first(store):
    store.save("older", _ticket("A", "RESOLVE", created_at="2026-01-01T00:00:00+00:00"))
    store.save("newer", _ticket("B", "GUIDE", created_at="2026-06-01T00:00:00+00:00"))
    summaries = store.list_summaries()
    assert [s["ticket_id"] for s in summaries] == ["newer", "older"]


def test_out_of_domain_gets_display_sentinels(store):
    store.save("ood", {"title": "random", "domain": "Out-of-Domain", "created_at": "2026-01-01T00:00:00+00:00"})
    summary = store.list_summaries()[0]
    assert summary["category"] == "Out-of-Domain"
    assert summary["outcome"] == "OUT_OF_DOMAIN"
    assert summary["risk"] is None


class TestPagination:
    def _seed(self, store, n):
        for i in range(n):
            store.save(f"t{i}", _ticket(f"Ticket {i}", "RESOLVE", created_at=f"2026-01-{i + 1:02d}T00:00:00+00:00"))

    def test_limit_returns_requested_page_size(self, store):
        self._seed(store, 5)
        page = store.list_summaries(limit=2, offset=0)
        assert len(page) == 2

    def test_offset_advances_through_pages_without_overlap(self, store):
        self._seed(store, 5)
        page1 = {s["ticket_id"] for s in store.list_summaries(limit=2, offset=0)}
        page2 = {s["ticket_id"] for s in store.list_summaries(limit=2, offset=2)}
        assert page1.isdisjoint(page2)

    def test_count_matches_total_regardless_of_limit(self, store):
        self._seed(store, 5)
        assert store.count() == 5
        assert len(store.list_summaries(limit=2, offset=0)) == 2

    def test_no_limit_returns_everything(self, store):
        self._seed(store, 5)
        assert len(store.list_summaries()) == 5


class TestFiltering:
    def _seed_mixed_outcomes(self, store):
        store.save("r1", _ticket("Resolve one", "RESOLVE"))
        store.save("r2", _ticket("Resolve two", "RESOLVE"))
        store.save("g1", _ticket("Guide one", "GUIDE"))

    def test_outcome_filter_narrows_list_and_count_consistently(self, store):
        self._seed_mixed_outcomes(store)
        filtered = store.list_summaries(outcome="RESOLVE")
        assert len(filtered) == 2
        assert store.count(outcome="RESOLVE") == 2
        assert all(s["outcome"] == "RESOLVE" for s in filtered)

    def test_search_is_case_insensitive_title_substring(self, store):
        self._seed_mixed_outcomes(store)
        results = store.list_summaries(search="RESOLVE")
        assert {s["ticket_id"] for s in results} == {"r1", "r2"}
        assert store.count(search="resolve") == 2

    def test_search_and_outcome_combine_with_and(self, store):
        self._seed_mixed_outcomes(store)
        results = store.list_summaries(outcome="GUIDE", search="resolve")
        assert results == []
        assert store.count(outcome="GUIDE", search="resolve") == 0

    def test_search_with_no_match_returns_empty(self, store):
        self._seed_mixed_outcomes(store)
        assert store.list_summaries(search="nonexistent") == []
