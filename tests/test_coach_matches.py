from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from jobs.riot import coach_matches as coach
from jobs.riot import load_raw


@pytest.fixture
def setup(monkeypatch):
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect = [(True,), ('pending', None), ('success', 'success')]
    cur.fetchall.return_value = [('added-player',), ('also-added',)]
    monkeypatch.setattr(coach.ingest, 'get_gold_conn', lambda: conn)
    monkeypatch.setattr(coach, 'init_roster', MagicMock())
    monkeypatch.setattr(coach.time, 'sleep', lambda _: None)
    for name in ['init_audit_tables','start_pipeline_run','finish_pipeline_run',
                 'save_payload','register_match_ids']:
        monkeypatch.setattr(coach.ingest, name, MagicMock())
    monkeypatch.setattr(coach.ingest, 'get_minio_config', lambda: {})
    monkeypatch.setattr(coach.ingest, 'utc_now', lambda: datetime(2026,9,14,tzinfo=timezone.utc))
    fetch = MagicMock(return_value=['EUW1_1','EUW1_2'])
    monkeypatch.setattr(coach.ingest, 'get_match_ids_by_puuid', fetch)
    download = MagicMock(return_value=(True,None))
    monkeypatch.setattr(coach.ingest, 'ingest_match_payload', download)
    loader = MagicMock(return_value={'error_count':0,'missing_bronze_files':0,
        'loaded_to_raw':2,'timelines_loaded_to_raw':2})
    monkeypatch.setattr(coach.load_raw, 'run', loader)
    return conn,cur,fetch,download,loader


def test_only_roster_bounded_history_dedup_and_targeted_load(setup, tmp_path):
    conn,cur,fetch,download,loader = setup
    result = coach.run(tmp_path)
    assert result['players'] == 2 and result['matches_downloaded'] == 1
    assert [c.args[0] for c in fetch.call_args_list] == ['added-player','also-added']
    assert fetch.call_args.kwargs['queue'] == 420 and fetch.call_args.kwargs['count'] == 50
    assert fetch.call_args.kwargs['end_time']-fetch.call_args.kwargs['start_time'] == 30*86400
    download.assert_called_once()
    assert download.call_args.args[-1] is True
    assert loader.call_args.kwargs['match_ids'] == ['EUW1_1','EUW1_2']
    assert any('FROM raw.riot_live_roster' in call.args[0] for call in cur.execute.call_args_list)
    coach.ingest.finish_pipeline_run.assert_called_once()
    conn.close.assert_called_once()


def test_error_stops_before_next_player_and_is_audited(setup, tmp_path):
    conn,_,fetch,download,loader = setup
    download.return_value = (False, {'error':'quota exhausted'})
    with pytest.raises(RuntimeError, match='collection failed'):
        coach.run(tmp_path)
    fetch.assert_called_once()
    loader.assert_not_called()
    assert coach.ingest.finish_pipeline_run.call_args.args[2] == 'failed'
    conn.close.assert_called_once()


def test_empty_roster_never_calls_riot(setup, tmp_path):
    _,cur,fetch,download,loader = setup
    cur.fetchall.return_value = []
    assert coach.run(tmp_path)['players'] == 0
    fetch.assert_not_called()
    download.assert_not_called()
    assert loader.call_args.kwargs['match_ids'] == []


def test_targeted_load_sql_preserves_empty_scope():
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall.return_value = []
    for select in [load_raw.select_matches_to_load, load_raw.select_timelines_to_load]:
        select(conn, 100, [])
        assert cur.execute.call_args.args[1] == ('euw1', [], [], 100)
        assert 'ANY(%s::text[])' in cur.execute.call_args.args[0]
