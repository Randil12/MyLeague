from __future__ import annotations

from datetime import datetime, timedelta

from airflow.sdk import dag, task

RAW_DIR = "/opt/airflow/data/bronze/patch_notes"


@dag(
    dag_id="patch_notes_scraping",
    description=(
        "Web scraping des notes de patch officielles Riot. Tourne chaque jour : "
        "détecte le patch courant via Data Dragon et ne scrape que s'il est nouveau "
        "(idempotent ; un 404 = notes pas encore publiées, retenté le lendemain)."
    ),
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=15),
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["patch-notes", "scraping", "bronze"],
)
def patch_notes_scraping() -> None:
    @task(execution_timeout=timedelta(minutes=10))
    def scrape_patch_notes() -> dict:
        from jobs.patch_notes.ingest import run

        return run(raw_dir=RAW_DIR, locale="fr-fr")

    scrape_patch_notes()


patch_notes_scraping()
