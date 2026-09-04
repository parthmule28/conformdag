FROM apache/airflow:3.3.0-python3.12@sha256:2e43c8d61ebbad0ef6df6d6559bd3f3ddbc4d9cac7392029b13db00def6ba216

USER root
COPY runtime/airflow-3.3.0/constraints.txt /opt/conformdag/constraints.txt
RUN apt-get update \
    && ACCEPT_EULA=Y apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && sed '/^apache-airflow-providers-google==/d' /opt/conformdag/constraints.txt > /tmp/conformdag-base-constraints.txt \
    && python -m pip install --no-cache-dir -r /tmp/conformdag-base-constraints.txt \
    && python -m pip install --no-cache-dir --upgrade \
        apache-airflow==3.3.0 \
        apache-airflow-providers-google==22.2.2 \
        google-cloud-aiplatform==1.155.0 \
        GitPython==3.1.58 \
        litellm==1.84.1 \
        pyasn1==0.6.4 \
        aiohttp==3.14.3 \
        cryptography==50.0.0 \
        snowflake-connector-python==4.7.1 \
        snowflake-sqlalchemy==1.11.0 \
        sqlparse==0.6.0 \
        tornado==6.5.8 \
    && rm -f /home/airflow/.local/bin/uv /home/airflow/.local/bin/uvx \
    && rm -f /tmp/conformdag-base-constraints.txt /opt/conformdag/constraints.txt
COPY runtime/entrypoint.py /usr/local/bin/conformdag-runtime
RUN chmod 0555 /usr/local/bin/conformdag-runtime
USER airflow

ENV AIRFLOW__CORE__LOAD_EXAMPLES=False \
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=sqlite:////tmp/airflow/airflow.db \
    PYTHONPATH=/home/airflow/.local/lib/python3.12/site-packages \
    PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["python", "/usr/local/bin/conformdag-runtime"]
