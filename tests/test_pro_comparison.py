from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from backend import db
from backend.main import app
from jobs.leaguepedia import client as cargo


def test_pro_endpoints_validate_and_bind_filters(monkeypatch):
    query=MagicMock(return_value=[])
    monkeypatch.setattr(db, 'query', query)
    with TestClient(app) as client:
        assert client.get('/api/pro/years').status_code==200
        assert client.get('/api/pro/options',params={'year':2026}).status_code==200
        assert client.get('/api/pro/players',params={'year':2026}).status_code==200
        assert client.get('/api/pro/compare',params={'year':2026,'player_a':'A','player_b':'A'}).status_code==422
        assert client.get('/api/pro/history',params={'year':2026,'player_a':'A'}).status_code==422
        assert client.get('/api/pro/players',params={'year':1999}).status_code==422
        malicious="' OR 1=1 --"
        result=client.get('/api/pro/compare',params={'year':2026,'player_a':'A','player_b':'B','region':malicious})
        assert result.status_code==200
        sql,params=query.call_args.args
        assert malicious not in sql and params['region']==malicious
        assert 'riot_matches' not in sql
        assert 'gold_pro_player_games' in sql
        assert 'avg(gold)' in sql and 'gold_at_15' not in sql


def test_verified_extra_scoreboard_fields(monkeypatch):
    query=MagicMock(return_value=[])
    monkeypatch.setattr(cargo.time, 'sleep', lambda _:None)
    fake=SimpleNamespace(cargo_client=SimpleNamespace(query=query))
    cargo.fetch_scoreboard_players(fake,'2026-01-01',until_iso='2026-01-02')
    fields=query.call_args.kwargs['fields'].split(',')
    for field in ['Items','Trinket','KeystoneRune','PrimaryTree','SecondaryTree','Runes','DamageToChampions','VisionScore']:
        assert field in fields
    assert 'GoldAt15' not in fields
