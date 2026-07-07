from __future__ import annotations

from datetime import datetime

from airflow.sdk import dag, task


@dag(
    dag_id="datadragon_ingestion",
    description="Ingest raw League of Legends reference data from Riot Data Dragon.",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["datadragon", "bronze", "elt"],
)
def datadragon_ingestion() -> None:
    @task
    def ingest_datadragon() -> dict[str, str]:
        from jobs.datadragon.ingest import run

        return run(raw_dir="/opt/airflow/data/bronze/datadragon", locale="fr_FR")

    ingest_datadragon()


datadragon_ingestion()
