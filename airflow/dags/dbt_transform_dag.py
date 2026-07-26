from __future__ import annotations

from datetime import datetime, timedelta

from airflow.sdk import dag, task

DBT_DIR = "/opt/airflow/dbt"
PROFILES_DIR = f"{DBT_DIR}/profiles"


@dag(
    dag_id="dbt_transform",
    description=(
        "ELT - étape Transform : dbt construit staging -> intermediate -> gold "
        "à partir de raw.riot_matches et reference.dim_*, puis exécute les tests dbt."
    ),
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=30),
    # 1 retry : utile si la base est momentanément indisponible ; un échec de test
    # de qualité dbt, lui, échouera de nouveau — c'est voulu (donnée à corriger).
    default_args={"retries": 1, "retry_delay": timedelta(minutes=3)},
    tags=["dbt", "elt", "gold"],
)
def dbt_transform() -> None:
    @task.bash(execution_timeout=timedelta(minutes=25))
    def dbt_build() -> str:
        # `dbt build` = run des modèles + exécution des tests de qualité de données.
        return (
            f"dbt build --project-dir {DBT_DIR} --profiles-dir {PROFILES_DIR} "
            "--target dev --fail-fast"
        )

    dbt_build()


dbt_transform()
