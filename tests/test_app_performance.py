from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from backend import db, queries
from backend.main import app
from jobs.riot import player_names
from jobs.riot.client import RiotApiError


def test_new_readonly_routes_and_roster_validation(monkeypatch):
    query = MagicMock(return_value=[])
    monkeypatch.setattr(db, "query", query)
    with TestClient(app) as client:
        assert client.get('/api/champions').status_code == 200
        assert client.get('/api/leaderboard').status_code == 200
        assert query.call_args.args[0] == queries.LEADERBOARD
        assert client.get('/api/team/summary', params={'patch':'16.18','roster':['a']*5}).status_code == 422
        assert client.get('/api/team/summary', params={'patch':'16.18','roster':list('abcde')}).status_code == 200
        assert query.call_args.args[1]['roster'] == list('abcde')
        assert 'https://ddragon.leagueoflegends.com' in client.get('/healthz').headers['content-security-policy']


def test_training_no_longer_requires_academy_masteries():
    assert 'gold.fact_match_participant' in queries.DATASETS['training']
    assert 'puuid = :player' in queries.DATASETS['history']
    assert "LIMIT 1000" in queries.LEADERBOARD
    assert "tier IN ('CHALLENGER','GRANDMASTER','MASTER')" in queries.LEADERBOARD


def test_riot_names_persist_full_identity(monkeypatch):
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall.return_value = [('private/puuid',)]
    monkeypatch.setattr(player_names, 'get_gold_conn', lambda: conn)
    monkeypatch.setattr(player_names.time, 'sleep', lambda _: None)
    fetch = MagicMock(return_value={'gameName':'Player', 'tagLine':'EUW'})
    monkeypatch.setattr(player_names, 'fetch_json', fetch)
    assert player_names.run()['updated'] == 1
    assert cur.execute.call_args.args[1] == ('Player#EUW', 'private/puuid')
    assert 'private%2Fpuuid' in fetch.call_args.args[0]
    conn.close.assert_called_once()


def test_names_stop_on_rate_limit(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [('a',),('b',)]
    monkeypatch.setattr(player_names, 'get_gold_conn', lambda: conn)
    monkeypatch.setattr(player_names.time, 'sleep', lambda _: None)
    fetch = MagicMock(side_effect=RiotApiError('redacted', 429, 120))
    monkeypatch.setattr(player_names, 'fetch_json', fetch)
    assert player_names.run()['status'] == 'deferred'
    assert fetch.call_count == 1
