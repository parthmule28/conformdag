from datetime import timedelta

from airflow import DAG
from airflow.operators.empty import EmptyOperator

with DAG(
    dag_id="conformdag_valid_example",
    owner="platform",
    tags=["domain:data", "owner:platform"],
    default_args={
        "execution_timeout": timedelta(hours=1),
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
    },
) as dag:
    EmptyOperator(task_id="start")
