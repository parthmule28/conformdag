"""Run the constrained Airflow import observation inside a runtime image."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from airflow.models import DagBag


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args()


def _observation(
    policy_id: str, status: str, message: str | None, **payload: Any
) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "status": status,
        "policy_id": policy_id,
        "message": message,
        "payload": payload,
    }


def main() -> None:
    args = _arguments()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    repository_root = Path("/workspace")
    os.environ.setdefault("AIRFLOW_HOME", "/tmp/airflow")  # noqa: S108 - container tmpfs
    os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "False")
    os.environ.setdefault(
        "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN", "sqlite:////tmp/airflow/airflow.db"
    )

    dagbag = DagBag(
        dag_folder=str(repository_root),
        include_examples=False,
        safe_mode=False,
    )
    import_errors = {str(path): str(error) for path, error in dagbag.import_errors.items()}
    observations: list[dict[str, Any]] = []
    for policy_id in manifest["policy_ids"]:
        if import_errors:
            observations.append(
                _observation(
                    policy_id,
                    "ERROR",
                    "Airflow DAG import failed",
                    dag_ids=sorted(dagbag.dags),
                    import_errors=import_errors,
                    airflow_profile=manifest.get("airflow_profile"),
                )
            )
        else:
            observations.append(
                _observation(
                    policy_id,
                    "PASS",
                    None,
                    dag_ids=sorted(dagbag.dags),
                    airflow_profile=manifest.get("airflow_profile"),
                )
            )
    print(json.dumps({"observations": observations}, sort_keys=True))


if __name__ == "__main__":
    main()
