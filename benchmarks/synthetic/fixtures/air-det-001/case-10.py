from airflow import DAG
dag = DAG("benchmark_air_det_001_10", tags=["domain:data", "owner:platform"])
