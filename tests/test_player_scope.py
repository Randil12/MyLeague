import json
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from backend import db, queries
from backend.main import app


def test_all_patches_only_allowed_for_player_analyses(monkeypatch):
    query=MagicMock(return_value=[])
    monkeypatch.setattr(db,'query',query)
    with TestClient(app) as client:
        for dataset in ['training','player_summary','player_matchups','history','progress','durations']:
            response=client.get('/api/data/'+dataset,params={'patch':'','player':'test-player'})
            assert response.status_code==200
            assert query.call_args.args[1]['patch']==''
        for dataset in ['draft','matchups','compositions']:
            assert client.get('/api/data/'+dataset,params={'patch':''}).status_code==422


def test_grafana_and_app_use_same_patch_count_source():
    root=Path(__file__).resolve().parents[1]
    dashboard=json.loads((root/'grafana/provisioning/dashboards/meta_lol.json').read_text(encoding='utf8'))
    counters=[target['rawSql'] for panel in dashboard['panels'] for target in panel.get('targets',[])
              if 'total_matches' in target.get('rawSql','')]
    assert len(counters)==1
    assert 'gold.gold_patch_summary' in counters[0]
    assert 'gold.gold_patch_summary' in queries.PATCHES
