from airflow import DAG
dag = DAG("benchmark_air_det_006_12", owner="platform", tags=["domain:data", "owner:platform"])
from airflow.operators.python import PythonOperator
PythonOperator(task_id="task", dag=dag)
