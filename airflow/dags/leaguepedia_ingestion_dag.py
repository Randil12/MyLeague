"""Single scheduled Leaguepedia pipeline: history, catalog, then player analytics."""
from datetime import timedelta

from airflow.sdk import dag, task
from pendulum import datetime


@dag(
    dag_id="leaguepedia_ingestion",
    description="Leaguepedia unifié : parties de l'année, référentiels et Gold joueurs.",
    schedule="15 * * * *",
    start_date=datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    max_active_tasks=1,
    dagrun_timeout=timedelta(minutes=55),
    default_args={"retries": 0},
    tags=["leaguepedia", "players", "bronze", "gold"],
)
def leaguepedia_ingestion():
    @task(execution_timeout=timedelta(minutes=25))
    def collect_current_year():
        from jobs.leaguepedia.yearly import run

        return run(
            raw_dir="/opt/airflow/data/bronze/leaguepedia",
            days_per_run=20,
            budget_seconds=600,
            revisit_after_seconds=86400,
            pipeline_name="leaguepedia_ingestion",
        )

    @task(execution_timeout=timedelta(minutes=15))
    def collect_catalog():
        from jobs.leaguepedia.ingest import run

        result = run(raw_dir="/opt/airflow/data/bronze/leaguepedia", include_scoreboards=False)
        if result["status"] != "success":
            raise RuntimeError("Leaguepedia catalog incomplete; inspect audit.pipeline_runs")
        return result

    @task.bash(execution_timeout=timedelta(minutes=10))
    def build_player_gold():
        return (
            "dbt build --project-dir /opt/airflow/dbt "
            "--profiles-dir /opt/airflow/dbt/profiles --target dev "
            "--select tag:leaguepedia_active --indirect-selection cautious "
            "--target-path /tmp/dbt-leaguepedia-active/target "
            "--log-path /tmp/dbt-leaguepedia-active/logs --fail-fast"
        )

    collect_current_year() >> collect_catalog() >> build_player_gold()


leaguepedia_ingestion()
