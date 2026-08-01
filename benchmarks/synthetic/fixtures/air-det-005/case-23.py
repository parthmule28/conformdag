from airflow import DAG
dag = DAG("benchmark_air_det_005_23", owner="platform", tags=["domain:data", "owner:platform"])
import requests
value = 1
