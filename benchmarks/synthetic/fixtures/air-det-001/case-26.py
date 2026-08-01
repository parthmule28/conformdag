from airflow import DAG
dag = DAG("benchmark_air_det_001_26", owner="platform", tags=["domain:data", "owner:platform"])
