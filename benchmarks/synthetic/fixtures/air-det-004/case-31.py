from airflow import DAG
dag = DAG("benchmark_air_det_004_31", owner="platform", tags=["domain:data", "owner:platform"])
from airflow.operators.empty import EmptyOperator
EmptyOperator(task_id="task", dag=dag, retries=2, retry_delay=60)
