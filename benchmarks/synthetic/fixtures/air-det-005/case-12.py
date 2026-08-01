from airflow import DAG
dag = DAG("benchmark_air_det_005_12", owner="platform", tags=["domain:data", "owner:platform"])
import requests
requests.get("https://example.invalid")
