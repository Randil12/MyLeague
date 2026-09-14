from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from backend import db
from backend.main import app


def test_matchup_opponent_is_bound_and_same_champion_rejected(monkeypatch):
    query = MagicMock(return_value=[])
    monkeypatch.setattr(db, 'query', query)
    with TestClient(app) as client:
        params = {'patch':'16.18','champion':'Darius','opponent':'Aatrox','minimum':1,'role':'TOP'}
        assert client.get('/api/data/matchups', params=params).status_code == 200
        sql, bound = query.call_args.args
        assert 'opponent = :opponent' in sql
        assert bound['champion'] == 'Darius' and bound['opponent'] == 'Aatrox'
        assert 'a.team_id <> b.team_id' in sql and 'a.team_position = b.team_position' in sql
        assert client.get('/api/data/matchups', params={**params,'opponent':'Darius'}).status_code == 422
        assert client.get('/api/data/matchups', params={**params,'opponent':'x'*101}).status_code == 422
