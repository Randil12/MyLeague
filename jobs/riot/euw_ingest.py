from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from jobs.riot.client import (
    get_league_entries,
    get_master_plus_entries,
    get_match,
    get_match_ids_by_puuid,
    get_match_timeline,
    write_json,
)

DEFAULT_RAW_DIR = Path("data/bronze/riot")
DEFAULT_MINIO_PREFIX = "bronze/riot"
REGION = "euw1"
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
        cur.execute(
            "ALTER TABLE audit.riot_tracked_players "
            "ADD COLUMN IF NOT EXISTS tracking_source TEXT NOT NULL DEFAULT 'ladder'"
        )
        cur.execute(
            "ALTER TABLE audit.riot_match_ingestion ADD COLUMN IF NOT EXISTS timeline_status TEXT"
        )
        cur.execute(
            "ALTER TABLE audit.riot_match_ingestion ADD COLUMN IF NOT EXISTS timeline_uri TEXT"
        )
        cur.execute(
            "ALTER TABLE audit.riot_match_ingestion "
            "ADD COLUMN IF NOT EXISTS timeline_retry_count INTEGER NOT NULL DEFAULT 0"
        )
        cur.execute(
            "UPDATE audit.riot_tracked_players SET region = %s WHERE region = %s",
            (REGION, REGION.upper()),
        )
        cur.execute(
            "UPDATE audit.riot_match_ingestion SET region = %s WHERE region = %s",
            (REGION, REGION.upper()),
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
    """Écrit l'objet en zone bronze.

    MinIO est l'unique zone bronze quand il est configuré (cas nominal en Docker) :
    pas de copie locale redondante. Sans MinIO (exécution hors conteneur), on
    bascule en écriture locale — mode dégradé assumé.
    """
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

    write_json(payload, local_path)
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
                region = EXCLUDED.region,
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
                    region = EXCLUDED.region,
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
        puuid = entry.get("puuid")
        if not puuid:
            errors.append({"stage": "snapshot_player", "entry": entry, "error": "missing puuid"})
            continue

        try:
            summoner = {
                "puuid": puuid,
                "id": entry.get("summonerId"),
                "accountId": entry.get("accountId"),
                "name": entry.get("summonerName"),
                "source": "league-v4",
            }
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
                    "stage": "snapshot_player",
                    "puuid": puuid,
                    "error": str(exc),
                }
            )

    mark_absent_players_not_current(conn, seen_puuids, snapshot_started_at)
    return entries, errors, seen_puuids


def parse_extra_tiers(spec: str) -> list[tuple[str, str, int]]:
    """Parse 'DIAMOND:I:1,EMERALD:I:1' -> [(tier, division, pages)]."""
    configs: list[tuple[str, str, int]] = []
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        bits = part.split(":")
        tier = bits[0].upper()
        division = bits[1].upper() if len(bits) > 1 and bits[1] else "I"
        pages = int(bits[2]) if len(bits) > 2 and bits[2] else 1
        configs.append((tier, division, pages))
    return configs


def upsert_lower_tier_player(conn, entry: dict[str, Any], seen_at: datetime) -> None:
    """Joueur des tiers non-apex (Diamond, Emerald...) pour comparer la méta par elo."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit.riot_tracked_players (
                region,
                puuid,
                summoner_id,
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
                tracking_source,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, TRUE, 'ladder', %s)
            ON CONFLICT (puuid) DO UPDATE SET
                tier = EXCLUDED.tier,
                rank = EXCLUDED.rank,
                league_points = EXCLUDED.league_points,
                wins = EXCLUDED.wins,
                losses = EXCLUDED.losses,
                queue_type = EXCLUDED.queue_type,
                last_seen_master_plus_at = EXCLUDED.last_seen_master_plus_at,
                updated_at = EXCLUDED.updated_at
            """,
            (
                REGION,
                entry["puuid"],
                entry.get("summonerId"),
                entry.get("summonerName"),
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


def snapshot_extra_tier_entries(
    conn,
    raw_path: Path,
    minio_config: dict[str, str | None],
    minio_prefix: str,
    run_id: str,
    extra_tiers_spec: str,
) -> tuple[int, list[dict[str, Any]]]:
    """Échantillonne des tiers inférieurs (league-v4 entries) pour la méta par niveau de jeu."""
    seen_at = utc_now()
    seen_count = 0
    errors: list[dict[str, Any]] = []

    for tier, division, pages in parse_extra_tiers(extra_tiers_spec):
        for page in range(1, pages + 1):
            try:
                entries = get_league_entries(tier, division, page=page)
            except Exception as exc:  # noqa: BLE001 - keep snapshot resilient per tier.
                errors.append(
                    {"stage": "extra_tier_entries", "tier": tier, "division": division,
                     "page": page, "error": str(exc)}
                )
                continue

            entries_path = (
                f"queue={QUEUE_NAME}/tier={tier}/division={division}"
                f"/page={page}/run_id={run_id}/ranked_entries.json"
            )
            save_payload(
                entries,
                build_local_path(raw_path, "ranked_entries", entries_path),
                build_key("ranked_entries", entries_path, minio_prefix),
                minio_config,
            )

            for entry in entries:
                puuid = entry.get("puuid")
                if not puuid:
                    continue
                try:
                    upsert_lower_tier_player(
                        conn, {**entry, "tier": entry.get("tier", tier)}, seen_at
                    )
                    seen_count += 1
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        {"stage": "extra_tier_player", "puuid": puuid, "error": str(exc)}
                    )

    return seen_count, errors


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


