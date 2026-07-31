FROM apache/airflow:3.3.0-python3.12@sha256:2e43c8d61ebbad0ef6df6d6559bd3f3ddbc4d9cac7392029b13db00def6ba216

USER root
COPY runtime/airflow-3.3.0/constraints.txt /opt/conformdag/constraints.txt
RUN python -m pip install --no-cache-dir -r /opt/conformdag/constraints.txt
COPY runtime/entrypoint.py /usr/local/bin/conformdag-runtime
RUN chmod 0555 /usr/local/bin/conformdag-runtime
USER airflow

ENV AIRFLOW__CORE__LOAD_EXAMPLES=False \
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=sqlite:////tmp/airflow/airflow.db \
    PYTHONPATH=/home/airflow/.local/lib/python3.12/site-packages \
    PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["python", "/usr/local/bin/conformdag-runtime"]
