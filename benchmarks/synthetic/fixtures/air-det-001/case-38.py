from airflow import DAG
dag = DAG("benchmark_air_det_001_38", owner="platform", tags=["domain:data", "owner:platform"])
