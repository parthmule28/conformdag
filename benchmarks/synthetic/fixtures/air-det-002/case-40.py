from airflow import DAG
dag = DAG("benchmark_air_det_002_40", owner="platform", tags=["domain:data", "owner:platform"])
