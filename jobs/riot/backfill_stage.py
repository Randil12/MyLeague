"""Resumable fixed historical windows, independent of the incremental watermark."""
import time
from datetime import timedelta
from pathlib import Path

from jobs.riot import euw_ingest as ingest

SCHEMA = """CREATE TABLE IF NOT EXISTS audit.riot_historical_progress (
    puuid TEXT PRIMARY KEY,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    next_offset INTEGER NOT NULL DEFAULT 0 CHECK (next_offset >= 0),
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)"""


def run_match_ingestion_stage(run_id, raw_dir, minio_prefix, lookback_days,
                              max_players, matches_per_player, max_matches_per_run,
                              ingest_timelines=False, budget_seconds=2100):
    conn = ingest.get_gold_conn()
    errors, seen = [], set()
    loaded = attempts = 0
    deadline = time.monotonic() + budget_seconds
    page_size = max(1, min(matches_per_player, 100))
    try:
        ingest.init_audit_tables(conn)
        with conn.cursor() as cur:
            cur.execute("UPDATE audit.pipeline_runs SET pipeline_name='riot_historical_backfill' WHERE run_id=%s", (run_id,))
            cur.execute('SELECT pg_try_advisory_lock(74120505)')
            if not cur.fetchone()[0]:
                raise RuntimeError('Historical backfill already running')
            cur.execute(SCHEMA)
            cur.execute("""SELECT t.puuid FROM audit.riot_tracked_players t
                LEFT JOIN audit.riot_historical_progress p USING(puuid)
                WHERE t.region='euw1' AND t.is_tracked AND NOT coalesce(p.completed,FALSE)
                ORDER BY (t.tracking_source IN ('club','academy')) DESC,
                    (p.puuid IS NOT NULL) DESC, p.updated_at NULLS LAST, t.puuid LIMIT %s""", (max_players,))
            players = [r[0] for r in cur.fetchall()]
        conn.commit()
        config = ingest.get_minio_config()
        for player in players:
            if attempts >= max_matches_per_run or time.monotonic() >= deadline:
                break
            end = ingest.utc_now()
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO audit.riot_historical_progress(puuid,window_start,window_end)
                    VALUES (%s,%s,%s) ON CONFLICT(puuid) DO NOTHING""",
                    (player, end-timedelta(days=lookback_days), end))
                cur.execute('SELECT window_start,window_end,next_offset FROM audit.riot_historical_progress WHERE puuid=%s', (player,))
                lower, upper, offset = cur.fetchone()
            conn.commit()
            while attempts < max_matches_per_run and time.monotonic() < deadline:
                try:
                    time.sleep(1.5)  # Leave headroom for the separately running live collector.
                    ids = ingest.get_match_ids_by_puuid(player, start_time=int(lower.timestamp()),
                        end_time=int(upper.timestamp()), queue=420, count=page_size, start=offset)
                    path = f'puuid={player}/start={int(lower.timestamp())}/end={int(upper.timestamp())}/offset={offset}/match_ids.json'
                    ingest.save_payload(ids, ingest.build_local_path(Path(raw_dir), 'historical_match_ids', path),
                                        ingest.build_key('historical_match_ids', path, minio_prefix), config)
                    seen.update(ids)
                    ingest.register_match_ids(conn, ids, player, run_id)
                    page_complete = True
                    for match_id in ids:
                        if attempts >= max_matches_per_run or time.monotonic() >= deadline:
                            page_complete = False
                            break
                        with conn.cursor() as cur:
                            cur.execute('SELECT status,timeline_status FROM audit.riot_match_ingestion WHERE match_id=%s', (match_id,))
                            status, timeline_status = cur.fetchone()
                        if status == 'not_found':
                            continue
                        if status == 'success':
                            if not ingest_timelines or timeline_status == 'success':
                                continue
                            attempts += 1
                            time.sleep(1.5)
                            error = ingest.ingest_timeline_payload(conn, Path(raw_dir), config, minio_prefix, match_id)
                        else:
                            attempts += 1
                            time.sleep(1.5)
                            success, error = ingest.ingest_match_payload(conn, Path(raw_dir), config,
                                minio_prefix, run_id, match_id, ingest_timelines)
                            loaded += int(success)
                        if error and error.get('error') != 'not_found (404)':
                            errors.append(error)
                            page_complete = False
                            break
                    if not page_complete:
                        break  # Retry this exact page; successful matches are deduplicated.
                    with conn.cursor() as cur:
                        cur.execute("""UPDATE audit.riot_historical_progress
                            SET next_offset=%s,completed=%s,updated_at=NOW() WHERE puuid=%s""",
                            (offset+len(ids), len(ids)<page_size, player))
                    conn.commit()
                    offset += len(ids)
                    if len(ids) < page_size:
                        break
                except Exception as exc:
                    conn.rollback()
                    errors.append({'stage':'historical_page', 'error':type(exc).__name__})
                    break
            if errors:
                break  # No hammering the API after a quota/authentication/storage failure.
        return {'run_id':run_id,'unique_match_ids_seen_this_run':len(seen),
                'matches_loaded':loaded,'match_error_count':len(errors),'match_error_samples':errors[:20]}
    except Exception as exc:
        conn.rollback()
        ingest.finish_pipeline_run(conn, run_id, 'failed', len(seen), loaded, 1, type(exc).__name__)
        raise
    finally:
        conn.close()  # Also releases the session advisory lock.
