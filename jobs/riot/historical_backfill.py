"""Rattrapage historique ciblé des matchs Riot sans rescanner tout le ladder.

Le DAG quotidien ``riot_euw_ingestion`` commence par actualiser les joueurs
Master+. Pour un rattrapage analytique, cette étape est inutilement coûteuse :
les joueurs sont déjà présents dans ``audit.riot_tracked_players``. Ce module
réutilise donc uniquement l'étape d'historique Match-v5, puis enregistre un
manifest et un run d'audit comme les autres pipelines.

Exemple :
    python -m jobs.riot.historical_backfill \
        --lookback-days 60 --max-players 10 \
        --matches-per-player 100 --max-matches-per-run 500
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jobs.riot.euw_ingest import (
    DEFAULT_MINIO_PREFIX,
    DEFAULT_RAW_DIR,
    finalize_riot_run,
    make_run_id,
    prepare_riot_run,
    run_match_ingestion_stage,
)


def run(
    raw_dir: str | Path = DEFAULT_RAW_DIR,
    minio_prefix: str = DEFAULT_MINIO_PREFIX,
    lookback_days: int = 60,
    max_players: int = 10,
    matches_per_player: int = 100,
    max_matches_per_run: int = 500,
    ingest_timelines: bool = False,
) -> dict[str, Any]:
    """Rattrape les historiques des joueurs les moins récemment traités."""
    run_id = f"{make_run_id()}_historical"
    prepare_riot_run(run_id)
    match_summary = run_match_ingestion_stage(
        run_id=run_id,
        raw_dir=raw_dir,
        minio_prefix=minio_prefix,
        lookback_days=lookback_days,
        max_players=max_players,
        matches_per_player=matches_per_player,
        max_matches_per_run=max_matches_per_run,
        ingest_timelines=ingest_timelines,
    )
    return finalize_riot_run(
        run_id=run_id,
        snapshot_summary={
            "snapshot_entries": 0,
            "snapshot_seen_puuids": 0,
            "snapshot_error_count": 0,
            "snapshot_error_samples": [],
        },
        match_summary=match_summary,
        raw_dir=raw_dir,
        minio_prefix=minio_prefix,
        lookback_days=lookback_days,
        max_players=max_players,
        matches_per_player=matches_per_player,
        max_matches_per_run=max_matches_per_run,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rattrapage historique Match-v5 des joueurs Riot déjà suivis."
    )
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--minio-prefix", default=DEFAULT_MINIO_PREFIX)
    parser.add_argument("--lookback-days", type=int, default=60)
    parser.add_argument("--max-players", type=int, default=10)
    parser.add_argument("--matches-per-player", type=int, default=100)
    parser.add_argument("--max-matches-per-run", type=int, default=500)
    parser.add_argument("--with-timelines", action="store_true")
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
        ingest_timelines=args.with_timelines,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
