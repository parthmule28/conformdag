from airflow import DAG
dag = DAG("benchmark_air_det_006_13", owner="platform", tags=["domain:data", "owner:platform"])
from airflow.operators.python import PythonOperator
PythonOperator(task_id="task", dag=dag)
