"""Hourly competition history and observed active-player analytics (not solo queue)."""
from datetime import timedelta

from airflow.sdk import dag, task
from pendulum import datetime


@dag(
    dag_id="leaguepedia_active_players",
    description="Parties de l'année courante, joueurs actifs observés et comparaisons Gold.",
    schedule="15 * * * *",
    start_date=datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=55),
    default_args={"retries": 1, "retry_delay": timedelta(minutes=3)},
    tags=["leaguepedia", "players", "gold"],
)
def leaguepedia_active_players():
    @task(execution_timeout=timedelta(minutes=20))
    def collect_current_year():
        from jobs.leaguepedia.yearly import run

        # Current UTC year, independent of the legacy LEAGUEPEDIA_YEAR override.
        return run(
            raw_dir="/opt/airflow/data/bronze/leaguepedia",
            days_per_run=20,
            budget_seconds=600,
            revisit_after_seconds=86400,
            pipeline_name="leaguepedia_active_players",
        )

    @task.bash(execution_timeout=timedelta(minutes=10))
    def build_player_gold():
        return (
            "dbt build --project-dir /opt/airflow/dbt "
            "--profiles-dir /opt/airflow/dbt/profiles --target dev "
            "--select tag:leaguepedia_active --indirect-selection cautious "
            "--target-path /tmp/dbt-leaguepedia-active/target "
            "--log-path /tmp/dbt-leaguepedia-active/logs --fail-fast"
        )

    collect_current_year() >> build_player_gold()


leaguepedia_active_players()
