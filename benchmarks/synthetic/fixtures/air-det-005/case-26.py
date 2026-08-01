from airflow import DAG
dag = DAG("benchmark_air_det_005_26", owner="platform", tags=["domain:data", "owner:platform"])
import requests
value = 1
