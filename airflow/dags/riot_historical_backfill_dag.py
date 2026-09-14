"""Rattrapage historique nocturne, borné et reprenable, pour les analyses multi-patch."""

from __future__ import annotations

from datetime import timedelta

from airflow.sdk import dag, task
from pendulum import datetime


@dag(
    dag_id="riot_historical_backfill",
    schedule="35 1 * * *",  # 01:35 UTC, après la fenêtre du run Riot de minuit.
    start_date=datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=55),
    tags=["riot", "historical", "bloc2"],
    description=(
        "Rattrape 60 jours de matchs des joueurs déjà suivis sans rescanner "
        "l'intégralité du ladder Master+."
    ),
)
def riot_historical_backfill() -> None:
    @task(execution_timeout=timedelta(minutes=40), retries=0)
    def backfill() -> dict:
        from jobs.riot.historical_backfill import run

        return run(
            lookback_days=60,
            max_players=10,
            matches_per_player=100,
            max_matches_per_run=500,
            raw_dir="/opt/airflow/data/bronze/riot",
            ingest_timelines=True,
        )

    @task(execution_timeout=timedelta(minutes=15))
    def load_raw(summary: dict) -> dict:
        from jobs.riot.load_raw import run

        result = run(raw_dir="/opt/airflow/data/bronze/riot", batch_limit=1000)
        if summary.get('error_count') or result.get('error_count') or result.get('missing_bronze_files'):
            raise RuntimeError('Backfill partiel : consulter audit.pipeline_runs ; reprise au prochain run.')
        return result

    load_raw(backfill())


riot_historical_backfill()
