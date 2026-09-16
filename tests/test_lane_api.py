from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from backend import db
from backend.main import app


def test_lane_requires_player_patch_and_binds_values(monkeypatch):
    query=MagicMock(return_value=[])
    monkeypatch.setattr(db,'query',query)
    with TestClient(app) as client:
        assert client.get('/api/lane').status_code == 422
        assert client.get('/api/lane',params={'player':'','patch':'16.18'}).status_code == 422
        params={'player':"x' OR 1=1 --",'patch':'16.18'}
        assert client.get('/api/lane',params=params).status_code == 200
        sql, bound=query.call_args.args
        assert bound==params and params['player'] not in sql
        assert 'gold.gold_coach_roster' in sql and 'LIMIT 200' not in sql
        assert client.get('/api/lane',params={**params,'patch':''}).status_code==200
