"""Continuous spectator polling. Run one replica; SQL lock enforces a single collector."""
from __future__ import annotations

import json
import logging
import os
import signal
from datetime import timedelta
from pathlib import Path
from threading import Event
from time import monotonic

from psycopg2 import sql

from jobs.riot.client import RiotApiError, get_active_game_by_puuid
from jobs.riot.euw_ingest import (
    get_gold_conn,
    get_minio_config,
    is_minio_enabled,
    upload_json_to_minio,
    utc_now,
)
from jobs.riot.live_games import LIVE_LOCK_ID, init_live_schema, insert_live_snapshot
from jobs.riot.live_roster import init_roster, start_server

LOCK_ID = LIVE_LOCK_ID
HEALTH_FILE = Path("/tmp/myleague-live-heartbeat")
logger = logging.getLogger(__name__)


def init_schema(conn):
    init_live_schema(conn)
    with conn.cursor() as cur:
        init_roster(cur)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS raw.riot_live_player_state (
                puuid text PRIMARY KEY, player_name text NOT NULL, selected boolean NOT NULL DEFAULT true,
                status text NOT NULL, game_id bigint, checked_at timestamptz NOT NULL,
                stored_at timestamptz NOT NULL DEFAULT clock_timestamp(), error_code text,
                request_ms integer NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS audit.riot_live_service (
                singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
                heartbeat_at timestamptz NOT NULL, next_poll_at timestamptz,
                status text NOT NULL, interval_seconds integer NOT NULL,
                selected_players integer NOT NULL, polled integer NOT NULL, errors integer NOT NULL
            );
            CREATE OR REPLACE VIEW gold.gold_coach_roster AS
            SELECT puuid, riot_id AS player_name FROM raw.riot_live_roster;
            CREATE OR REPLACE VIEW gold.gold_live_service AS
            SELECT heartbeat_at, next_poll_at, status, interval_seconds, selected_players, polled, errors,
                now() > greatest(heartbeat_at + interval '3 minutes',
                                 coalesce(next_poll_at, heartbeat_at) + interval '2 minutes') AS is_stale
            FROM audit.riot_live_service;
            CREATE OR REPLACE VIEW gold.gold_live_players AS
            SELECT p.player_name, p.status, p.game_id::text AS game_id, p.checked_at, p.stored_at,
                p.error_code, p.request_ms,
                round(extract(epoch FROM (p.stored_at - p.checked_at)) * 1000) AS storage_delay_ms,
                now() - p.checked_at > make_interval(secs => greatest(180, coalesce(s.interval_seconds,60)*3))
                    AS is_stale,
                g.game_started_at, g.observed_at AS first_observed_at,
                (SELECT string_agg(coalesce(c.name, '#' || (v->>'championId')), ', ' ORDER BY v->>'championId')
                 FROM jsonb_array_elements(coalesce(g.payload->'participants','[]')) v
                 LEFT JOIN reference.dim_champion_latest c ON c.champion_key::text = v->>'championId'
                 WHERE v->>'teamId' = '100') AS blue_team,
                (SELECT string_agg(coalesce(c.name, '#' || (v->>'championId')), ', ' ORDER BY v->>'championId')
                 FROM jsonb_array_elements(coalesce(g.payload->'participants','[]')) v
                 LEFT JOIN reference.dim_champion_latest c ON c.champion_key::text = v->>'championId'
                 WHERE v->>'teamId' = '200') AS red_team
            FROM raw.riot_live_player_state p
            LEFT JOIN raw.riot_live_game_snapshots g ON g.game_id = p.game_id
            LEFT JOIN audit.riot_live_service s ON s.singleton = true
            WHERE p.selected AND EXISTS (SELECT 1 FROM raw.riot_live_roster r WHERE r.puuid=p.puuid);
        """)
        cur.execute(sql.SQL("GRANT SELECT ON gold.gold_live_players, gold.gold_live_service, gold.gold_coach_roster TO {}").format(
            sql.Identifier(os.getenv("DATA_ANALYST_USER", "data_analyst"))))
    conn.commit()


def heartbeat(conn, status, interval, selected, polled, errors, wait=0):
    now = utc_now()
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO audit.riot_live_service
            VALUES (true,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (singleton) DO UPDATE SET
            heartbeat_at=EXCLUDED.heartbeat_at, next_poll_at=EXCLUDED.next_poll_at,
            status=EXCLUDED.status, interval_seconds=EXCLUDED.interval_seconds,
            selected_players=EXCLUDED.selected_players, polled=EXCLUDED.polled, errors=EXCLUDED.errors""",
                    (now, now + timedelta(seconds=wait), status, interval, selected, polled, errors))
    conn.commit()


def select_players(conn, limit):
    with conn.cursor() as cur:
        cur.execute("""SELECT puuid, riot_id FROM raw.riot_live_roster
            ORDER BY created_at, id LIMIT %s""", (limit,))
        players = cur.fetchall()
        cur.execute("UPDATE raw.riot_live_player_state SET selected=false WHERE selected")
        # Keep known observations for selected players until their next successful check.
        cur.execute("UPDATE raw.riot_live_player_state SET selected=true WHERE puuid = ANY(%s)",
                    ([p[0] for p in players],))
    conn.commit()
    return players


