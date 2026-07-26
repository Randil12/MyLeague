from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow.sdk import dag, task

RAW_DIR = "/opt/airflow/data/bronze/leaguepedia"


@dag(
    dag_id="leaguepedia_ingestion",
    description=(
        "ELT Leaguepedia : tournois, équipes, joueurs et parties professionnelles "
        "(picks/bans par patch) via l'API Cargo — comparaison méta pro vs solo queue."
    ),
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=45),
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["leaguepedia", "esport", "bronze", "elt"],
)
def leaguepedia_ingestion() -> None:
    @task(execution_timeout=timedelta(minutes=40))
    def ingest_leaguepedia() -> dict:
        from jobs.leaguepedia.ingest import run

        return run(
            raw_dir=RAW_DIR,
            year=int(os.getenv("LEAGUEPEDIA_YEAR", "0")) or None,
            lookback_days=int(os.getenv("LEAGUEPEDIA_LOOKBACK_DAYS", "30")),
            max_pages=int(os.getenv("LEAGUEPEDIA_MAX_PAGES", "20")),
        )

    ingest_leaguepedia()


leaguepedia_ingestion()
