from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow.sdk import dag, task

RAW_DIR = "/opt/airflow/data/bronze/riot"


@dag(
    dag_id="riot_live_spectator",
    description=(
        "Pipeline quasi temps réel (micro-batch toutes les 30 min) : capture des parties "
        "en cours des joueurs suivis via spectator-v5 (drafts/compositions live)."
    ),
    schedule="*/30 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=25),
    # Pas de retry : le prochain run (30 min) rattrape naturellement — inutile
    # d'insister sur un instantané par nature éphémère.
    default_args={"retries": 0},
    tags=["riot", "spectator", "realtime", "bronze"],
)
def riot_live_spectator() -> None:
    @task(execution_timeout=timedelta(minutes=20))
    def poll_live_games() -> dict:
        from jobs.riot.live_games import run

        return run(
            raw_dir=RAW_DIR,
            max_players=int(os.getenv("RIOT_LIVE_MAX_PLAYERS", "30")),
        )

    poll_live_games()


riot_live_spectator()
