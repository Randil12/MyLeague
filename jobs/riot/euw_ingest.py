from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from jobs.riot.client import (
    get_master_plus_entries,
    get_match,
    get_match_ids_by_puuid,
    get_summoner_by_id,
    write_json,
)


DEFAULT_RAW_DIR = Path("data/bronze/riot")
DEFAULT_MINIO_PREFIX = "bronze/riot"
REGION = "EUW1"
ROUTING = "europe"
QUEUE_ID = 420
QUEUE_NAME = "ranked_solo_5x5"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def upload_json_to_minio(
    payload: Any,
    bucket: str,
    key: str,
    endpoint_url: str,
    access_key_id: str,
    secret_access_key: str,
    region_name: str,
) -> None:
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name=region_name,
    )
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"),
        ContentType="application/json",
    )


def get_minio_config() -> dict[str, str | None]:
    return {
        "endpoint_url": os.getenv("MINIO_ENDPOINT_URL"),
        "bucket": os.getenv("MINIO_BUCKET", "myleague-data"),
        "access_key_id": os.getenv("AWS_ACCESS_KEY_ID"),
        "secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
        "region_name": os.getenv("AWS_DEFAULT_REGION", "eu-west-3"),
    }


def is_minio_enabled(config: dict[str, str | None]) -> bool:
    return all(
        [
            config["endpoint_url"],
            config["bucket"],
            config["access_key_id"],
            config["secret_access_key"],
        ]
    )


def get_gold_conn():
    import psycopg2

    return psycopg2.connect(
        host=os.getenv("GOLD_POSTGRES_HOST", "gold-postgres"),
        port=int(os.getenv("GOLD_POSTGRES_PORT", "5432")),
        dbname=os.getenv("GOLD_POSTGRES_DB", "gold"),
        user=os.getenv("GOLD_POSTGRES_USER", "gold"),
        password=os.getenv("GOLD_POSTGRES_PASSWORD", "gold"),
    )


