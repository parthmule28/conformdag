from airflow import DAG
dag = DAG("benchmark_air_det_002_30", owner="platform", tags=["domain:data", "owner:platform"])
