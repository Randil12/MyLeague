"""Annual boundaries and non-truncating pagination; no network or database."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from jobs.leaguepedia.client import PaginationLimit, cargo_query, fetch_scoreboard_players
from jobs.leaguepedia.yearly import fetch_complete, windows


def client_with_pages(pages):
    calls = []
    def query(**kwargs):
        calls.append(kwargs)
        return pages[len(calls) - 1]
    return SimpleNamespace(cargo_client=SimpleNamespace(query=query)), calls


def test_full_page_is_not_assumed_complete(monkeypatch):
    monkeypatch.setattr("jobs.leaguepedia.client.time.sleep", lambda _: None)
    client, calls = client_with_pages([[{"id": 1}, {"id": 2}], [{"id": 3}]])
    with pytest.raises(PaginationLimit):
        cargo_query(client, "Games", "id", page_size=2, max_pages=1, strict=True)
    assert calls[-1]["offset"] == 2
    assert calls[-1]["limit"] == 1


def test_exact_page_size_with_empty_probe_is_complete(monkeypatch):
    monkeypatch.setattr("jobs.leaguepedia.client.time.sleep", lambda _: None)
    client, _ = client_with_pages([[{"id": 1}, {"id": 2}], []])
    assert len(cargo_query(client, "Games", "id", page_size=2, max_pages=1, strict=True)) == 2


def test_scoreboard_has_exclusive_upper_bound_and_no_retirement_filter(monkeypatch):
    monkeypatch.setattr("jobs.leaguepedia.client.time.sleep", lambda _: None)
    client, calls = client_with_pages([[]])
    fetch_scoreboard_players(client, "2026-01-01 00:00:00", until_iso="2026-01-02 00:00:00")
    assert 'DateTime_UTC < "2026-01-02 00:00:00"' in calls[0]["where"]
    assert "IsRetired" not in calls[0]["where"]
    assert calls[0]["order_by"] == "DateTime_UTC,GameId,Link"


def test_daily_windows_include_leap_day_and_never_overlap():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2025, 1, 1, tzinfo=timezone.utc)
    parts = list(windows(start, end))
    assert len(parts) == 366
    assert parts[-1][1] == end
    assert all(a[1] == b[0] for a, b in zip(parts, parts[1:]))


def test_saturated_window_is_split_without_gaps():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    calls = []
    def fetch(client, lower, max_pages, until_iso):
        calls.append((lower, until_iso))
        if len(calls) == 1:
            raise PaginationLimit("full")
        return [{"start": lower}]
    rows = fetch_complete(None, fetch, start, start + timedelta(days=1), 1)
    assert len(rows) == 2
    assert calls[1][1] == calls[2][0]
    assert calls[1][0] == calls[0][0]
    assert calls[2][1] == calls[0][1]


def test_unsplittable_window_fails_instead_of_skipping():
    def fetch(*args, **kwargs):
        raise PaginationLimit("full")
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(PaginationLimit):
        fetch_complete(None, fetch, start, start + timedelta(seconds=1), 1)
