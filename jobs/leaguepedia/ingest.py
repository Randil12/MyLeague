"""ELT Leaguepedia : Extract/Load des données e-sport professionnelles.

Même pattern que l'ELT Riot : JSON bruts en bronze (local + MinIO), chargement
JSONB dans raw.*, transformation déléguée à dbt (méta pro par patch).
Résilient par dataset : l'échec d'une famille n'empêche pas les autres.
"""

from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from jobs.leaguepedia.client import (
    fetch_players,
    fetch_scoreboard_games,
    fetch_scoreboard_players,
    fetch_teams,
    fetch_tournaments,
    get_client,
)
from jobs.riot.client import write_json
from jobs.riot.euw_ingest import (
    get_gold_conn,
    get_minio_config,
    is_minio_enabled,
    upload_json_to_minio,
    utc_now,
)

DEFAULT_RAW_DIR = Path("data/bronze/leaguepedia")
DEFAULT_MINIO_PREFIX = "bronze/leaguepedia"
PIPELINE_NAME = "leaguepedia_ingestion"


def field(row: dict[str, Any], name: str) -> Any:
    """Cargo renvoie parfois 'DateTime UTC' pour un champ demandé 'DateTime_UTC'."""
    if name in row:
        return row[name]
    return row.get(name.replace("_", " "))


def extract_game(row: dict[str, Any]) -> dict[str, Any] | None:
    """Normalise une ligne ScoreboardGames. None si pas d'identifiant exploitable."""
    game_id = field(row, "GameId")
    if not game_id:
        return None
    return {
        "game_id": str(game_id),
        "patch": field(row, "Patch") or None,
        "game_date": field(row, "DateTime_UTC") or None,
    }


def extract_player_game(row: dict[str, Any]) -> dict[str, Any] | None:
    """Normalise une ligne ScoreboardPlayers. Clé composite (game_id, player_page)."""
    game_id = field(row, "GameId")
    player_page = field(row, "Link")
    if not game_id or not player_page:
        return None
    return {
        "game_id": str(game_id),
        "player_page": str(player_page),
        "champion": field(row, "Champion") or None,
        "role": field(row, "Role") or None,
        "game_date": field(row, "DateTime_UTC") or None,
    }


