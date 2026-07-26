from __future__ import annotations

from datetime import datetime, timedelta

from airflow.sdk import dag, task

RAW_DIR = "/opt/airflow/data/bronze/datadragon"
LOCALE = "fr_FR"


@dag(
    dag_id="datadragon_ingestion",
    description=(
        "ETL Data Dragon : extraction du référentiel LoL, "
        "transformation Python et chargement dans Postgres (schéma reference)."
    ),
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["datadragon", "reference", "etl"],
)
def datadragon_ingestion() -> None:
    @task
    def extract_datadragon() -> dict[str, str]:
        """Extract : appelle Data Dragon et conserve une copie brute en bronze (traçabilité)."""
        from jobs.datadragon.ingest import run

        return run(raw_dir=RAW_DIR, locale=LOCALE)

    @task
    def transform_and_load_reference(extract_result: dict[str, str]) -> dict[str, str]:
        """Transform + Load : typage/aplatissement en Python puis upsert dans reference.dim_*."""
        from jobs.datadragon.transform_load import run

        result = run(raw_dir=RAW_DIR, locale=LOCALE)
        return {key: str(value) for key, value in result.items()}

    transform_and_load_reference(extract_datadragon())


datadragon_ingestion()
