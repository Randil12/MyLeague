from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend import live_roster as proxy
from backend.main import app
from jobs.riot import live_roster as roster
from jobs.riot.client import RiotApiError
from jobs.riot.live_service import select_players


@pytest.fixture(autouse=True)
def reset_lookup(monkeypatch):
    monkeypatch.setattr(roster, "NEXT_LOOKUP", 0)


@pytest.mark.parametrize("value", [None, "Player", "#EUW", "Player#", "a#b#c", "a\n#b", "a"*33+"#b"])
def test_invalid_id(value):
    with pytest.raises(roster.RosterError) as exc:
        roster.parse_riot_id(value)
    assert exc.value.status == 422


def test_riot_id_resolved_and_euw_checked(monkeypatch):
    fetch = MagicMock(side_effect=[{"puuid": "private-id", "gameName": "My Player", "tagLine": "EUW"}, {}])
    monkeypatch.setattr(roster, "fetch_json", fetch)
    assert roster.resolve(" My Player#EUW ") == ("private-id", "My Player#EUW")
    assert "My%20Player/EUW" in fetch.call_args_list[0].args[0]
    assert "euw1.api.riotgames.com" in fetch.call_args_list[1].args[0]
    assert all(c.kwargs == {"retries": 0} for c in fetch.call_args_list)


@pytest.mark.parametrize("code,expected", [(404,404), (401,503), (403,503), (429,429), (500,503)])
def test_redacted_riot_errors(monkeypatch, code, expected):
    monkeypatch.setattr(roster, "fetch_json", MagicMock(side_effect=RiotApiError("SECRET", code, 120)))
    with pytest.raises(roster.RosterError) as exc:
        roster.resolve("Player#EUW")
    assert exc.value.status == expected
    assert "SECRET" not in exc.value.message


def test_cooldown_stops_lookup(monkeypatch):
    fetch = MagicMock()
    monkeypatch.setattr(roster, "fetch_json", fetch)
    monkeypatch.setattr(roster, "NEXT_LOOKUP", float("inf"))
    with pytest.raises(roster.RosterError):
        roster.resolve("Player#EUW")
    fetch.assert_not_called()


def connection(monkeypatch):
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    monkeypatch.setattr(roster, "get_gold_conn", lambda: conn)
    return conn, cur


def test_list_never_exposes_puuid(monkeypatch):
    conn, cur = connection(monkeypatch)
    cur.fetchall.return_value = [(1, "Player#EUW")]
    assert roster.roster_request("GET", "/roster")["players"] == [{"id":1,"riot_id":"Player#EUW"}]
    conn.close.assert_called_once()


def test_full_list_avoids_riot(monkeypatch):
    _, cur = connection(monkeypatch)
    cur.fetchone.return_value = (5,)
    monkeypatch.setenv("RIOT_LIVE_STREAM_MAX_PLAYERS", "5")
    resolve = MagicMock()
    monkeypatch.setattr(roster, "resolve", resolve)
    with pytest.raises(roster.RosterError) as exc:
        roster.roster_request("POST", "/roster", {"riot_id":"Player#EUW"})
    assert exc.value.status == 409
    resolve.assert_not_called()


def test_add_parameterized_and_idempotent(monkeypatch):
    _, cur = connection(monkeypatch)
    cur.fetchone.side_effect = [(0,), (7,)]
    monkeypatch.setattr(roster, "resolve", lambda _: ("puuid", "Player#EUW"))
    assert roster.roster_request("POST", "/roster", {"riot_id":"Player#EUW"})["id"] == 7
    call = cur.execute.call_args_list[-1]
    assert "ON CONFLICT(puuid)" in call.args[0]
    assert call.args[1] == ("puuid", "Player#EUW")
    identity_call = cur.execute.call_args_list[-2]
    assert "INSERT INTO audit.riot_tracked_players" in identity_call.args[0]
    assert "false, true, 'club'" in identity_call.args[0]
    assert "ON CONFLICT (puuid) DO UPDATE SET is_tracked=true" in identity_call.args[0]
    assert identity_call.args[1] == ("puuid", "Player#EUW")


def test_startup_repairs_existing_roster_and_enables_match_collection():
    cur = MagicMock()
    roster.init_roster(cur)
    repair = cur.execute.call_args_list[-2].args[0]
    assert "INSERT INTO audit.riot_tracked_players" in repair
    assert "FROM raw.riot_live_roster" in repair
    assert "false, false, 'live'" in repair
    assert "ON CONFLICT (puuid) DO NOTHING" in repair
    activation = cur.execute.call_args.args[0]
    assert "SET is_tracked=true" in activation
    assert "FROM raw.riot_live_roster" in activation
    assert "ELSE t.tracking_source END" in activation


def test_remove_only_roster(monkeypatch):
    _, cur = connection(monkeypatch)
    roster.roster_request("DELETE", "/roster/12")
    sql, params = cur.execute.call_args.args
    assert sql == "DELETE FROM raw.riot_live_roster WHERE id=%s"
    assert params == (12,)


def test_collector_uses_only_coach_roster():
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall.return_value = []
    assert select_players(conn, 5) == []
    assert "FROM raw.riot_live_roster" in cur.execute.call_args_list[0].args[0]
    assert "riot_tracked_players" not in str(cur.execute.call_args_list)


def test_api_requires_action_header(monkeypatch):
    forward = MagicMock(return_value={"id":1})
    monkeypatch.setattr(proxy, "forward", forward)
    with TestClient(app) as client:
        assert client.post("/api/live/roster", json={"riot_id":"Player#EUW"}).status_code == 403
        assert client.delete("/api/live/roster/1").status_code == 403
        forward.assert_not_called()
        response = client.post("/api/live/roster", json={"riot_id":"Player#EUW"},
                               headers={"X-MyLeague-Action":"roster"})
        assert response.status_code == 200


def test_cross_origin_preflight_not_enabled():
    with TestClient(app) as client:
        response = client.options("/api/live/roster", headers={"Origin":"https://other.invalid",
            "Access-Control-Request-Method":"POST", "Access-Control-Request-Headers":"x-myleague-action"})
        assert "access-control-allow-origin" not in response.headers