def store_state(conn, puuid, name, status, observed, request_ms, game_id=None, error=None):
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO raw.riot_live_player_state
            (puuid,player_name,status,game_id,checked_at,error_code,request_ms)
            VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (puuid) DO UPDATE SET
            player_name=EXCLUDED.player_name,status=EXCLUDED.status,game_id=EXCLUDED.game_id,
            checked_at=EXCLUDED.checked_at,stored_at=clock_timestamp(),error_code=EXCLUDED.error_code,
            request_ms=EXCLUDED.request_ms,selected=true""",
                    (puuid, name, status, game_id, observed, error, request_ms))
    conn.commit()


def archive_game(conn, game, puuid, config):
    game_id = game.get("gameId")
    if not isinstance(game_id, int) or game_id <= 0:
        raise ValueError("Invalid spectator gameId")
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM raw.riot_live_game_snapshots WHERE game_id=%s", (game_id,))
        exists = cur.fetchone() is not None
    if not exists:
        # Archive before SQL deduplication: storage failures are retried on the next poll.
        upload_json_to_minio(
            game, bucket=str(config["bucket"]), key=f"bronze/riot/live_games/game_id={game_id}/active_game.json",
            endpoint_url=str(config["endpoint_url"]), access_key_id=str(config["access_key_id"]),
            secret_access_key=str(config["secret_access_key"]), region_name=str(config["region_name"]),
        )
        insert_live_snapshot(conn, game, puuid)


def poll_cycle(conn, config, stop, interval, limit):
    players = select_players(conn, limit)
    begin = monotonic()
    errors = polled = 0
    cooldown = 0.0
    cycle_status = "idle" if not players else "running"
    heartbeat(conn, cycle_status, interval, len(players), polled, errors)
    for puuid, name in players:
        if stop.is_set():
            break
        # The successful write also checks the connection holding the advisory lock.
        heartbeat(conn, "polling", interval, len(players), polled, errors)
        request_start = monotonic()
        try:
            game = get_active_game_by_puuid(puuid, retries=0)
            observed = utc_now()
            request_ms = int((monotonic() - request_start) * 1000)
            game_id = None
            if game is None:
                status = "not_in_game"
            elif game.get("gameQueueConfigId") != 420:
                status = "other_queue"
            else:
                archive_game(conn, game, puuid, config)
                status, game_id = "in_game", game["gameId"]
            store_state(conn, puuid, name, status, observed, request_ms, game_id)
        except Exception as exc:  # noqa: BLE001 - isolate an unavailable player; redact logs.
            conn.rollback()
            errors += 1
            code = exc.status_code if isinstance(exc, RiotApiError) else None
            store_state(conn, puuid, name, "error", utc_now(), int((monotonic()-request_start)*1000),
                        error=f"riot_{code}" if code else type(exc).__name__)
            logger.warning("Spectator observation failed (%s)", code or type(exc).__name__)
            if code == 429:
                cooldown = max(interval, exc.retry_after or 60)
                cycle_status = "rate_limited"
            elif code in (401, 403):
                cooldown, cycle_status = max(interval, 900), "authentication_error"
            else:
                cooldown, cycle_status = max(interval, 60), "degraded"
        polled += 1
        if cooldown or stop.is_set():
            break  # In particular, never call another player after a 429.
        stop.wait(1)
    wait = max(cooldown, interval - (monotonic()-begin), 1)
    heartbeat(conn, cycle_status if errors or not players else "ok", interval, len(players), polled, errors, wait)
    return wait


def run_forever(stop=None):
    stop = stop or Event()
    interval = int(os.getenv("RIOT_LIVE_POLL_SECONDS", "60"))
    limit = int(os.getenv("RIOT_LIVE_STREAM_MAX_PLAYERS", "5"))
    if not 30 <= interval <= 3600 or not 1 <= limit <= 10:
        raise ValueError("Live interval must be 30..3600 seconds and player limit 1..10")
    config = get_minio_config()
    if not is_minio_enabled(config):
        raise ValueError("MinIO configuration is required for the live service")
    while not stop.is_set():
        conn = None
        try:
            conn = get_gold_conn()
            with conn.cursor() as cur:
                cur.execute("SET statement_timeout='10s'")
                cur.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,))
                locked = cur.fetchone()[0]
            conn.commit()
            if not locked:
                raise RuntimeError("Another spectator collector holds the lock")
            init_schema(conn)
            while not stop.is_set():
                wait = poll_cycle(conn, config, stop, interval, limit)
                logger.info("Spectator cycle complete; next cycle in %.0fs", wait)
                # A permitted API cooldown is healthy, not a stuck process.
                HEALTH_FILE.write_text(json.dumps({"deadline": utc_now().timestamp()+wait+180}), encoding="utf-8")
                stop.wait(wait)
            heartbeat(conn, "stopped", interval, 0, 0, 0)
        except Exception as exc:  # noqa: BLE001 - reconnect after database/service failures.
            logger.error("Live service retry in 60s (%s)", type(exc).__name__)
            stop.wait(60)
        finally:
            if conn is not None:
                conn.close()  # Releases the session advisory lock.


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop = Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    server = start_server()
    try:
        run_forever(stop)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
