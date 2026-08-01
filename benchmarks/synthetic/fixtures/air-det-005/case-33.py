from airflow import DAG
dag = DAG("benchmark_air_det_005_33", owner="platform", tags=["domain:data", "owner:platform"])
import requests
value = 1
