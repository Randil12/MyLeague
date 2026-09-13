"""Opt-in computation: enable the Compose spark profile before triggering this DAG."""
from datetime import timedelta

from airflow.sdk import dag, task
from pendulum import datetime


@dag(dag_id="spark_matchups", schedule=None,
     start_date=datetime(2026, 1, 1, tz="UTC"), catchup=False,
     max_active_runs=1, dagrun_timeout=timedelta(minutes=25),
     default_args={"retries": 0}, tags=["spark", "distributed", "gold"])
def spark_matchups():
    @task(execution_timeout=timedelta(minutes=22))
    def compute():
        from urllib.request import Request, urlopen

        # Only a fixed internal endpoint; no Docker socket or SSH credentials in Airflow.
        with urlopen(Request("http://spark-runner:8090/run", data=b"", method="POST"),
                     timeout=1260) as response:
            return response.read().decode("utf-8")

    compute()


spark_matchups()
