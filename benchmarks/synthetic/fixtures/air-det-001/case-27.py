from airflow import DAG
dag = DAG("benchmark_air_det_001_27", owner="platform", tags=["domain:data", "owner:platform"])
