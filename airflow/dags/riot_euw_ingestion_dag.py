from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow.sdk import dag, task


@dag(
    dag_id="riot_euw_ingestion",
    description="Ingest EUW Master+ ranked solo queue matches from Riot API into bronze.",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=60),
    tags=["riot", "euw", "bronze", "etl"],
)
def riot_euw_ingestion() -> None:
    @task(execution_timeout=timedelta(minutes=45))
    def ingest_euw_matches() -> dict:
        from jobs.riot.euw_ingest import run

        return run(
            raw_dir="/opt/airflow/data/bronze/riot",
            lookback_days=int(os.getenv("RIOT_EUW_LOOKBACK_DAYS", "7")),
            max_players=int(os.getenv("RIOT_EUW_MAX_PLAYERS", "25")),
            matches_per_player=int(os.getenv("RIOT_EUW_MATCHES_PER_PLAYER", "10")),
            max_matches_per_run=int(os.getenv("RIOT_EUW_MAX_MATCHES_PER_RUN", "250")),
        )

    ingest_euw_matches()


riot_euw_ingestion()
