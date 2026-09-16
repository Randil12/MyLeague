from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from backend import db
from backend.main import app


def test_collective_sizes_and_all_patches(monkeypatch):
    query = MagicMock(return_value=[])
    monkeypatch.setattr(db, 'query', query)
    with TestClient(app) as client:
        for endpoint, minimum in [('/api/team', 2), ('/api/team/summary', 1)]:
            for size in range(1, 7):
                for patch in ['', '16.18']:
                    response = client.get(endpoint, params={'patch': patch, 'roster': list('abcdef')[:size]})
                    assert response.status_code == (200 if minimum <= size <= 5 else 422)
                    if response.status_code == 200:
                        assert query.call_args.args[1]['patch'] == patch
            assert client.get(endpoint, params={'patch': '', 'roster': ['a', 'a']}).status_code == 422
            assert client.get(endpoint, params={'patch': '', 'roster': ['a', '']}).status_code == 422
