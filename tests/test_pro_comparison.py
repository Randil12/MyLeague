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


def test_multi_player_selection_and_role_filter(monkeypatch):
    query = MagicMock(return_value=[])
    monkeypatch.setattr(db, 'query', query)
    with TestClient(app) as client:
        for endpoint in ['compare', 'history']:
            for players in [['A', 'B'], ['A', 'B', 'C', 'D', 'E']]:
                response = client.get(f'/api/pro/{endpoint}', params={'year': 2026, 'selected_players': players, 'role': 'Top'})
                assert response.status_code == 200
                sql, params = query.call_args.args
                assert params['selected_players'] == players
                assert params['role'] == 'Top'
                assert 'ANY(CAST(:selected_players AS text[]))' in sql
            for players in [['A'], ['A', 'A'], ['A', ''], ['A', 'B', 'C', 'D', 'E', 'F']]:
                assert client.get(f'/api/pro/{endpoint}', params={'year': 2026, 'selected_players': players}).status_code == 422
        assert client.get('/api/pro/players', params={'year': 2026, 'role': 'Top'}).status_code == 200
        assert query.call_args.args[1]['role'] == 'Top'


def test_verified_extra_scoreboard_fields(monkeypatch):
    query=MagicMock(return_value=[])
    monkeypatch.setattr(cargo.time, 'sleep', lambda _:None)
    fake=SimpleNamespace(cargo_client=SimpleNamespace(query=query))
    cargo.fetch_scoreboard_players(fake,'2026-01-01',until_iso='2026-01-02')
    fields=query.call_args.kwargs['fields'].split(',')
    for field in ['Items','Trinket','KeystoneRune','PrimaryTree','SecondaryTree','Runes','DamageToChampions','VisionScore']:
        assert field in fields
    assert 'GoldAt15' not in fields


def test_coaching_sources_are_separate_and_bound(monkeypatch):
    query = MagicMock(return_value=[])
    monkeypatch.setattr(db, 'query', query)
    with TestClient(app) as client:
        params = {'year': 2026, 'player': "bad' OR 1=1 --"}
        assert client.get('/api/pro/coaching', params={**params, 'source': 'invalid'}).status_code == 422
        for source, table, excluded in [('pro', 'gold_pro_player_games', 'fact_match_participant'),
                                        ('soloq', 'fact_match_participant', 'gold_pro_player_games')]:
            assert client.get('/api/pro/coaching', params={**params, 'source': source}).status_code == 200
            sql, bound = query.call_args.args
            assert table in sql and excluded not in sql
            assert params['player'] not in sql and bound == params
            assert 'nullif' in sql and 'games_with_cs_min' in sql
        assert client.get('/api/pro/accounts', params=params).status_code == 200
        assert 'reported_soloqueue_accounts' in query.call_args.args[0]
        assert client.get('/api/pro/draft/patches').status_code == 200
        assert client.get('/api/pro/draft', params={'patch': '16.18'}).status_code == 200
        assert 'gold_pro_champion_draft_by_patch' in query.call_args.args[0]
        assert client.get('/api/pro/draft').status_code == 422
