"""Annual orchestration guarantees, without external services."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from jobs.leaguepedia import yearly


@pytest.fixture
def collector(monkeypatch, tmp_path):
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = (True,)
    cur.fetchall.return_value = []
    monkeypatch.setattr(yearly.ingest, "get_gold_conn", lambda: conn)
    monkeypatch.setattr(yearly.ingest, "get_client", lambda: object())
    monkeypatch.setattr(yearly.ingest, "get_minio_config", lambda: {})
    monkeypatch.setattr(yearly.ingest, "utc_now", lambda: datetime(2026, 1, 4, 12, tzinfo=timezone.utc))
    monkeypatch.setattr(yearly.ingest, "init_leaguepedia_schema", lambda _: None)
    monkeypatch.setattr(yearly.ingest, "start_run", lambda *args: None)
    monkeypatch.setattr(yearly.ingest, "finish_run", lambda *args: None)
    monkeypatch.setattr(yearly, "fetch_complete", lambda *args: [{"GameId": "g1"}])
    monkeypatch.setattr(yearly.ingest, "save_bronze", lambda *args: None)
    monkeypatch.setattr(yearly.ingest, "upsert_scoreboard_games", lambda *args: 1)
    monkeypatch.setattr(yearly.ingest, "upsert_scoreboard_players", lambda *args: 1)
    return conn, cur, tmp_path


def test_partial_backfill_is_reported_not_complete(collector):
    conn, _, path = collector
    result = yearly.run(path, days_per_run=3)
    assert result["days_processed"] == 3
    assert result["days_remaining"] == 1
    assert result["coverage_complete_as_observed"] is False
    conn.close.assert_called_once()


def test_incomplete_raw_load_does_not_checkpoint(collector, monkeypatch):
    conn, cur, path = collector
    monkeypatch.setattr(yearly.ingest, "upsert_scoreboard_players", lambda *args: 0)
    with pytest.raises(RuntimeError, match="Incomplete raw load"):
        yearly.run(path)
    assert not any("INSERT INTO audit.leaguepedia_year_days" in str(c) for c in cur.execute.call_args_list)
    conn.rollback.assert_called_once()


def test_minio_failure_prevents_raw_writes(collector, monkeypatch):
    _, cur, path = collector
    save = MagicMock(side_effect=RuntimeError("archive unavailable"))
    write = MagicMock()
    monkeypatch.setattr(yearly.ingest, "save_bronze", save)
    monkeypatch.setattr(yearly.ingest, "upsert_scoreboard_games", write)
    with pytest.raises(RuntimeError, match="archive unavailable"):
        yearly.run(path)
    write.assert_not_called()
    assert not any("INSERT INTO audit.leaguepedia_year_days" in str(c) for c in cur.execute.call_args_list)


def test_parallel_collector_is_rejected(collector):
    conn, cur, path = collector
    cur.fetchone.return_value = (False,)
    with pytest.raises(RuntimeError, match="already running"):
        yearly.run(path)
    conn.close.assert_called_once()


def test_recent_days_refresh_but_fresh_history_is_not_reloaded(collector):
    _, cur, path = collector
    now = datetime(2026, 1, 4, 12, tzinfo=timezone.utc)
    cur.fetchall.return_value = [(datetime(2026, 1, d).date(), now) for d in range(1, 5)]
    result = yearly.run(path, revisit_after_seconds=86400)
    assert result["days_processed"] == 2
    assert result["coverage_complete_as_observed"] is True


def test_legacy_equipment_days_are_revisited_first(collector, monkeypatch):
    _, cur, path = collector
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    cur.fetchall.side_effect = [
        [(datetime(2026, 1, d).date(), old) for d in range(1, 5)],
        [(datetime(2026, 1, 2).date(),)],
    ]
    fetch = MagicMock(return_value=[{'GameId':'g1'}])
    monkeypatch.setattr(yearly, 'fetch_complete', fetch)
    yearly.run(path, days_per_run=3)
    # Recent days first, then the incomplete historical day within the same cap.
    assert [call.args[2].day for call in fetch.call_args_list] == [3,3,4,4,2,2]
    assert any("payload ?&" in call.args[0] for call in cur.execute.call_args_list)
