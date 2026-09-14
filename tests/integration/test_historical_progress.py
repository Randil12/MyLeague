"""Actual PostgreSQL checkpoint and MinIO archive; external Riot calls simulated."""
from unittest.mock import MagicMock

from jobs.riot import backfill_stage


def test_empty_history_is_archived_and_checkpointed(infrastructure, monkeypatch, tmp_path):
    conn, s3 = infrastructure
    player = 'ci-historical-progress'
    with conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO audit.riot_tracked_players
            (region,puuid,first_seen_master_plus_at,last_seen_master_plus_at,tracking_source,last_match_ingestion_at)
            VALUES ('euw1',%s,NOW(),NOW(),'club','2026-09-14T00:00:00Z')""", (player,))
    api = MagicMock(return_value=[])
    monkeypatch.setattr(backfill_stage.ingest, 'get_match_ids_by_puuid', api)
    monkeypatch.setattr(backfill_stage.time, 'sleep', lambda _: None)
    try:
        result = backfill_stage.run_match_ingestion_stage('ci-history',tmp_path,'bronze/riot',60,1,100,5)
        assert result['match_error_count'] == 0
        with conn, conn.cursor() as cur:
            cur.execute("""SELECT completed,next_offset,EXTRACT(day FROM window_end-window_start)
                FROM audit.riot_historical_progress WHERE puuid=%s""", (player,))
            assert cur.fetchone() == (True, 0, 60)
            cur.execute('SELECT last_match_ingestion_at::date::text FROM audit.riot_tracked_players WHERE puuid=%s', (player,))
            assert cur.fetchone()[0] == '2026-09-14'
        assert api.call_args.kwargs['start'] == 0
        objects = s3.list_objects_v2(Bucket='ci-live',Prefix=f'bronze/riot/region=euw1/historical_match_ids/puuid={player}/')
        assert objects['KeyCount'] == 1
    finally:
        with conn, conn.cursor() as cur:
            cur.execute('DELETE FROM audit.riot_tracked_players WHERE puuid=%s', (player,))
            cur.execute('DELETE FROM audit.riot_historical_progress WHERE puuid=%s', (player,))
