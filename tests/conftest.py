"""Shared pytest fixtures for the fix-engine test suite."""

from collections.abc import Callable
from pathlib import Path
from shutil import copyfile

import pytest

VIOLATIONS_PY = '''\
"""DAG with mechanical policy violations."""

from airflow.sdk import DAG
from airflow.providers.standard.operators.python import PythonOperator


def _extract():
    return 1


with DAG(dag_id="violations", schedule=None) as dag:
    extract = PythonOperator(
        task_id="extract",
        python_callable=_extract,
        retries=9,
    )
    load = PythonOperator(
        task_id="load",
        python_callable=_extract,
        execution_timeout=timedelta(seconds=100000),
    )
'''

FORBIDDEN_PY = '''\
"""DAG with a forbidden operator import."""

from airflow.operators.python import PythonOperator

with DAG(dag_id="forbidden", schedule=None) as dag:
    task = PythonOperator(task_id="task", python_callable=lambda: None)
'''


@pytest.fixture(name="build_repository")
def build_repository_fixture() -> Callable[[Path], Path]:
    """Provide a factory building a scan-ready repository with one violating DAG."""

    def build(root: Path) -> Path:
        (root / "policies").mkdir(parents=True)
        (root / "standards").mkdir(parents=True)
        (root / "dags").mkdir(parents=True)
        copyfile("policies/pack.yaml", root / "policies/pack.yaml")
        copyfile("standards/dag-authoring.md", root / "standards/dag-authoring.md")
        (root / "conformdag.yaml").write_text(
            'config_version: "1"\nscan:\n  policy_pack: policies/pack.yaml\n',
            encoding="utf-8",
        )
        (root / "dags" / "violations.py").write_text(
            "from datetime import timedelta\n" + VIOLATIONS_PY, encoding="utf-8"
        )
        return root

    return build
