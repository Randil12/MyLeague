"""DAG manuel de rattrapage historique Riot pour les analyses multi-patch."""

from __future__ import annotations

from airflow.decorators import dag, task
from pendulum import datetime


@dag(
    dag_id="riot_historical_backfill",
    schedule=None,
    start_date=datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    tags=["riot", "historical", "bloc2", "manual"],
    description=(
        "Rattrape 60 jours de matchs des joueurs déjà suivis sans rescanner "
        "l'intégralité du ladder Master+."
    ),
)
def riot_historical_backfill() -> None:
    @task
    def backfill() -> dict:
        from jobs.riot.historical_backfill import run

        return run(
            lookback_days=60,
            max_players=10,
            matches_per_player=100,
            max_matches_per_run=500,
            ingest_timelines=False,
        )

    backfill()


riot_historical_backfill()
