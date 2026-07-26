"""Étape Load de l'ELT Riot : bronze (JSON MinIO/disque) -> raw.riot_matches (Postgres JSONB).

Pattern ELT assumé (vs ETL Data Dragon) : les matchs sont volumineux et leur schéma
évolue à chaque patch. On charge le JSON brut dans le warehouse, la transformation
est déléguée à dbt (staging -> intermediate -> gold), ce qui permet de retraiter
tout l'historique sans re-solliciter l'API Riot (rate limits).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jobs.riot.euw_ingest import (
    DEFAULT_RAW_DIR,
    REGION,
    get_gold_conn,
    get_minio_config,
    is_minio_enabled,
    utc_now,
)


def parse_s3_uri(uri: str | None) -> tuple[str, str] | None:
    """'s3://bucket/path/to/key' -> (bucket, key), sinon None."""
    if not uri or not uri.startswith("s3://"):
        return None
    bucket, _, key = uri[5:].partition("/")
    if not bucket or not key:
        return None
    return bucket, key


def fetch_payload_from_minio(uri: str | None) -> dict[str, Any] | None:
    """Lit un objet bronze depuis MinIO (chemin nominal : le lake est l'unique bronze).

    L'URI provient de l'audit (bronze_uri / timeline_uri). Le fichier local n'est
    consulté avant qu'en mode dégradé, quand l'ingestion a tourné sans MinIO.
    """
    parsed = parse_s3_uri(uri)
    if not parsed:
        return None
    config = get_minio_config()
    if not is_minio_enabled(config):
        return None

    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=config["endpoint_url"],
        aws_access_key_id=config["access_key_id"],
        aws_secret_access_key=config["secret_access_key"],
        region_name=config["region_name"],
    )
    obj = client.get_object(Bucket=parsed[0], Key=parsed[1])
    return json.loads(obj["Body"].read().decode("utf-8"))


def validate_match_payload(match_id: str, payload: Any) -> str | None:
    """Contrôle de cohérence avant chargement. Retourne la raison du rejet, ou None si valide."""
    if not isinstance(payload, dict):
        return "payload is not a JSON object"
    metadata_match_id = (payload.get("metadata") or {}).get("matchId")
    if metadata_match_id and metadata_match_id != match_id:
        return f"matchId mismatch: expected {match_id}, got {metadata_match_id}"
    info = payload.get("info")
    if not isinstance(info, dict):
        return "missing 'info' block"
    participants = info.get("participants")
    if not isinstance(participants, list) or len(participants) != 10:
        count = len(participants) if isinstance(participants, list) else "none"
        return f"unexpected participants count: {count}"
    if not info.get("gameVersion"):
        return "missing gameVersion"
    return None


def init_raw_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS raw")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw.riot_matches (
                match_id TEXT PRIMARY KEY,
                region TEXT NOT NULL,
                game_version TEXT,
                source_puuid TEXT,
                source_tier TEXT,
                payload JSONB NOT NULL,
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute("ALTER TABLE raw.riot_matches ADD COLUMN IF NOT EXISTS source_puuid TEXT")
        cur.execute("ALTER TABLE raw.riot_matches ADD COLUMN IF NOT EXISTS source_tier TEXT")
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_raw_riot_matches_game_version
                ON raw.riot_matches (game_version)
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw.riot_match_timelines (
                match_id TEXT PRIMARY KEY,
                region TEXT NOT NULL,
                payload JSONB NOT NULL,
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    conn.commit()


def select_matches_to_load(conn, batch_limit: int) -> list[dict[str, Any]]:
    """Matchs ingérés avec succès en bronze mais pas encore chargés dans raw.

    Le tier du joueur source (audit.riot_tracked_players) est propagé pour
    permettre l'analyse de la méta par niveau de jeu.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.match_id, m.source_puuid, p.tier, m.bronze_uri
            FROM audit.riot_match_ingestion m
            LEFT JOIN raw.riot_matches r ON r.match_id = m.match_id
            LEFT JOIN audit.riot_tracked_players p ON p.puuid = m.source_puuid
            WHERE m.region = %s
              AND m.status = 'success'
              AND r.match_id IS NULL
            ORDER BY m.loaded_at ASC NULLS LAST
            LIMIT %s
            """,
            (REGION, batch_limit),
        )
        return [
            {"match_id": row[0], "source_puuid": row[1], "source_tier": row[2], "bronze_uri": row[3]}
            for row in cur.fetchall()
        ]


def select_timelines_to_load(conn, batch_limit: int) -> list[str]:
    """Timelines réussies en bronze mais pas encore chargées dans raw."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.match_id, m.timeline_uri
            FROM audit.riot_match_ingestion m
            -- le match doit déjà être chargé dans raw (contrainte FK timeline -> match)
            INNER JOIN raw.riot_matches rm ON rm.match_id = m.match_id
            LEFT JOIN raw.riot_match_timelines t ON t.match_id = m.match_id
            WHERE m.region = %s
              AND m.timeline_status = 'success'
              AND t.match_id IS NULL
            ORDER BY m.updated_at ASC
            LIMIT %s
            """,
            (REGION, batch_limit),
        )
        return [{"match_id": row[0], "timeline_uri": row[1]} for row in cur.fetchall()]


def bronze_match_path(raw_path: Path, match_id: str) -> Path:
    return raw_path / f"region={REGION}" / "matches" / f"match_id={match_id}" / "match.json"


def bronze_timeline_path(raw_path: Path, match_id: str) -> Path:
    return raw_path / f"region={REGION}" / "timelines" / f"match_id={match_id}" / "timeline.json"


def insert_match(
    conn,
    match_id: str,
    payload: dict[str, Any],
    source_puuid: str | None = None,
    source_tier: str | None = None,
) -> None:
    from psycopg2.extras import Json

    game_version = payload.get("info", {}).get("gameVersion")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO raw.riot_matches (
                match_id, region, game_version, source_puuid, source_tier, payload, loaded_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (match_id) DO NOTHING
            """,
            (match_id, REGION, game_version, source_puuid, source_tier, Json(payload), utc_now()),
        )


