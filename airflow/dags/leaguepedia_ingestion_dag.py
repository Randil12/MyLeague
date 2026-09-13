from __future__ import annotations

import os
from datetime import timedelta

from airflow.sdk import dag, task
from pendulum import datetime

RAW_DIR = "/opt/airflow/data/bronze/leaguepedia"


@dag(
    dag_id="leaguepedia_ingestion",
    description=(
        "Référentiels Leaguepedia : tournois, équipes et fiches joueurs. "
        "Les parties sont collectées par leaguepedia_active_players."
    ),
    schedule="0 1,7,13,19 * * *",  # UTC : toutes les 6 h, avant dbt (README.md).
    start_date=datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=75),
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
            include_scoreboards=False,  # Matches now belong to leaguepedia_active_players.
        )

    ingest_leaguepedia()


leaguepedia_ingestion()
