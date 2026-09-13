"""Retired ID kept as an inert DAG: never launch a second Cargo collector."""
from airflow.sdk import dag, task
from pendulum import datetime


@dag(
    dag_id="leaguepedia_active_players",
    description="Retiré : utiliser leaguepedia_ingestion (pipeline fusionné).",
    schedule=None,
    start_date=datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    tags=["leaguepedia", "retired"],
)
def leaguepedia_active_players():
    @task
    def retired():
        from airflow.exceptions import AirflowSkipException

        raise AirflowSkipException("Replaced by leaguepedia_ingestion; no API calls.")

    retired()


leaguepedia_active_players()