def mark_timeline_result(conn, match_id: str, status: str, timeline_uri: str | None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE audit.riot_match_ingestion
            SET timeline_status = %s,
                timeline_uri = %s,
                timeline_retry_count = timeline_retry_count
                    + CASE WHEN %s = 'failed' THEN 1 ELSE 0 END,
                updated_at = NOW()
            WHERE match_id = %s
            """,
            (status, timeline_uri, status, match_id),
        )
    conn.commit()


def mark_match_not_found(conn, match_id: str, run_id: str, error_message: str) -> None:
    """Match définitivement introuvable (404) : exclu des retries, on ne gaspille plus de quota."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE audit.riot_match_ingestion
            SET status = 'not_found',
                run_id = %s,
                error_message = %s,
                updated_at = NOW()
            WHERE match_id = %s
            """,
            (run_id, error_message[:2000], match_id),
        )
    conn.commit()


def select_retriable_timelines(conn, limit: int) -> list[str]:
    """Matchs OK dont la timeline a échoué : retentés jusqu'à 5 fois."""
    if limit <= 0:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT match_id
            FROM audit.riot_match_ingestion
            WHERE region = %s
              AND status = 'success'
              AND timeline_status = 'failed'
              AND timeline_retry_count < 5
            ORDER BY updated_at ASC
            LIMIT %s
            """,
            (REGION, limit),
        )
        return [row[0] for row in cur.fetchall()]


def ingest_timeline_payload(
    conn,
    raw_path: Path,
    minio_config: dict[str, str | None],
    minio_prefix: str,
    match_id: str,
) -> dict[str, Any] | None:
    """Timeline du match (analyse par phase de jeu). Non bloquant : le match reste success."""
    try:
        timeline_payload = get_match_timeline(match_id)
        timeline_path = f"match_id={match_id}/timeline.json"
        timeline_uri = save_payload(
            timeline_payload,
            build_local_path(raw_path, "timelines", timeline_path),
            build_key("timelines", timeline_path, minio_prefix),
            minio_config,
        )
        mark_timeline_result(conn, match_id, "success", timeline_uri)
        return None
    except Exception as exc:  # noqa: BLE001 - timeline failure must not fail the match.
        mark_timeline_result(conn, match_id, "failed", None)
        return {"stage": "timeline", "matchId": match_id, "error": str(exc)}


def ingest_match_payload(
    conn,
    raw_path: Path,
    minio_config: dict[str, str | None],
    minio_prefix: str,
    run_id: str,
    match_id: str,
    ingest_timeline: bool = False,
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

        timeline_error = None
        if ingest_timeline:
            timeline_error = ingest_timeline_payload(
                conn, raw_path, minio_config, minio_prefix, match_id
            )
        return True, timeline_error
    except Exception as exc:  # noqa: BLE001 - keep ingestion resilient per match.
        # 404 = match supprimé/inexistant côté Riot : inutile de le retenter.
        if getattr(exc, "status_code", None) == 404:
            mark_match_not_found(conn, match_id, run_id, str(exc))
            return False, {"stage": "match", "matchId": match_id, "error": "not_found (404)"}
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
    ingest_timelines: bool = False,
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
        success, error = ingest_match_payload(
            conn, raw_path, minio_config, minio_prefix, run_id, match_id, ingest_timelines
        )
        match_attempts += 1
        if success:
            loaded_matches += 1
        if error:
            errors.append(error)

    # Rattrapage des timelines en échec sur des matchs déjà ingérés (budget limité).
    if ingest_timelines:
        for match_id in select_retriable_timelines(conn, limit=50):
            timeline_error = ingest_timeline_payload(
                conn, raw_path, minio_config, minio_prefix, match_id
            )
            if timeline_error:
                errors.append(timeline_error)

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
                    ingest_timelines,
                )
                match_attempts += 1
                if success:
                    loaded_matches += 1
                if error:
                    errors.append(error)

            update_player_ingestion_timestamp(conn, puuid, end_dt)
        except Exception as exc:  # noqa: BLE001 - keep ingestion resilient per player.
            errors.append({"stage": "match_ids", "puuid": puuid, "error": str(exc)})

    return len(unique_match_ids), loaded_matches, errors


def make_run_id() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def summarize_errors(errors: list[dict[str, Any]], sample_size: int = 20) -> dict[str, Any]:
    return {
        "count": len(errors),
        "samples": errors[:sample_size],
    }


def prepare_riot_run(run_id: str | None = None) -> dict[str, Any]:
    current_run_id = run_id or make_run_id()
    conn = get_gold_conn()
    try:
        init_audit_tables(conn)
        start_pipeline_run(conn, current_run_id)
        return {
            "run_id": current_run_id,
            "region": REGION,
            "routing": ROUTING,
            "queue_id": QUEUE_ID,
            "queue_name": QUEUE_NAME,
        }
    finally:
        conn.close()


def run_snapshot_stage(
    run_id: str,
    raw_dir: str | Path = DEFAULT_RAW_DIR,
    minio_prefix: str = DEFAULT_MINIO_PREFIX,
    extra_tiers: str = "",
) -> dict[str, Any]:
    raw_path = Path(raw_dir)
    minio_config = get_minio_config()
    conn = get_gold_conn()
    try:
        init_audit_tables(conn)
        entries, errors, seen_puuids = snapshot_master_plus_players(
            conn,
            raw_path,
            minio_config,
            minio_prefix,
            run_id,
        )

        extra_tier_seen = 0
        if extra_tiers:
            extra_tier_seen, extra_tier_errors = snapshot_extra_tier_entries(
                conn,
                raw_path,
                minio_config,
                minio_prefix,
                run_id,
                extra_tiers,
            )
            errors = list(errors) + extra_tier_errors

        return {
            "run_id": run_id,
            "snapshot_entries": len(entries),
            "snapshot_seen_puuids": len(seen_puuids),
            "extra_tier_players_seen": extra_tier_seen,
            "snapshot_error_count": len(errors),
            "snapshot_error_samples": errors[:20],
        }
    finally:
        conn.close()


def run_match_ingestion_stage(
    run_id: str,
    raw_dir: str | Path = DEFAULT_RAW_DIR,
    minio_prefix: str = DEFAULT_MINIO_PREFIX,
    lookback_days: int = 7,
    max_players: int = 25,
    matches_per_player: int = 10,
    max_matches_per_run: int = 250,
    ingest_timelines: bool = False,
) -> dict[str, Any]:
    raw_path = Path(raw_dir)
    minio_config = get_minio_config()
    conn = get_gold_conn()
    try:
        init_audit_tables(conn)
        unique_match_ids, loaded_matches, errors = ingest_tracked_player_matches(
            conn,
            raw_path,
            minio_config,
            minio_prefix,
            run_id,
            lookback_days,
            max_players,
            matches_per_player,
            max_matches_per_run,
            ingest_timelines,
        )
        return {
            "run_id": run_id,
            "unique_match_ids_seen_this_run": unique_match_ids,
            "matches_loaded": loaded_matches,
            "match_error_count": len(errors),
            "match_error_samples": errors[:20],
        }
    finally:
        conn.close()


def finalize_riot_run(
    run_id: str,
    snapshot_summary: dict[str, Any],
    match_summary: dict[str, Any],
    raw_dir: str | Path = DEFAULT_RAW_DIR,
    minio_prefix: str = DEFAULT_MINIO_PREFIX,
    lookback_days: int = 7,
    max_players: int = 25,
    matches_per_player: int = 10,
    max_matches_per_run: int = 250,
) -> dict[str, Any]:
    raw_path = Path(raw_dir)
    minio_config = get_minio_config()
    snapshot_error_count = int(snapshot_summary.get("snapshot_error_count", 0))
    match_error_count = int(match_summary.get("match_error_count", 0))
    total_error_count = snapshot_error_count + match_error_count
    snapshot_entries = int(snapshot_summary.get("snapshot_entries", 0))
    snapshot_seen_puuids = int(snapshot_summary.get("snapshot_seen_puuids", 0))
    unique_match_ids = int(match_summary.get("unique_match_ids_seen_this_run", 0))
    loaded_matches = int(match_summary.get("matches_loaded", 0))

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
        "snapshot_entries": snapshot_entries,
        "snapshot_seen_puuids": snapshot_seen_puuids,
        "unique_match_ids_seen_this_run": unique_match_ids,
        "matches_loaded": loaded_matches,
        "error_count": total_error_count,
        "snapshot_error_count": snapshot_error_count,
        "match_error_count": match_error_count,
        "snapshot_error_samples": snapshot_summary.get("snapshot_error_samples", []),
        "match_error_samples": match_summary.get("match_error_samples", []),
    }
    manifest_path = f"run_id={run_id}/manifest.json"
    manifest_uri = save_payload(
        manifest,
        build_local_path(raw_path, "manifests", manifest_path),
        build_key("manifests", manifest_path, minio_prefix),
        minio_config,
    )

    status = "success" if total_error_count == 0 else "partial_success"
    conn = get_gold_conn()
    try:
        init_audit_tables(conn)
        finish_pipeline_run(
            conn,
            run_id,
            status=status,
            records_read=snapshot_entries + unique_match_ids,
            records_written=snapshot_seen_puuids + loaded_matches,
            error_count=total_error_count,
        )
    finally:
        conn.close()

    return {
        "run_id": run_id,
        "region": REGION,
        "routing": ROUTING,
        "snapshot_entries": snapshot_entries,
        "tracked_players_seen": snapshot_seen_puuids,
        "unique_match_ids_seen_this_run": unique_match_ids,
        "matches_loaded": loaded_matches,
        "error_count": total_error_count,
        "manifest": manifest_uri,
        "status": status,
    }

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


if __name__ == "__main__":  # pragma: no cover
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








