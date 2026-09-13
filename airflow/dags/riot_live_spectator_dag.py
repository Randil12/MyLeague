from __future__ import annotations

from datetime import timedelta

from airflow.sdk import dag, task
from pendulum import datetime


@dag(
    dag_id="riot_live_spectator",
    description=(
        "Ancien pipeline spectator : remplacé par le service Docker riot-live en continu. "
        "Ce DAG reste visible pour conserver son historique, mais ne collecte plus."
    ),
    schedule=None,
    start_date=datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=25),
    # DAG conservé pour son historique ; la collecte tourne dans riot-live.
    default_args={"retries": 0},
    tags=["riot", "spectator", "realtime", "bronze"],
)
def riot_live_spectator() -> None:
    @task(execution_timeout=timedelta(minutes=20))
    def poll_live_games() -> dict:
        from airflow.exceptions import AirflowSkipException

        raise AirflowSkipException("Collecte remplacée par le service Docker riot-live.")

    poll_live_games()


riot_live_spectator()
