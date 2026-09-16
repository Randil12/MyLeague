"""Focused tests for the new API; no real database or secrets required."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from backend import db, queries
from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_numeric_patch_order(client, monkeypatch):
    monkeypatch.setattr(db, "query", lambda *_: [{"patch": p} for p in ["16.9", "16.10", "15.24"]])
    assert [r["patch"] for r in client.get("/api/patches").json()] == ["16.10", "16.9", "15.24"]


@pytest.mark.parametrize("name", queries.DATASETS)
def test_allowlisted_queries_bind_input(client, monkeypatch, name):
    calls = []

    def query(sql, params):
        calls.append((sql, params))
        return [{"winrate": Decimal("0.55")}]

    monkeypatch.setattr(db, "query", query)
    value = "16.1' OR 1=1 --"
    response = client.get(f"/api/data/{name}", params={"patch": value, "player": "test-player"})
    assert response.status_code == 200
    assert response.json()[0]["winrate"] == .55
    assert value not in calls[0][0]
    assert calls[0][1]["patch"] == value
    assert response.headers["cache-control"] == "no-store"


def test_invalid_parameters_do_not_hit_database(client, monkeypatch):
    def fail(*_):
        pytest.fail("Invalid request reached database")
    monkeypatch.setattr(db, "query", fail)
    for path in ["/api/data/unknown?patch=16.1", "/api/data/history?patch=16.1",
                 "/api/data/matchups?patch=16.1&minimum=0", "/api/data/matchups?patch=16.1&role=INVALID"]:
        assert client.get(path).status_code in {404, 422}
    assert client.get("/api/team", params=[("patch", "16.1"), *[("roster", "same")] * 5]).status_code == 422
    assert client.get("/api/team", params={"patch": "16.1", "roster": "only-one"}).status_code == 422


def test_team_requires_exact_five_and_bound_roster(client, monkeypatch):
    calls = []
    monkeypatch.setattr(db, "query", lambda sql, params: calls.append(params) or [])
    response = client.get("/api/team", params=[("patch", "16.1"), *[("roster", str(i)) for i in range(5)]])
    assert response.status_code == 200
    assert calls[0]["roster"] == [str(i) for i in range(5)]
    assert "count(DISTINCT puuid) = cardinality(CAST(:roster AS text[]))" in queries.TEAM
    assert "match_id, team_id, patch" in queries.TEAM


def test_database_error_is_redacted(client, monkeypatch):
    def fail(*_):
        raise OperationalError("private SQL", {}, Exception("password=SECRET"))
    monkeypatch.setattr(db, "query", fail)
    response = client.get("/api/patches")
    assert response.status_code == 503
    assert "SECRET" not in response.text
    assert "private SQL" not in response.text
    assert client.get("/healthz").status_code == 200


def test_matchups_reject_ambiguous_roles():
    assert "a.role_count = 1 AND b.role_count = 1" in queries.PAIRED
    assert "a.team_id <> b.team_id" in queries.PAIRED
    assert "a.team_position = b.team_position" in queries.PAIRED
