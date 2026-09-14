from datetime import datetime, timezone
from unittest.mock import MagicMock

from jobs.riot import backfill_stage as stage
from jobs.riot import client


def setup(monkeypatch, pages, states=None):
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    state = {'offset': 0, 'updates': [], 'sql': [], 'statuses': states or {}}

    def execute(sql, params=None):
        state['sql'].append(sql)
        if 'pg_try_advisory_lock' in sql:
            cur.fetchone.return_value = (True,)
        elif 'SELECT t.puuid' in sql:
            cur.fetchall.return_value = [('player',)]
        elif 'SELECT window_start' in sql:
            cur.fetchone.return_value = (now, now, state['offset'])
        elif 'SELECT status,timeline_status' in sql:
            cur.fetchone.return_value = state['statuses'].get(params[0], ('pending', None))
        elif 'SET next_offset' in sql:
            state['updates'].append(params)
            state['offset'] = params[0]

    cur.execute.side_effect = execute
    monkeypatch.setattr(stage.ingest, 'get_gold_conn', lambda: conn)
    for name in ['init_audit_tables', 'get_minio_config', 'save_payload', 'register_match_ids', 'finish_pipeline_run']:
        monkeypatch.setattr(stage.ingest, name, MagicMock())
    monkeypatch.setattr(stage.time, 'sleep', lambda _: None)
    api = MagicMock(side_effect=pages)
    monkeypatch.setattr(stage.ingest, 'get_match_ids_by_puuid', api)
    ingest = MagicMock(return_value=(True, None))
    monkeypatch.setattr(stage.ingest, 'ingest_match_payload', ingest)
    monkeypatch.setattr(stage.ingest, 'ingest_timeline_payload', MagicMock(return_value=None))
    return state, api, ingest


def run(**kwargs):
    return stage.run_match_ingestion_stage('test', '/tmp/test', 'bronze/riot', 60, 10, 2, **kwargs)


def test_paginates_fixed_window_without_incremental_watermark(monkeypatch):
    state, api, ingest = setup(monkeypatch, [['a', 'b'], ['c']])
    result = run(max_matches_per_run=10)
    assert result['matches_loaded'] == 3
    assert [c.kwargs['start'] for c in api.call_args_list] == [0, 2]
    assert state['updates'][-1] == (3, True, 'player')
    assert all('last_match_ingestion_at' not in sql for sql in state['sql'])
    assert ingest.call_count == 3


def test_budget_does_not_advance_partial_page(monkeypatch):
    state, _, _ = setup(monkeypatch, [['a', 'b']])
    assert run(max_matches_per_run=1)['matches_loaded'] == 1
    assert state['updates'] == []


def test_failed_match_keeps_page_for_retry(monkeypatch):
    state, _, ingest = setup(monkeypatch, [['a', 'b']])
    ingest.return_value = (False, {'error': 'quota'})
    assert run(max_matches_per_run=10)['match_error_count'] == 1
    assert state['updates'] == []


def test_interrupted_page_resumes_and_skips_already_saved_match(monkeypatch):
    state, api, ingest = setup(monkeypatch, [['a','b'], ['a','b'], []])
    run(max_matches_per_run=1)
    state['statuses']['a'] = ('success','success')
    run(max_matches_per_run=10)
    assert [c.kwargs['start'] for c in api.call_args_list] == [0,0,2]
    assert ingest.call_count == 2
    assert state['updates'][-1] == (2,True,'player')


def test_existing_matches_and_terminal_404_are_skipped(monkeypatch):
    state, _, ingest = setup(monkeypatch, [['a', 'b'], []],
                             {'a': ('success', 'success'), 'b': ('not_found', None)})
    run(max_matches_per_run=10, ingest_timelines=True)
    ingest.assert_not_called()
    assert state['updates'][-1][1] is True


def test_missing_timeline_is_retried_without_refetching_match(monkeypatch):
    state, _, ingest = setup(monkeypatch, [['a']], {'a': ('success', None)})
    run(max_matches_per_run=10, ingest_timelines=True)
    ingest.assert_not_called()
    stage.ingest.ingest_timeline_payload.assert_called_once()
    assert state['updates'][-1][1] is True


def test_riot_offset_is_forwarded(monkeypatch):
    fetch = MagicMock(return_value=[])
    monkeypatch.setattr(client, 'fetch_json', fetch)
    client.get_match_ids_by_puuid('player', 1, 2, count=100, start=200)
    assert 'start=200' in fetch.call_args.args[0]
