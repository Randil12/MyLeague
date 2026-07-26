from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from airflow.sdk import dag, task

RAW_DIR = "/opt/airflow/data/bronze/riot"


@dag(
    dag_id="riot_euw_ingestion",
    description="Ingest EUW Master+ ranked solo queue matches from Riot API into bronze.",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=90),
    # 1 retry Airflow pour les pannes transitoires ; la reprise fine (match par match)
    # est gérée par les tables d'audit et les statuts pending/failed/not_found.
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["riot", "euw", "bronze", "etl"],
)
def riot_euw_ingestion() -> None:
    @task
    def prepare_run() -> dict[str, Any]:
        from jobs.riot.euw_ingest import prepare_riot_run

        return prepare_riot_run()

    @task(execution_timeout=timedelta(minutes=35))
    def snapshot_master_plus(run_context: dict[str, Any]) -> dict[str, Any]:
        from jobs.riot.euw_ingest import run_snapshot_stage

        return run_snapshot_stage(
            run_id=run_context["run_id"],
            raw_dir=RAW_DIR,
            # Ex : "DIAMOND:I:1,EMERALD:I:1" pour comparer la méta par niveau de jeu.
            extra_tiers=os.getenv("RIOT_EUW_EXTRA_TIERS", ""),
        )

    @task(execution_timeout=timedelta(minutes=45))
    def ingest_matches(run_context: dict[str, Any], snapshot_summary: dict[str, Any]) -> dict[str, Any]:
        from jobs.riot.euw_ingest import run_match_ingestion_stage

        return run_match_ingestion_stage(
            run_id=run_context["run_id"],
            raw_dir=RAW_DIR,
            lookback_days=int(os.getenv("RIOT_EUW_LOOKBACK_DAYS", "7")),
            max_players=int(os.getenv("RIOT_EUW_MAX_PLAYERS", "25")),
            matches_per_player=int(os.getenv("RIOT_EUW_MATCHES_PER_PLAYER", "10")),
            max_matches_per_run=int(os.getenv("RIOT_EUW_MAX_MATCHES_PER_RUN", "250")),
            # Attention : double le nombre d'appels API (1 timeline par match).
            ingest_timelines=os.getenv("RIOT_EUW_INGEST_TIMELINES", "true").lower()
            in ("1", "true", "yes"),
        )

    @task
    def finalize_run(
        run_context: dict[str, Any],
        snapshot_summary: dict[str, Any],
        match_summary: dict[str, Any],
    ) -> dict[str, Any]:
        from jobs.riot.euw_ingest import finalize_riot_run

        return finalize_riot_run(
            run_id=run_context["run_id"],
            snapshot_summary=snapshot_summary,
            match_summary=match_summary,
            raw_dir=RAW_DIR,
            lookback_days=int(os.getenv("RIOT_EUW_LOOKBACK_DAYS", "7")),
            max_players=int(os.getenv("RIOT_EUW_MAX_PLAYERS", "25")),
            matches_per_player=int(os.getenv("RIOT_EUW_MATCHES_PER_PLAYER", "10")),
            max_matches_per_run=int(os.getenv("RIOT_EUW_MAX_MATCHES_PER_RUN", "250")),
        )

    @task(execution_timeout=timedelta(minutes=20))
    def load_matches_to_warehouse(finalize_summary: dict[str, Any]) -> dict[str, Any]:
        """Étape Load de l'ELT : bronze -> raw.riot_matches (JSONB), le T est délégué à dbt."""
        from jobs.riot.load_raw import run

        return run(
            raw_dir=RAW_DIR,
            batch_limit=int(os.getenv("RIOT_EUW_RAW_LOAD_BATCH_LIMIT", "1000")),
        )

    run_context = prepare_run()
    snapshot_summary = snapshot_master_plus(run_context)
    match_summary = ingest_matches(run_context, snapshot_summary)
    finalize_summary = finalize_run(run_context, snapshot_summary, match_summary)
    load_matches_to_warehouse(finalize_summary)


riot_euw_ingestion()