def init_audit_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS staging")
        cur.execute("CREATE SCHEMA IF NOT EXISTS intermediate")
        cur.execute("CREATE SCHEMA IF NOT EXISTS gold")
        cur.execute("CREATE SCHEMA IF NOT EXISTS audit")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS audit.riot_tracked_players (
                region TEXT NOT NULL,
                puuid TEXT PRIMARY KEY,
                summoner_id TEXT,
                account_id TEXT,
                profile_icon_id INTEGER,
                summoner_level BIGINT,
                riot_summoner_name TEXT,
                tier TEXT,
                rank TEXT,
                league_points INTEGER,
                wins INTEGER,
                losses INTEGER,
                queue_type TEXT,
                first_seen_master_plus_at TIMESTAMPTZ NOT NULL,
                last_seen_master_plus_at TIMESTAMPTZ NOT NULL,
                last_match_ingestion_at TIMESTAMPTZ,
                is_currently_master_plus BOOLEAN NOT NULL DEFAULT TRUE,
                is_tracked BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS audit.riot_match_ingestion (
                region TEXT NOT NULL,
                match_id TEXT PRIMARY KEY,
                first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                loaded_at TIMESTAMPTZ,
                status TEXT NOT NULL DEFAULT 'pending',
                source_puuid TEXT,
                run_id TEXT,
                bronze_uri TEXT,
                error_message TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS audit.pipeline_runs (
                run_id TEXT PRIMARY KEY,
                pipeline_name TEXT NOT NULL,
                source TEXT NOT NULL,
                started_at TIMESTAMPTZ NOT NULL,
                ended_at TIMESTAMPTZ,
                status TEXT NOT NULL,
                records_read INTEGER DEFAULT 0,
                records_written INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                error_message TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    conn.commit()


def start_pipeline_run(conn, run_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit.pipeline_runs (run_id, pipeline_name, source, started_at, status)
            VALUES (%s, %s, %s, %s, 'running')
            ON CONFLICT (run_id) DO UPDATE SET status = 'running', started_at = EXCLUDED.started_at
            """,
            (run_id, "riot_euw_ingestion", "riot_api", utc_now()),
        )
    conn.commit()


def finish_pipeline_run(
    conn,
    run_id: str,
    status: str,
    records_read: int,
    records_written: int,
    error_count: int,
    error_message: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE audit.pipeline_runs
            SET ended_at = %s,
                status = %s,
                records_read = %s,
                records_written = %s,
                error_count = %s,
                error_message = %s
            WHERE run_id = %s
            """,
            (utc_now(), status, records_read, records_written, error_count, error_message, run_id),
        )
    conn.commit()


def save_payload(
    payload: Any,
    local_path: Path,
    minio_key: str,
    minio_config: dict[str, str | None],
) -> str:
    write_json(payload, local_path)

    if is_minio_enabled(minio_config):
        upload_json_to_minio(
            payload,
            bucket=str(minio_config["bucket"]),
            key=minio_key,
            endpoint_url=str(minio_config["endpoint_url"]),
            access_key_id=str(minio_config["access_key_id"]),
            secret_access_key=str(minio_config["secret_access_key"]),
            region_name=str(minio_config["region_name"]),
        )
        return f"s3://{minio_config['bucket']}/{minio_key}"

    return str(local_path)


def build_key(dataset: str, relative_path: str, minio_prefix: str = DEFAULT_MINIO_PREFIX) -> str:
    return f"{minio_prefix}/region={REGION}/{dataset}/{relative_path}"


def build_local_path(raw_path: Path, dataset: str, relative_path: str) -> Path:
    return raw_path / f"region={REGION}" / dataset / relative_path


def upsert_tracked_player(conn, entry: dict[str, Any], summoner: dict[str, Any], seen_at: datetime) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit.riot_tracked_players (
                region,
                puuid,
                summoner_id,
                account_id,
                profile_icon_id,
                summoner_level,
                riot_summoner_name,
                tier,
                rank,
                league_points,
                wins,
                losses,
                queue_type,
                first_seen_master_plus_at,
                last_seen_master_plus_at,
                is_currently_master_plus,
                is_tracked,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, TRUE, %s)
            ON CONFLICT (puuid) DO UPDATE SET
                summoner_id = EXCLUDED.summoner_id,
                account_id = EXCLUDED.account_id,
                profile_icon_id = EXCLUDED.profile_icon_id,
                summoner_level = EXCLUDED.summoner_level,
                riot_summoner_name = EXCLUDED.riot_summoner_name,
                tier = EXCLUDED.tier,
                rank = EXCLUDED.rank,
                league_points = EXCLUDED.league_points,
                wins = EXCLUDED.wins,
                losses = EXCLUDED.losses,
                queue_type = EXCLUDED.queue_type,
                last_seen_master_plus_at = EXCLUDED.last_seen_master_plus_at,
                is_currently_master_plus = TRUE,
                is_tracked = TRUE,
                updated_at = EXCLUDED.updated_at
            """,
            (
                REGION,
                summoner["puuid"],
                summoner.get("id"),
                summoner.get("accountId"),
                summoner.get("profileIconId"),
                summoner.get("summonerLevel"),
                summoner.get("name") or entry.get("summonerName"),
                entry.get("tier"),
                entry.get("rank"),
                entry.get("leaguePoints"),
                entry.get("wins"),
                entry.get("losses"),
                entry.get("queueType"),
                seen_at,
                seen_at,
                seen_at,
            ),
        )
    conn.commit()


def mark_absent_players_not_current(conn, seen_puuids: set[str], snapshot_started_at: datetime) -> None:
    if not seen_puuids:
        return
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE audit.riot_tracked_players
            SET is_currently_master_plus = FALSE,
                updated_at = %s
            WHERE region = %s
              AND is_tracked = TRUE
              AND last_seen_master_plus_at < %s
              AND NOT (puuid = ANY(%s))
            """,
            (utc_now(), REGION, snapshot_started_at, list(seen_puuids)),
        )
    conn.commit()


def select_players_for_match_ingestion(conn, max_players: int) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT puuid, last_match_ingestion_at
            FROM audit.riot_tracked_players
            WHERE region = %s AND is_tracked = TRUE
            ORDER BY last_match_ingestion_at NULLS FIRST, last_seen_master_plus_at DESC
            LIMIT %s
            """,
            (REGION, max_players),
        )
        return [
            {"puuid": row[0], "last_match_ingestion_at": row[1]}
            for row in cur.fetchall()
        ]


def register_match_ids(conn, match_ids: list[str], source_puuid: str, run_id: str) -> list[str]:
    candidates = []
    with conn.cursor() as cur:
        for match_id in match_ids:
            cur.execute(
                """
                INSERT INTO audit.riot_match_ingestion (region, match_id, source_puuid, run_id, status)
                VALUES (%s, %s, %s, %s, 'pending')
                ON CONFLICT (match_id) DO UPDATE SET
                    source_puuid = COALESCE(audit.riot_match_ingestion.source_puuid, EXCLUDED.source_puuid),
                    run_id = EXCLUDED.run_id,
                    updated_at = NOW()
                RETURNING status
                """,
                (REGION, match_id, source_puuid, run_id),
            )
            status = cur.fetchone()[0]
            if status != "success":
                candidates.append(match_id)
    conn.commit()
    return candidates


def mark_match_success(conn, match_id: str, run_id: str, bronze_uri: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE audit.riot_match_ingestion
            SET status = 'success',
                loaded_at = NOW(),
                run_id = %s,
                bronze_uri = %s,
                error_message = NULL,
                updated_at = NOW()
            WHERE match_id = %s
            """,
            (run_id, bronze_uri, match_id),
        )
    conn.commit()


def mark_match_failed(conn, match_id: str, run_id: str, error_message: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE audit.riot_match_ingestion
            SET status = 'failed',
                run_id = %s,
                error_message = %s,
                retry_count = retry_count + 1,
                updated_at = NOW()
            WHERE match_id = %s
            """,
            (run_id, error_message[:2000], match_id),
        )
    conn.commit()


def update_player_ingestion_timestamp(conn, puuid: str, ingested_until: datetime) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE audit.riot_tracked_players
            SET last_match_ingestion_at = %s,
                updated_at = NOW()
            WHERE puuid = %s
            """,
            (ingested_until, puuid),
        )
    conn.commit()


def snapshot_master_plus_players(
    conn,
    raw_path: Path,
    minio_config: dict[str, str | None],
    minio_prefix: str,
    run_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str]]:
    snapshot_started_at = utc_now()
    entries = get_master_plus_entries()
    ranked_entries_path = f"queue={QUEUE_NAME}/run_id={run_id}/ranked_entries.json"
    save_payload(
        entries,
        build_local_path(raw_path, "ranked_entries", ranked_entries_path),
        build_key("ranked_entries", ranked_entries_path, minio_prefix),
        minio_config,
    )

    errors = []
    seen_puuids: set[str] = set()
    for entry in entries:
        encrypted_summoner_id = entry.get("summonerId")
        if not encrypted_summoner_id:
            errors.append({"stage": "snapshot_summoner", "entry": entry, "error": "missing summonerId"})
            continue
        try:
            summoner = get_summoner_by_id(encrypted_summoner_id)
            puuid = summoner["puuid"]
            seen_puuids.add(puuid)
            upsert_tracked_player(conn, entry, summoner, snapshot_started_at)

            summoner_payload = {"leagueEntry": entry, "summoner": summoner}
            summoner_path = f"puuid={puuid}/run_id={run_id}/summoner.json"
            save_payload(
                summoner_payload,
                build_local_path(raw_path, "summoners", summoner_path),
                build_key("summoners", summoner_path, minio_prefix),
                minio_config,
            )
        except Exception as exc:  # noqa: BLE001 - keep snapshot resilient per player.
            errors.append(
                {
                    "stage": "snapshot_summoner",
                    "summonerId": encrypted_summoner_id,
                    "error": str(exc),
                }
            )

    mark_absent_players_not_current(conn, seen_puuids, snapshot_started_at)
    return entries, errors, seen_puuids


