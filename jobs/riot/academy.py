"""Suivi des joueurs de Nexus Esport Academy.

- register : résout un Riot ID (GameName#TAG) en puuid via account-v1 et marque le
  joueur comme suivi (tracking_source='academy'). Ses matchs seront ingérés par
  riot_euw_ingestion et ses parties en cours par riot_live_spectator.
- masteries : capture le pool de champions (champion-mastery-v4) des joueurs academy,
  pour le coaching individuel ("ton champion le plus maîtrisé est faible ce patch").

Usage CLI :
    python -m jobs.riot.academy register --riot-id "GameName#TAG"
    python -m jobs.riot.academy masteries
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jobs.riot.client import get_account_by_riot_id, get_champion_masteries_by_puuid
from jobs.riot.euw_ingest import (
    DEFAULT_MINIO_PREFIX,
    DEFAULT_RAW_DIR,
    REGION,
    build_key,
    build_local_path,
    get_gold_conn,
    get_minio_config,
    init_audit_tables,
    save_payload,
    utc_now,
)


def parse_riot_id(riot_id: str) -> tuple[str, str]:
    game_name, sep, tag_line = riot_id.partition("#")
    if not sep or not game_name.strip() or not tag_line.strip():
        raise ValueError(f"Riot ID invalide : '{riot_id}' (format attendu : 'GameName#TAG')")
    return game_name.strip(), tag_line.strip()


def init_masteries_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS raw")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw.riot_champion_masteries (
                region TEXT NOT NULL,
                puuid TEXT NOT NULL,
                champion_key INTEGER NOT NULL,
                mastery_level INTEGER,
                mastery_points BIGINT,
                last_played_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (puuid, champion_key)
            )
            """
        )
    conn.commit()


def register_academy_player(riot_id: str) -> dict[str, Any]:
    game_name, tag_line = parse_riot_id(riot_id)
    account = get_account_by_riot_id(game_name, tag_line)
    puuid = account["puuid"]
    seen_at = utc_now()

    conn = get_gold_conn()
    try:
        init_audit_tables(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit.riot_tracked_players (
                    region, puuid, riot_summoner_name,
                    first_seen_master_plus_at, last_seen_master_plus_at,
                    is_currently_master_plus, is_tracked, tracking_source, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, FALSE, TRUE, 'academy', %s)
                ON CONFLICT (puuid) DO UPDATE SET
                    riot_summoner_name = EXCLUDED.riot_summoner_name,
                    is_tracked = TRUE,
                    tracking_source = 'academy',
                    updated_at = EXCLUDED.updated_at
                """,
                (REGION, puuid, f"{game_name}#{tag_line}", seen_at, seen_at, seen_at),
            )
        conn.commit()
    finally:
        conn.close()

    return {"riot_id": f"{game_name}#{tag_line}", "puuid": puuid, "tracking_source": "academy"}


def select_academy_players(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT puuid
            FROM audit.riot_tracked_players
            WHERE region = %s AND is_tracked = TRUE AND tracking_source = 'academy'
            ORDER BY updated_at DESC
            """,
            (REGION,),
        )
        return [row[0] for row in cur.fetchall()]


def upsert_masteries(conn, puuid: str, masteries: list[dict[str, Any]]) -> int:
    with conn.cursor() as cur:
        for mastery in masteries:
            cur.execute(
                """
                INSERT INTO raw.riot_champion_masteries (
                    region, puuid, champion_key, mastery_level, mastery_points,
                    last_played_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, to_timestamp(%s / 1000.0), NOW())
                ON CONFLICT (puuid, champion_key) DO UPDATE SET
                    mastery_level = EXCLUDED.mastery_level,
                    mastery_points = EXCLUDED.mastery_points,
                    last_played_at = EXCLUDED.last_played_at,
                    updated_at = NOW()
                """,
                (
                    REGION,
                    puuid,
                    mastery.get("championId"),
                    mastery.get("championLevel"),
                    mastery.get("championPoints"),
                    mastery.get("lastPlayTime") or 0,
                ),
            )
    conn.commit()
    return len(masteries)


def ingest_academy_masteries(
    raw_dir: str | Path = DEFAULT_RAW_DIR,
    minio_prefix: str = DEFAULT_MINIO_PREFIX,
) -> dict[str, Any]:
    raw_path = Path(raw_dir)
    minio_config = get_minio_config()
    run_id = utc_now().strftime("%Y%m%dT%H%M%SZ")
    conn = get_gold_conn()

    puuids: list[str] = []
    players_processed = 0
    masteries_loaded = 0
    errors: list[dict[str, Any]] = []

    try:
        init_audit_tables(conn)
        init_masteries_schema(conn)
        puuids = select_academy_players(conn)

        for puuid in puuids:
            try:
                masteries = get_champion_masteries_by_puuid(puuid)
                masteries_path = f"puuid={puuid}/run_id={run_id}/masteries.json"
                save_payload(
                    masteries,
                    build_local_path(raw_path, "masteries", masteries_path),
                    build_key("masteries", masteries_path, minio_prefix),
                    minio_config,
                )
                masteries_loaded += upsert_masteries(conn, puuid, masteries)
                players_processed += 1
            except Exception as exc:  # noqa: BLE001 - keep ingestion resilient per player.
                errors.append({"stage": "masteries", "puuid": puuid, "error": str(exc)})
    finally:
        conn.close()

    return {
        "run_id": run_id,
        "region": REGION,
        "academy_players": len(puuids),
        "players_processed": players_processed,
        "masteries_loaded": masteries_loaded,
        "error_count": len(errors),
        "error_samples": errors[:10],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gestion des joueurs suivis pour l'academy.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    register_parser = subparsers.add_parser("register", help="Enregistrer un joueur academy.")
    register_parser.add_argument("--riot-id", required=True, help="Format : 'GameName#TAG'")

    masteries_parser = subparsers.add_parser("masteries", help="Ingérer les maîtrises champions.")
    masteries_parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    masteries_parser.add_argument("--minio-prefix", default=DEFAULT_MINIO_PREFIX)

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.command == "register":
        result = register_academy_player(args.riot_id)
    else:
        result = ingest_academy_masteries(raw_dir=args.raw_dir, minio_prefix=args.minio_prefix)
    print(json.dumps(result, indent=2, default=str))