def init_leaguepedia_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS raw")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw.leaguepedia_tournaments (
                overview_page TEXT PRIMARY KEY,
                payload JSONB NOT NULL,
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw.leaguepedia_teams (
                overview_page TEXT PRIMARY KEY,
                payload JSONB NOT NULL,
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw.leaguepedia_players (
                overview_page TEXT PRIMARY KEY,
                payload JSONB NOT NULL,
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw.leaguepedia_scoreboard_games (
                game_id TEXT PRIMARY KEY,
                patch TEXT,
                game_date TIMESTAMPTZ,
                payload JSONB NOT NULL,
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_lp_scoreboard_games_patch
                ON raw.leaguepedia_scoreboard_games (patch)
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw.leaguepedia_scoreboard_players (
                game_id TEXT NOT NULL,
                player_page TEXT NOT NULL,
                champion TEXT,
                role TEXT,
                game_date TIMESTAMPTZ,
                payload JSONB NOT NULL,
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (game_id, player_page)
            )
            """
        )
    conn.commit()


def start_run(conn, run_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit.pipeline_runs (run_id, pipeline_name, source, started_at, status)
            VALUES (%s, %s, 'leaguepedia', %s, 'running')
            ON CONFLICT (run_id) DO UPDATE SET status = 'running', started_at = EXCLUDED.started_at
            """,
            (run_id, PIPELINE_NAME, utc_now()),
        )
    conn.commit()


def finish_run(conn, run_id: str, status: str, read: int, written: int, error_count: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE audit.pipeline_runs
            SET ended_at = %s, status = %s, records_read = %s,
                records_written = %s, error_count = %s
            WHERE run_id = %s
            """,
            (utc_now(), status, read, written, error_count, run_id),
        )
    conn.commit()


def save_bronze(
    payload: Any,
    dataset: str,
    run_id: str,
    raw_path: Path,
    minio_prefix: str,
    minio_config: dict[str, str | None],
) -> None:
    """MinIO est l'unique zone bronze ; écriture locale seulement en mode dégradé."""
    relative = f"{dataset}/run_id={run_id}/{dataset}.json"

    if is_minio_enabled(minio_config):
        upload_json_to_minio(
            payload,
            bucket=str(minio_config["bucket"]),
            key=f"{minio_prefix}/{relative}",
            endpoint_url=str(minio_config["endpoint_url"]),
            access_key_id=str(minio_config["access_key_id"]),
            secret_access_key=str(minio_config["secret_access_key"]),
            region_name=str(minio_config["region_name"]),
        )
        return

    write_json(payload, raw_path / relative)
    write_json(payload, raw_path / dataset / "latest.json")


def upsert_by_overview_page(conn, table: str, rows: list[dict[str, Any]]) -> int:
    from psycopg2.extras import Json

    written = 0
    with conn.cursor() as cur:
        for row in rows:
            overview_page = field(row, "OverviewPage")
            if not overview_page:
                continue
            cur.execute(
                f"""
                INSERT INTO raw.{table} (overview_page, payload, loaded_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (overview_page) DO UPDATE SET
                    payload = EXCLUDED.payload, loaded_at = NOW()
                """,
                (str(overview_page), Json(row)),
            )
            written += 1
    conn.commit()
    return written


def upsert_scoreboard_players(conn, rows: list[dict[str, Any]]) -> int:
    from psycopg2.extras import Json

    written = 0
    with conn.cursor() as cur:
        for row in rows:
            player_game = extract_player_game(row)
            if player_game is None:
                continue
            # Savepoint par ligne : une violation (ex : partie absente de
            # scoreboard_games -> clé étrangère) ne fait sauter que cette ligne.
            cur.execute("SAVEPOINT lp_row")
            try:
                cur.execute(
                    """
                    INSERT INTO raw.leaguepedia_scoreboard_players
                        (game_id, player_page, champion, role, game_date, payload, loaded_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (game_id, player_page) DO UPDATE SET
                        champion = EXCLUDED.champion,
                        role = EXCLUDED.role,
                        game_date = EXCLUDED.game_date,
                        payload = EXCLUDED.payload,
                        loaded_at = NOW()
                    """,
                    (
                        player_game["game_id"],
                        player_game["player_page"],
                        player_game["champion"],
                        player_game["role"],
                        player_game["game_date"],
                        Json(row),
                    ),
                )
                cur.execute("RELEASE SAVEPOINT lp_row")
                written += 1
            except Exception:  # noqa: BLE001 - ligne orpheline : ignorée, retentée au run suivant.
                cur.execute("ROLLBACK TO SAVEPOINT lp_row")
    conn.commit()
    return written


def upsert_scoreboard_games(conn, rows: list[dict[str, Any]]) -> int:
    from psycopg2.extras import Json

    written = 0
    with conn.cursor() as cur:
        for row in rows:
            game = extract_game(row)
            if game is None:
                continue
            cur.execute(
                """
                INSERT INTO raw.leaguepedia_scoreboard_games
                    (game_id, patch, game_date, payload, loaded_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (game_id) DO UPDATE SET
                    patch = EXCLUDED.patch,
                    game_date = EXCLUDED.game_date,
                    payload = EXCLUDED.payload,
                    loaded_at = NOW()
                """,
                (game["game_id"], game["patch"], game["game_date"], Json(row)),
            )
            written += 1
    conn.commit()
    return written


def run(
    raw_dir: str | Path = DEFAULT_RAW_DIR,
    minio_prefix: str = DEFAULT_MINIO_PREFIX,
    year: int | None = None,
    lookback_days: int = 30,
    max_pages: int = 20,
) -> dict[str, Any]:
    raw_path = Path(raw_dir)
    minio_config = get_minio_config()
    run_id = utc_now().strftime("%Y%m%dT%H%M%SZ")
    target_year = year or utc_now().year
    since_iso = (utc_now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d %H:%M:%S")

    client = get_client()
    conn = get_gold_conn()

    records_read = 0
    records_written = 0
    errors: list[dict[str, str]] = []
    summary: dict[str, Any] = {"run_id": run_id, "year": target_year, "since": since_iso}

    fetchers = {
        "tournaments": lambda: fetch_tournaments(client, target_year),
        "teams": lambda: fetch_teams(client, max_pages=max_pages),
        "players": lambda: fetch_players(client, max_pages=max_pages),
        "scoreboard_games": lambda: fetch_scoreboard_games(client, since_iso, max_pages=max_pages),
        "scoreboard_players": lambda: fetch_scoreboard_players(
            client, since_iso, max_pages=max_pages
        ),
    }

    try:
        init_leaguepedia_schema(conn)
        start_run(conn, run_id)

        for dataset, fetcher in fetchers.items():
            try:
                rows = fetcher()
                records_read += len(rows)
                save_bronze(rows, dataset, run_id, raw_path, minio_prefix, minio_config)

                if dataset == "scoreboard_games":
                    written = upsert_scoreboard_games(conn, rows)
                elif dataset == "scoreboard_players":
                    written = upsert_scoreboard_players(conn, rows)
                else:
                    written = upsert_by_overview_page(conn, f"leaguepedia_{dataset}", rows)

                records_written += written
                summary[f"{dataset}_read"] = len(rows)
                summary[f"{dataset}_written"] = written
            except Exception as exc:  # noqa: BLE001 - keep ingestion resilient per dataset.
                errors.append({"dataset": dataset, "error": str(exc)})

        status = "success" if not errors else "partial_success"
        finish_run(conn, run_id, status, records_read, records_written, len(errors))
    except Exception as exc:
        try:
            finish_run(conn, run_id, "failed", records_read, records_written, len(errors) + 1)
        finally:
            conn.close()
        raise exc
    finally:
        if not conn.closed:
            conn.close()

    summary["status"] = status
    summary["error_count"] = len(errors)
    summary["error_samples"] = errors[:5]
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest Leaguepedia esports data into bronze/raw.")
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--minio-prefix", default=DEFAULT_MINIO_PREFIX)
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--max-pages", type=int, default=20)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    result = run(
        raw_dir=args.raw_dir,
        minio_prefix=args.minio_prefix,
        year=args.year,
        lookback_days=args.lookback_days,
        max_pages=args.max_pages,
    )
    print(json.dumps(result, indent=2, default=str))