def insert_with_savepoint(conn, insert_fn, *args) -> str | None:
    """Isole chaque insertion : une violation (ex : clé étrangère) n'annule que
    la ligne concernée, pas le lot — la ligne sera retentée au run suivant.
    Retourne le message d'erreur, ou None si l'insertion a réussi."""
    with conn.cursor() as cur:
        cur.execute("SAVEPOINT row_sp")
    try:
        insert_fn(conn, *args)
        with conn.cursor() as cur:
            cur.execute("RELEASE SAVEPOINT row_sp")
        return None
    except Exception as exc:  # noqa: BLE001
        with conn.cursor() as cur:
            cur.execute("ROLLBACK TO SAVEPOINT row_sp")
        return str(exc)


def insert_timeline(conn, match_id: str, payload: dict[str, Any]) -> None:
    from psycopg2.extras import Json

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO raw.riot_match_timelines (match_id, region, payload, loaded_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (match_id) DO NOTHING
            """,
            (match_id, REGION, Json(payload), utc_now()),
        )


def run(raw_dir: str | Path = DEFAULT_RAW_DIR, batch_limit: int = 1000) -> dict[str, Any]:
    raw_path = Path(raw_dir)
    conn = get_gold_conn()
    loaded = 0
    timelines_loaded = 0
    recovered_from_minio = 0
    invalid_payloads = 0
    candidates: list[dict[str, Any]] = []
    timeline_candidates: list[dict[str, Any]] = []
    missing_files: list[str] = []
    errors: list[dict[str, Any]] = []

    def read_payload(local_path: Path, uri: str | None) -> tuple[Any, bool]:
        """Lit le bronze local, sinon retombe sur MinIO. Retourne (payload, depuis_minio)."""
        if local_path.exists():
            return json.loads(local_path.read_text(encoding="utf-8")), False
        return fetch_payload_from_minio(uri), True

    try:
        init_raw_schema(conn)
        candidates = select_matches_to_load(conn, batch_limit)

        for candidate in candidates:
            match_id = candidate["match_id"]
            try:
                payload, from_minio = read_payload(
                    bronze_match_path(raw_path, match_id), candidate.get("bronze_uri")
                )
                if payload is None:
                    missing_files.append(match_id)
                    continue
                if from_minio:
                    recovered_from_minio += 1

                rejection = validate_match_payload(match_id, payload)
                if rejection:
                    invalid_payloads += 1
                    errors.append({"match_id": match_id, "stage": "validation", "error": rejection})
                    continue

                insert_error = insert_with_savepoint(
                    conn,
                    lambda c: insert_match(
                        c,
                        match_id,
                        payload,
                        source_puuid=candidate.get("source_puuid"),
                        source_tier=candidate.get("source_tier"),
                    ),
                )
                if insert_error:
                    errors.append({"match_id": match_id, "error": insert_error})
                else:
                    loaded += 1
            except Exception as exc:  # noqa: BLE001 - keep warehouse load resilient per match.
                errors.append({"match_id": match_id, "error": str(exc)})

        timeline_candidates = select_timelines_to_load(conn, batch_limit)
        for candidate in timeline_candidates:
            match_id = candidate["match_id"]
            try:
                payload, from_minio = read_payload(
                    bronze_timeline_path(raw_path, match_id), candidate.get("timeline_uri")
                )
                if payload is None:
                    missing_files.append(f"timeline:{match_id}")
                    continue
                if from_minio:
                    recovered_from_minio += 1
                insert_error = insert_with_savepoint(conn, insert_timeline, match_id, payload)
                if insert_error:
                    errors.append({"match_id": match_id, "stage": "timeline", "error": insert_error})
                else:
                    timelines_loaded += 1
            except Exception as exc:  # noqa: BLE001
                errors.append({"match_id": match_id, "stage": "timeline", "error": str(exc)})

        conn.commit()
    finally:
        conn.close()

    return {
        "region": REGION,
        "candidates": len(candidates),
        "loaded_to_raw": loaded,
        "timeline_candidates": len(timeline_candidates),
        "timelines_loaded_to_raw": timelines_loaded,
        "recovered_from_minio": recovered_from_minio,
        "invalid_payloads": invalid_payloads,
        "missing_bronze_files": len(missing_files),
        "missing_samples": missing_files[:10],
        "error_count": len(errors),
        "error_samples": errors[:10],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load bronze Riot matches into raw.riot_matches (JSONB) for dbt."
    )
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--batch-limit", type=int, default=1000)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    result = run(raw_dir=args.raw_dir, batch_limit=args.batch_limit)
    for key, value in result.items():
        print(f"{key}={value}")
