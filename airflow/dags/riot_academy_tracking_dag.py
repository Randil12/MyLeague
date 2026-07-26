from __future__ import annotations

from datetime import datetime, timedelta

from airflow.sdk import dag, task

RAW_DIR = "/opt/airflow/data/bronze/riot"


@dag(
    dag_id="riot_academy_tracking",
    description=(
        "Suivi des joueurs de Nexus Esport Academy : capture quotidienne de leur pool "
        "de champions (champion-mastery-v4). Enregistrer un joueur : "
        "python -m jobs.riot.academy register --riot-id 'GameName#TAG'"
    ),
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=30),
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["riot", "academy", "mastery", "bronze"],
)
def riot_academy_tracking() -> None:
    @task(execution_timeout=timedelta(minutes=25))
    def ingest_masteries() -> dict:
        from jobs.riot.academy import ingest_academy_masteries

        return ingest_academy_masteries(raw_dir=RAW_DIR)

    ingest_masteries()


riot_academy_tracking()
