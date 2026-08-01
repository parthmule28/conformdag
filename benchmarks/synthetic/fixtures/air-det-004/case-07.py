from airflow import DAG
dag = DAG("benchmark_air_det_004_07", owner="platform", tags=["domain:data", "owner:platform"])
from airflow.operators.empty import EmptyOperator
EmptyOperator(task_id="task", dag=dag, retries=6, retry_delay=3601)
