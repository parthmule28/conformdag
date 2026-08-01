from airflow import DAG
dag = DAG("benchmark_air_det_001_23", owner="platform", tags=["domain:data", "owner:platform"])
