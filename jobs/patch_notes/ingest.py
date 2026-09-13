"""Ingestion des notes de patch : détecte le patch courant et scrape s'il est nouveau.

Déclenché quotidiennement : la version courante vient de Data Dragon (source de
vérité des sorties de patch). Idempotent — un patch déjà ingéré est ignoré, et
des notes pas encore publiées (404) seront naturellement retentées le lendemain.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jobs.datadragon.client import get_latest_version
from jobs.patch_notes.scraper import (
    build_patch_notes_url,
    fetch_html,
    parse_patch_notes,
    patch_from_version,
)
from jobs.riot.client import write_json
from jobs.riot.euw_ingest import (
    get_gold_conn,
    get_minio_config,
    is_minio_enabled,
    upload_json_to_minio,
    utc_now,
)

DEFAULT_RAW_DIR = Path("data/bronze/patch_notes")
DEFAULT_MINIO_PREFIX = "bronze/patch_notes"
PIPELINE_NAME = "patch_notes_scraping"


def init_patch_notes_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS raw")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw.riot_patch_notes (
                patch TEXT PRIMARY KEY,
                locale TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT,
                section_count INTEGER,
                payload JSONB NOT NULL,
                scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    conn.commit()


def patch_already_ingested(conn, patch: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM raw.riot_patch_notes WHERE patch = %s", (patch,))
        return cur.fetchone() is not None


def upsert_patch_notes(conn, patch: str, locale: str, url: str, parsed: dict[str, Any]) -> None:
    from psycopg2.extras import Json

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO raw.riot_patch_notes
                (patch, locale, url, title, section_count, payload, scraped_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (patch) DO UPDATE SET
                locale = EXCLUDED.locale,
                url = EXCLUDED.url,
                title = EXCLUDED.title,
                section_count = EXCLUDED.section_count,
                payload = EXCLUDED.payload,
                scraped_at = NOW()
            """,
            (patch, locale, url, parsed.get("title"), len(parsed.get("sections", [])), Json(parsed)),
        )
    conn.commit()


def upload_html_to_minio(html: str, key: str, minio_config: dict[str, str | None]) -> None:
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=minio_config["endpoint_url"],
        aws_access_key_id=minio_config["access_key_id"],
        aws_secret_access_key=minio_config["secret_access_key"],
        region_name=minio_config["region_name"],
    )
    client.put_object(
        Bucket=str(minio_config["bucket"]),
        Key=key,
        Body=html.encode("utf-8"),
        ContentType="text/html; charset=utf-8",
    )


def save_bronze(
    html: str,
    parsed: dict[str, Any],
    patch: str,
    run_id: str,
    raw_path: Path,
    minio_prefix: str,
    minio_config: dict[str, str | None],
) -> None:
    """MinIO est l'unique zone bronze ; écriture locale seulement en mode dégradé."""
    if is_minio_enabled(minio_config):
        upload_html_to_minio(
            html, f"{minio_prefix}/patch={patch}/run_id={run_id}/notes.html", minio_config
        )
        upload_json_to_minio(
            parsed,
            bucket=str(minio_config["bucket"]),
            key=f"{minio_prefix}/patch={patch}/run_id={run_id}/notes.json",
            endpoint_url=str(minio_config["endpoint_url"]),
            access_key_id=str(minio_config["access_key_id"]),
            secret_access_key=str(minio_config["secret_access_key"]),
            region_name=str(minio_config["region_name"]),
        )
        return

    patch_dir = raw_path / f"patch={patch}"
    html_path = patch_dir / "notes.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")
    write_json(parsed, patch_dir / "notes.json")


def record_run(conn, run_id: str, status: str, read: int, written: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit.pipeline_runs
                (run_id, pipeline_name, source, started_at, ended_at, status,
                 records_read, records_written, error_count)
            VALUES (%s, %s, 'web_scraping', %s, %s, %s, %s, %s, 0)
            ON CONFLICT (run_id) DO UPDATE SET
                ended_at = EXCLUDED.ended_at,
                status = EXCLUDED.status,
                records_read = EXCLUDED.records_read,
                records_written = EXCLUDED.records_written
            """,
            (run_id, PIPELINE_NAME, utc_now(), utc_now(), status, read, written),
        )
    conn.commit()


def run(
    raw_dir: str | Path = DEFAULT_RAW_DIR,
    minio_prefix: str = DEFAULT_MINIO_PREFIX,
    locale: str = "fr-fr",
    patch: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    raw_path = Path(raw_dir)
    minio_config = get_minio_config()
    run_id = utc_now().strftime("%Y%m%dT%H%M%SZ")

    # Détection du patch courant : Data Dragon fait foi pour les sorties de patch.
    target_patch = patch or patch_from_version(get_latest_version())
    url = build_patch_notes_url(target_patch, locale)

    conn = get_gold_conn()
    try:
        init_patch_notes_schema(conn)

        if not force and patch_already_ingested(conn, target_patch):
            record_run(conn, run_id, "success", 0, 0)
            return {"run_id": run_id, "patch": target_patch, "status": "already_ingested"}

        html = fetch_html(url)
        if html is None:
            # Patch détecté sur Data Dragon mais notes pas encore en ligne :
            # non bloquant, le run quotidien suivant les récupérera.
            record_run(conn, run_id, "success", 0, 0)
            return {"run_id": run_id, "patch": target_patch, "url": url,
                    "status": "not_published_yet"}

        parsed = parse_patch_notes(html)
        save_bronze(html, parsed, target_patch, run_id, raw_path, minio_prefix, minio_config)
        upsert_patch_notes(conn, target_patch, locale, url, parsed)
        record_run(conn, run_id, "success", 1, 1)

        return {
            "run_id": run_id,
            "patch": target_patch,
            "url": url,
            "title": parsed.get("title"),
            "sections": len(parsed.get("sections", [])),
            "status": "scraped",
        }
    except Exception:
        try:
            record_run(conn, run_id, "failed", 0, 0)
        finally:
            conn.close()
        raise
    finally:
        if not conn.closed:
            conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape Riot patch notes for the current patch.")
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--minio-prefix", default=DEFAULT_MINIO_PREFIX)
    parser.add_argument("--locale", default="fr-fr")
    parser.add_argument("--patch", default=None, help="Forcer un patch précis, ex : 16.12")
    parser.add_argument("--force", action="store_true", help="Re-scraper même si déjà ingéré")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    result = run(
        raw_dir=args.raw_dir,
        minio_prefix=args.minio_prefix,
        locale=args.locale,
        patch=args.patch,
        force=args.force,
    )
    print(json.dumps(result, indent=2, default=str))
