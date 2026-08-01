from airflow import DAG
dag = DAG("benchmark_air_det_001_33", owner="platform", tags=["domain:data", "owner:platform"])