def select_retriable_matches(conn, limit: int) -> list[str]:
    if limit <= 0:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT match_id
            FROM audit.riot_match_ingestion
            WHERE region = %s
              AND status IN ('pending', 'failed')
              AND retry_count < 5
            ORDER BY updated_at ASC, first_seen_at ASC
            LIMIT %s
            """,
            (REGION, limit),
        )
        return [row[0] for row in cur.fetchall()]


def ingest_match_payload(
    conn,
    raw_path: Path,
    minio_config: dict[str, str | None],
    minio_prefix: str,
    run_id: str,
    match_id: str,
) -> tuple[bool, dict[str, Any] | None]:
    try:
        match_payload = get_match(match_id)
        match_path = f"match_id={match_id}/match.json"
        bronze_uri = save_payload(
            match_payload,
            build_local_path(raw_path, "matches", match_path),
            build_key("matches", match_path, minio_prefix),
            minio_config,
        )
        mark_match_success(conn, match_id, run_id, bronze_uri)
        return True, None
    except Exception as exc:  # noqa: BLE001 - keep ingestion resilient per match.
        mark_match_failed(conn, match_id, run_id, str(exc))
        return False, {"stage": "match", "matchId": match_id, "error": str(exc)}

def ingest_tracked_player_matches(
    conn,
    raw_path: Path,
    minio_config: dict[str, str | None],
    minio_prefix: str,
    run_id: str,
    lookback_days: int,
    max_players: int,
    matches_per_player: int,
    max_matches_per_run: int,
) -> tuple[int, int, list[dict[str, Any]]]:
    errors = []
    loaded_matches = 0
    match_attempts = 0
    unique_match_ids: set[str] = set()
    end_dt = utc_now()
    end_time = int(end_dt.timestamp())

    retriable_match_ids = select_retriable_matches(conn, max_matches_per_run)
    for match_id in retriable_match_ids:
        if match_attempts >= max_matches_per_run:
            break
        success, error = ingest_match_payload(conn, raw_path, minio_config, minio_prefix, run_id, match_id)
        match_attempts += 1
        if success:
            loaded_matches += 1
        elif error:
            errors.append(error)

    players = select_players_for_match_ingestion(conn, max_players)

    for player in players:
        if match_attempts >= max_matches_per_run:
            break

        puuid = player["puuid"]
        last_match_ingestion_at = player["last_match_ingestion_at"]
        start_dt = last_match_ingestion_at or (end_dt - timedelta(days=lookback_days))
        start_time = int(start_dt.timestamp())

        try:
            player_match_ids = get_match_ids_by_puuid(
                puuid,
                start_time=start_time,
                end_time=end_time,
                queue=QUEUE_ID,
                count=matches_per_player,
            )
            match_ids_path = (
                f"puuid={puuid}/start={start_time}/end={end_time}/run_id={run_id}/match_ids.json"
            )
            save_payload(
                player_match_ids,
                build_local_path(raw_path, "match_ids", match_ids_path),
                build_key("match_ids", match_ids_path, minio_prefix),
                minio_config,
            )
            candidate_match_ids = register_match_ids(conn, player_match_ids, puuid, run_id)
            unique_match_ids.update(player_match_ids)

            for match_id in candidate_match_ids:
                if match_attempts >= max_matches_per_run:
                    break
                success, error = ingest_match_payload(
                    conn,
                    raw_path,
                    minio_config,
                    minio_prefix,
                    run_id,
                    match_id,
                )
                match_attempts += 1
                if success:
                    loaded_matches += 1
                elif error:
                    errors.append(error)

            update_player_ingestion_timestamp(conn, puuid, end_dt)
        except Exception as exc:  # noqa: BLE001 - keep ingestion resilient per player.
            errors.append({"stage": "match_ids", "puuid": puuid, "error": str(exc)})

    return len(unique_match_ids), loaded_matches, errors


def run(
    raw_dir: str | Path = DEFAULT_RAW_DIR,
    minio_prefix: str = DEFAULT_MINIO_PREFIX,
    lookback_days: int = 7,
    max_players: int = 25,
    matches_per_player: int = 10,
    max_matches_per_run: int = 250,
) -> dict[str, Any]:
    raw_path = Path(raw_dir)
    minio_config = get_minio_config()
    run_id = utc_now().strftime("%Y%m%dT%H%M%SZ")
    conn = get_gold_conn()
    errors: list[dict[str, Any]] = []

    try:
        init_audit_tables(conn)
        start_pipeline_run(conn, run_id)

        entries, snapshot_errors, seen_puuids = snapshot_master_plus_players(
            conn,
            raw_path,
            minio_config,
            minio_prefix,
            run_id,
        )
        errors.extend(snapshot_errors)

        unique_match_ids, loaded_matches, match_errors = ingest_tracked_player_matches(
            conn,
            raw_path,
            minio_config,
            minio_prefix,
            run_id,
            lookback_days,
            max_players,
            matches_per_player,
            max_matches_per_run,
        )
        errors.extend(match_errors)

        manifest = {
            "run_id": run_id,
            "region": REGION,
            "routing": ROUTING,
            "queue_id": QUEUE_ID,
            "queue_name": QUEUE_NAME,
            "lookback_days": lookback_days,
            "max_players": max_players,
            "matches_per_player": matches_per_player,
            "max_matches_per_run": max_matches_per_run,
            "snapshot_entries": len(entries),
            "snapshot_seen_puuids": len(seen_puuids),
            "unique_match_ids_seen_this_run": unique_match_ids,
            "matches_loaded": loaded_matches,
            "errors": errors,
        }
        manifest_path = f"run_id={run_id}/manifest.json"
        manifest_uri = save_payload(
            manifest,
            build_local_path(raw_path, "manifests", manifest_path),
            build_key("manifests", manifest_path, minio_prefix),
            minio_config,
        )

        status = "success" if not errors else "partial_success"
        finish_pipeline_run(
            conn,
            run_id,
            status=status,
            records_read=len(entries) + unique_match_ids,
            records_written=len(seen_puuids) + loaded_matches,
            error_count=len(errors),
        )

        return {
            "run_id": run_id,
            "region": REGION,
            "routing": ROUTING,
            "snapshot_entries": len(entries),
            "tracked_players_seen": len(seen_puuids),
            "unique_match_ids_seen_this_run": unique_match_ids,
            "matches_loaded": loaded_matches,
            "error_count": len(errors),
            "manifest": manifest_uri,
        }
    except Exception as exc:
        try:
            finish_pipeline_run(
                conn,
                run_id,
                status="failed",
                records_read=0,
                records_written=0,
                error_count=len(errors) + 1,
                error_message=str(exc),
            )
        finally:
            conn.close()
        raise
    finally:
        if not conn.closed:
            conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest EUW Master+ Riot matches into bronze.")
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--minio-prefix", default=DEFAULT_MINIO_PREFIX)
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--max-players", type=int, default=25)
    parser.add_argument("--matches-per-player", type=int, default=10)
    parser.add_argument("--max-matches-per-run", type=int, default=250)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    result = run(
        raw_dir=args.raw_dir,
        minio_prefix=args.minio_prefix,
        lookback_days=args.lookback_days,
        max_players=args.max_players,
        matches_per_player=args.matches_per_player,
        max_matches_per_run=args.max_matches_per_run,
    )
    for key, value in result.items():
        print(f"{key}={value}")



