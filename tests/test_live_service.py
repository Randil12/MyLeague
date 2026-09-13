"""Spectator lifecycle and error handling without contacting Riot, SQL or MinIO."""
from threading import Event
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend import db
from backend.main import app
from jobs.riot import client
from jobs.riot import live_service as live


class Stop:
    def is_set(self):
        return False

    def wait(self, seconds):
        return False


@pytest.fixture
def cycle(monkeypatch):
    states, beats, archived = [], [], []
    monkeypatch.setattr(live, "select_players", lambda *_: [("p1", "Player 1"), ("p2", "Player 2")])
    monkeypatch.setattr(live, "store_state", lambda *a, **kw: states.append((a, kw)))
    monkeypatch.setattr(live, "heartbeat", lambda *a, **kw: beats.append((a, kw)))
    monkeypatch.setattr(live, "archive_game", lambda *a: archived.append(a))
    return states, beats, archived


def test_cycle_saves_games_and_distinguishes_absence(monkeypatch, cycle):
    states, beats, archived = cycle
    game = {"gameId": 42, "gameQueueConfigId": 420}
    responses = iter([game, None])
    monkeypatch.setattr(live, "get_active_game_by_puuid", lambda *a, **kw: next(responses))
    live.poll_cycle(MagicMock(), {}, Stop(), 60, 5)
    assert [r[0][3] for r in states] == ["in_game", "not_in_game"]
    assert len(archived) == 1
    assert beats[-1][0][1] == "ok"


@pytest.mark.parametrize("code,delay,status", [(429, 180, "rate_limited"), (401, 900, "authentication_error"),
                                               (403, 900, "authentication_error"), (500, 60, "degraded")])
def test_errors_stop_the_cycle_and_never_mean_game_ended(monkeypatch, cycle, code, delay, status):
    states, beats, _ = cycle
    requests = []
    def fail(puuid, retries):
        requests.append(puuid)
        assert retries == 0
        raise client.RiotApiError("secret details must not be logged", code, 180 if code == 429 else None)
    monkeypatch.setattr(live, "get_active_game_by_puuid", fail)
    wait = live.poll_cycle(MagicMock(), {}, Stop(), 60, 5)
    assert requests == ["p1"]
    assert states[0][0][3] == "error"
    assert states[0][1]["error"] == f"riot_{code}"
    assert wait >= delay
    assert beats[-1][0][1] == status


def test_other_queue_is_not_archived(monkeypatch, cycle):
    states, _, archived = cycle
    monkeypatch.setattr(live, "get_active_game_by_puuid", lambda *a, **kw: {"gameQueueConfigId": 450})
    live.poll_cycle(MagicMock(), {}, Stop(), 60, 5)
    assert all(r[0][3] == "other_queue" for r in states)
    assert not archived


def test_storage_failure_is_retriable_not_a_positive_observation(monkeypatch, cycle):
    states, _, _ = cycle
    monkeypatch.setattr(live, "get_active_game_by_puuid", lambda *a, **kw: {"gameQueueConfigId": 420, "gameId": 42})
    def fail(*args):
        raise RuntimeError("MinIO down")
    monkeypatch.setattr(live, "archive_game", fail)
    live.poll_cycle(MagicMock(), {}, Stop(), 60, 5)
    assert len(states) == 1
    assert states[0][0][3] == "error"


@pytest.mark.parametrize("existing", [True, False])
def test_archive_deduplication_and_storage_order(monkeypatch, existing):
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (1,) if existing else None
    calls = []
    monkeypatch.setattr(live, "upload_json_to_minio", lambda *a, **kw: calls.append("bronze"))
    monkeypatch.setattr(live, "insert_live_snapshot", lambda *a: calls.append("sql"))
    config = dict.fromkeys(["bucket", "endpoint_url", "access_key_id", "secret_access_key", "region_name"], "test")
    live.archive_game(conn, {"gameId": 42}, "p1", config)
    assert calls == ([] if existing else ["bronze", "sql"])


def test_shutdown_does_not_start_an_api_request(monkeypatch, cycle):
    stop = Event()
    stop.set()
    request = MagicMock()
    monkeypatch.setattr(live, "get_active_game_by_puuid", request)
    live.poll_cycle(MagicMock(), {}, stop, 60, 5)
    request.assert_not_called()


@pytest.mark.parametrize("header,expected", [(None, 60), ("180", 180), ("invalid", 60), ("inf", 60), ("0", 1)])
def test_retry_after_parsing(header, expected):
    assert client.retry_after_seconds(header) == expected


def test_404_is_absence_but_403_is_an_error(monkeypatch):
    def fail404(*a, **kw):
        raise client.RiotApiError("not found", 404)
    monkeypatch.setattr(client, "fetch_json", fail404)
    assert client.get_active_game_by_puuid("p1", retries=0) is None
    def fail403(*a, **kw):
        raise client.RiotApiError("forbidden", 403)
    monkeypatch.setattr(client, "fetch_json", fail403)
    with pytest.raises(client.RiotApiError):
        client.get_active_game_by_puuid("p1", retries=0)


def test_live_api_reads_only_sanitized_gold_views(monkeypatch):
    calls = []
    monkeypatch.setattr(db, "query", lambda sql: calls.append(sql) or [])
    api = TestClient(app)
    for endpoint in ("status", "players"):
        response = api.get(f"/api/live/{endpoint}")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
    assert all("gold.gold_live_" in sql and "raw." not in sql for sql in calls)
