"""Coach roster -> Match-V5 + timelines -> bronze -> raw -> existing Gold DAG."""
from datetime import timedelta

from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sdk import dag, task
from pendulum import datetime


@dag(dag_id='riot_coach_matches', schedule='35 * * * *',
     start_date=datetime(2026, 1, 1, tz='UTC'), catchup=False,
     max_active_runs=1, dagrun_timeout=timedelta(minutes=50),
     default_args={'retries':0}, tags=['riot','coach','roster','gold'])
def riot_coach_matches():
    @task(execution_timeout=timedelta(minutes=40))
    def collect_roster_matches():
        from airflow.exceptions import AirflowSkipException

        from jobs.riot.coach_matches import run

        result = run(raw_dir='/opt/airflow/data/bronze/riot')
        if not result['players']:
            raise AirflowSkipException('No coach roster configured')
        return result

    collect_roster_matches() >> TriggerDagRunOperator(
        task_id='refresh_gold', trigger_dag_id='dbt_transform',
        trigger_run_id='coach__{{ run_id }}', skip_when_already_exists=True,
        wait_for_completion=False,
    )


riot_coach_matches()
