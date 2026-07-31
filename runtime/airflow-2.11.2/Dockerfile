FROM apache/airflow:2.11.2-python3.12@sha256:a69d3b7e8013f57338ca19a0bc4de862f62af178a21088cd4459f1081911c07c

USER root
COPY runtime/airflow-2.11.2/constraints.txt /opt/conformdag/constraints.txt
RUN python -m pip install --no-cache-dir -r /opt/conformdag/constraints.txt
COPY runtime/entrypoint.py /usr/local/bin/conformdag-runtime
RUN chmod 0555 /usr/local/bin/conformdag-runtime
USER airflow

ENV AIRFLOW__CORE__LOAD_EXAMPLES=False \
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=sqlite:////tmp/airflow/airflow.db \
    PYTHONPATH=/home/airflow/.local/lib/python3.12/site-packages \
    PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["python", "/usr/local/bin/conformdag-runtime"]
