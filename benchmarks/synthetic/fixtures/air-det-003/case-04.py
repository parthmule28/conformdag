from airflow import DAG
dag = DAG("benchmark_air_det_003_04", owner="platform", tags=["domain:data", "owner:platform"])
from airflow.operators.empty import EmptyOperator
EmptyOperator(task_id="task", dag=dag, execution_timeout=86401)
