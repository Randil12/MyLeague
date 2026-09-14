"""Bounded recent soloQ collection for the explicit coach roster, not the ladder."""
import time
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from jobs.riot import euw_ingest as ingest, load_raw
from jobs.riot.live_roster import init_roster


def run(raw_dir=ingest.DEFAULT_RAW_DIR, matches_per_player=50, lookback_days=30):
    if not 1 <= matches_per_player <= 100 or not 1 <= lookback_days <= 60:
        raise ValueError('Invalid coach collection window')
    conn = ingest.get_gold_conn()
    run_id = 'coach-' + uuid4().hex
    seen, attempted = set(), set()
    loaded = 0
    started = False
    try:
        ingest.init_audit_tables(conn)
        with conn.cursor() as cur:
            cur.execute('SELECT pg_try_advisory_lock(74120506)')
            if not cur.fetchone()[0]:
                raise RuntimeError('Coach collection already running')
            init_roster(cur)
            cur.execute('SELECT puuid FROM raw.riot_live_roster ORDER BY created_at, id LIMIT 10')
            players = [r[0] for r in cur.fetchall()]
        conn.commit()
        ingest.start_pipeline_run(conn, run_id)
        started = True
        with conn.cursor() as cur:
            cur.execute("UPDATE audit.pipeline_runs SET pipeline_name='riot_coach_matches' WHERE run_id=%s", (run_id,))
        conn.commit()
        config = ingest.get_minio_config()
        end = ingest.utc_now()
        lower = int((end - timedelta(days=lookback_days)).timestamp())
        for player in players:
            # Re-read a bounded recent window: no watermark that could skip games
            # when the page is full, or when a previous attempt failed midway.
            time.sleep(1.5)
            ids = ingest.get_match_ids_by_puuid(player, start_time=lower,
                end_time=int(end.timestamp()), queue=420, count=matches_per_player)
            path = f'puuid={player}/run_id={run_id}/match_ids.json'
            ingest.save_payload(ids, ingest.build_local_path(Path(raw_dir), 'coach_match_ids', path),
                ingest.build_key('coach_match_ids', path), config)
            seen.update(ids)
            ingest.register_match_ids(conn, ids, player, run_id)
            for match_id in ids:
                if match_id in attempted:
                    continue
                attempted.add(match_id)
                with conn.cursor() as cur:
                    cur.execute('SELECT status,timeline_status FROM audit.riot_match_ingestion WHERE match_id=%s', (match_id,))
                    status, timeline = cur.fetchone()
                if status == 'not_found':
                    continue
                if status == 'success':
                    if timeline == 'success':
                        continue
                    time.sleep(1.5)
                    error = ingest.ingest_timeline_payload(conn, Path(raw_dir), config,
                        ingest.DEFAULT_MINIO_PREFIX, match_id)
                else:
                    time.sleep(1.5)
                    success, error = ingest.ingest_match_payload(conn, Path(raw_dir), config,
                        ingest.DEFAULT_MINIO_PREFIX, run_id, match_id, True)
                    loaded += int(success)
                if error and error.get('error') != 'not_found (404)':
                    # Existing client has already retried/backed off. Stop instead
                    # of hammering the API; the next run reuses archived matches.
                    raise RuntimeError('Coach match/timeline collection failed; inspect Riot ingestion audit')
        result = load_raw.run(raw_dir=raw_dir, batch_limit=max(1, len(seen)), match_ids=sorted(seen))
        if result['error_count'] or result['missing_bronze_files']:
            raise RuntimeError('Coach raw load incomplete; next run will retry')
        ingest.finish_pipeline_run(conn, run_id, 'success', len(seen), loaded, 0)
        return {'players':len(players), 'matches_seen':len(seen), 'matches_downloaded':loaded,
                'loaded_to_raw':result['loaded_to_raw'], 'timelines_loaded_to_raw':result['timelines_loaded_to_raw']}
    except Exception as exc:
        conn.rollback()
        if started:
            ingest.finish_pipeline_run(conn, run_id, 'failed', len(seen), loaded, 1, type(exc).__name__)
        raise
    finally:
        conn.close()
