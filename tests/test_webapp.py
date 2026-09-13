"""API tests without a live database: safe failure, validation and SQL binding."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from webapp import server


@pytest.fixture
def client():
    with TestClient(server.app) as value:
        yield value


def test_shell_and_assets(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'lang="fr"' in response.text
    assert "MYLEAGUE" in response.text
    assert "DATA_ANALYST_PASSWORD" not in response.text
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    for path in ("/static/app.js", "/static/style.css", "/healthz"):
        assert client.get(path).status_code == 200


def test_patches_sort_numerically(client, monkeypatch):
    monkeypatch.setattr(server, "query", lambda *_: [{"patch": p} for p in ["16.9", "16.10", "15.24"]])
    assert client.get("/api/patches").json() == [
        {"patch": "16.10"}, {"patch": "16.9"}, {"patch": "15.24"},
    ]


@pytest.mark.parametrize("dataset", list(server.DATASETS))
def test_every_dataset_uses_bound_parameters(client, monkeypatch, dataset):
    calls = []

    def read(sql, params):
        calls.append((sql, params))
        return []

    monkeypatch.setattr(server, "query", read)
    payload = "16.1' OR 1=1 --"
    response = client.get(f"/api/data/{dataset}", params={"patch": payload})
    assert response.status_code == 200
    assert response.json() == []
    assert payload not in calls[0][0]
    assert calls[0][1]["patch"] == payload
    assert response.headers["cache-control"] == "no-store"


def test_rejects_unknown_dataset_and_invalid_params(client, monkeypatch):
    def no_query(*args):
        pytest.fail("Invalid input must not reach PostgreSQL")

    monkeypatch.setattr(server, "query", no_query)
    assert client.get("/api/data/secret").status_code == 404
    assert client.get("/api/data/meta").status_code == 422
    assert client.get("/api/data/meta", params={"patch": "x" * 33}).status_code == 422
    assert client.post("/api/data/meta", json={"sql": "DROP TABLE gold"}).status_code == 405


def test_database_failure_does_not_leak_details(client, monkeypatch):
    def fail(*args):
        raise OperationalError("SELECT private", {}, Exception("password=DO_NOT_EXPOSE"))

    monkeypatch.setattr(server, "query", fail)
    response = client.get("/api/data/meta?patch=16.1")
    assert response.status_code == 503
    assert "Données indisponibles" in response.json()["detail"]
    assert "DO_NOT_EXPOSE" not in response.text
    assert "SELECT private" not in response.text
    assert client.get("/").status_code == 200


def test_decimal_and_date_serialization(client, monkeypatch):
    monkeypatch.setattr(server, "query", lambda *_: [{
        "winrate": Decimal("0.5123"), "last_game_at": datetime(2026, 9, 13, tzinfo=timezone.utc),
        "kda": None,
    }])
    row = client.get("/api/data/summary?patch=16.1").json()[0]
    assert row["winrate"] == .5123
    assert row["last_game_at"].startswith("2026-09-13")
    assert row["kda"] is None


def test_engine_is_readonly_and_bounded(monkeypatch):
    config = {}

    def create(url, **kwargs):
        config.update(kwargs)
        assert url.username == "data_analyst"
        return object()

    server.get_engine.cache_clear()
    monkeypatch.setenv("DATA_ANALYST_USER", "data_analyst")
    monkeypatch.setattr(server, "create_engine", create)
    try:
        server.get_engine()
        assert "default_transaction_read_only=on" in config["connect_args"]["options"]
        assert "statement_timeout=8000" in config["connect_args"]["options"]
        assert config["max_overflow"] == 2
    finally:
        server.get_engine.cache_clear()
