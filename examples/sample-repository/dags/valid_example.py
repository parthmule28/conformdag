from datetime import timedelta

from airflow import DAG
from airflow.operators.empty import EmptyOperator
from pendulum import datetime

with DAG(
    dag_id="conformdag_valid_example",
    owner="platform",
    tags=["domain:data", "owner:platform"],
    start_date=datetime(2026, 1, 1, tz="UTC"),
    default_args={
        "execution_timeout": timedelta(hours=1),
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
    },
) as dag:
    EmptyOperator(task_id="start")
