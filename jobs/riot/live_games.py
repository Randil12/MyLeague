"""Pipeline quasi temps réel (micro-batch) : parties en cours des joueurs suivis.

Interroge spectator-v5 pour les joueurs suivis (academy en priorité, puis ladder),
et capture les drafts/compositions des parties ranked solo queue en cours.
Répond à l'exigence de pipeline temps réel (C4.2.2) avec une approche polling
compatible avec les rate limits d'une clé de développement.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jobs.riot.client import get_active_game_by_puuid
from jobs.riot.euw_ingest import (
    DEFAULT_MINIO_PREFIX,
    DEFAULT_RAW_DIR,
    QUEUE_ID,
    REGION,
    build_key,
    build_local_path,
    get_gold_conn,
    get_minio_config,
    save_payload,
    utc_now,
)


def init_live_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS raw")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw.riot_live_game_snapshots (
                game_id BIGINT PRIMARY KEY,
                region TEXT NOT NULL,
                queue_id INTEGER,
                observed_puuid TEXT,
                game_started_at TIMESTAMPTZ,
                payload JSONB NOT NULL,
                observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    conn.commit()


def select_players_to_poll(conn, max_players: int) -> list[str]:
    """Joueurs academy en priorité, puis les Master+ vus le plus récemment."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT puuid
            FROM audit.riot_tracked_players
            WHERE region = %s AND is_tracked = TRUE
            ORDER BY (tracking_source = 'academy') DESC,
                     last_seen_master_plus_at DESC
            LIMIT %s
            """,
            (REGION, max_players),
        )
        return [row[0] for row in cur.fetchall()]


def insert_live_snapshot(conn, game: dict[str, Any], observed_puuid: str) -> bool:
    """Insère la partie observée. Retourne False si déjà connue (déduplication)."""
    from psycopg2.extras import Json

    game_id = game.get("gameId")
    start_ms = game.get("gameStartTime") or 0
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO raw.riot_live_game_snapshots (
                game_id, region, queue_id, observed_puuid, game_started_at, payload, observed_at
            )
            VALUES (%s, %s, %s, %s, to_timestamp(%s / 1000.0), %s, %s)
            ON CONFLICT (game_id) DO NOTHING
            RETURNING game_id
            """,
            (
                game_id,
                REGION,
                game.get("gameQueueConfigId"),
                observed_puuid,
                start_ms,
                Json(game),
                utc_now(),
            ),
        )
        inserted = cur.fetchone() is not None
    conn.commit()
    return inserted


def run(
    raw_dir: str | Path = DEFAULT_RAW_DIR,
    minio_prefix: str = DEFAULT_MINIO_PREFIX,
    max_players: int = 30,
    queue_id: int = QUEUE_ID,
) -> dict[str, Any]:
    raw_path = Path(raw_dir)
    minio_config = get_minio_config()
    run_id = utc_now().strftime("%Y%m%dT%H%M%SZ")
    conn = get_gold_conn()

    polled = 0
    in_game = 0
    new_games = 0
    errors: list[dict[str, Any]] = []

    try:
        init_live_schema(conn)
        puuids = select_players_to_poll(conn, max_players)

        for puuid in puuids:
            polled += 1
            try:
                game = get_active_game_by_puuid(puuid)
            except Exception as exc:  # noqa: BLE001 - keep polling resilient per player.
                errors.append({"stage": "active_game", "puuid": puuid, "error": str(exc)})
                continue

            if game is None:
                continue
            if queue_id and game.get("gameQueueConfigId") != queue_id:
                continue

            in_game += 1
            if insert_live_snapshot(conn, game, puuid):
                new_games += 1
                game_path = f"game_id={game.get('gameId')}/run_id={run_id}/active_game.json"
                save_payload(
                    game,
                    build_local_path(raw_path, "live_games", game_path),
                    build_key("live_games", game_path, minio_prefix),
                    minio_config,
                )
    finally:
        conn.close()

    return {
        "run_id": run_id,
        "region": REGION,
        "players_polled": polled,
        "players_in_game": in_game,
        "new_games_captured": new_games,
        "error_count": len(errors),
        "error_samples": errors[:10],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Poll live games (spectator-v5) for tracked players.")
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--minio-prefix", default=DEFAULT_MINIO_PREFIX)
    parser.add_argument("--max-players", type=int, default=30)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    result = run(raw_dir=args.raw_dir, minio_prefix=args.minio_prefix, max_players=args.max_players)
    print(json.dumps(result, indent=2, default=str))
