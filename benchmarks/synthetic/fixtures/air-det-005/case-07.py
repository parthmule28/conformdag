from airflow import DAG
dag = DAG("benchmark_air_det_005_07", owner="platform", tags=["domain:data", "owner:platform"])
import requests
requests.get("https://example.invalid")
