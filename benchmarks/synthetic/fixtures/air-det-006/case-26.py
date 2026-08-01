from airflow import DAG
dag = DAG("benchmark_air_det_006_26", owner="platform", tags=["domain:data", "owner:platform"])
from airflow.operators.empty import EmptyOperator
EmptyOperator(task_id="task", dag=dag)
