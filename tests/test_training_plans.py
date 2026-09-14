import pytest
from fastapi.testclient import TestClient

from backend.main import app
from jobs.riot.training import validate


def goal(**changes):
    return dict(action='create', player='test-player', title='Lane', metric='gd_15',
                threshold=0, champion='', role='', starts_on='2026-01-01',
                ends_on='2026-01-07', **changes)


@pytest.mark.parametrize('field,value', [
    ('metric','unknown'), ('threshold',float('nan')), ('threshold',float('inf')),
    ('role','invalid'), ('title',' '), ('ends_on','2025-12-31'),
    ('ends_on','2028-01-01'), ('player',''),
])
def test_reject_invalid_goals(field,value):
    body=goal(); body[field]=value
    with pytest.raises(ValueError):
        validate(body)


def test_negative_deltas_allowed_but_negative_cs_rejected():
    body=goal(); body['threshold']=-100
    assert validate(body)['threshold']==-100
    body['metric']='cs_min'
    with pytest.raises(ValueError):
        validate(body)


def test_training_proxy_requires_action_and_validates(monkeypatch):
    calls=[]
    monkeypatch.setattr('backend.training.forward',lambda *args: calls.append(args) or [])
    with TestClient(app) as client:
        assert client.post('/api/training',json=goal()).status_code==403
        assert not calls
        assert client.post('/api/training',json=goal(),headers={'X-MyLeague-Action':'roster'}).status_code==200
        assert calls[-1][1]=='/training'
        assert client.get('/api/training',params={'player':'test-player'}).status_code==200
        assert calls[-1][2]['action']=='list'
