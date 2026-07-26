from __future__ import annotations

from datetime import datetime, timedelta

from airflow.sdk import dag, task


@dag(
    dag_id="pipeline_health_monitoring",
    description="Détecte les pipelines en échec ou obsolètes et notifie un webhook optionnel.",
    schedule="*/15 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=5),
    default_args={"retries": 1, "retry_delay": timedelta(minutes=2)},
    tags=["monitoring", "alerting", "audit"],
)
def pipeline_health_monitoring() -> None:
    @task(execution_timeout=timedelta(minutes=3))
    def check_health() -> dict:
        from jobs.monitoring.pipeline_health import run

        return run()

    check_health()


pipeline_health_monitoring()

