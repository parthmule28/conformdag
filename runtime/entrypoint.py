"""Run the constrained Airflow import observation inside a runtime image."""

from __future__ import annotations

import argparse
import inspect
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


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


def _stage_sources(repository_root: Path, manifest: dict[str, Any], target: Path) -> None:
    """Copy only selected, non-symlinked Python inputs into the runtime workspace."""
    excluded = [str(pattern) for pattern in manifest.get("exclude", [])]
    selected: set[Path] = set()
    for pattern in manifest.get("include", []):
        for candidate in repository_root.glob(str(pattern)):
            if not candidate.is_file() or candidate.is_symlink() or candidate.suffix != ".py":
                continue
            relative = candidate.relative_to(repository_root)
            if any(relative.match(pattern) for pattern in excluded):
                continue
            selected.add(relative)
    for relative in sorted(selected):
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repository_root / relative, destination)


def normalize_import_errors(
    import_errors: dict[str, object], dag_folder: Path, staging_root: Path
) -> dict[str, str]:
    """Remove random container staging paths from report-visible diagnostics."""
    normalized: dict[str, str] = {}
    for raw_path, error in import_errors.items():
        path = Path(raw_path)
        try:
            key = str(path.relative_to(dag_folder))
        except ValueError:
            key = path.name
        normalized[key] = str(error).replace(str(staging_root), "<runtime>")
    return normalized


def main() -> None:
    args = _arguments()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    repository_root = Path("/workspace")
    os.environ["AIRFLOW_HOME"] = "/tmp/airflow"  # noqa: S108 - container tmpfs
    os.environ["AIRFLOW__CORE__LOAD_EXAMPLES"] = "False"
    os.environ["AIRFLOW__CORE__DAGS_FOLDER"] = "/tmp/conformdag-dags"  # noqa: S108
    os.environ["AIRFLOW__LOGGING__BASE_LOG_FOLDER"] = "/tmp/airflow/logs"  # noqa: S108
    os.environ["AIRFLOW__SCHEDULER__CHILD_PROCESS_LOG_DIRECTORY"] = "/tmp/airflow/logs/scheduler"  # noqa: S108
    os.environ["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"] = "sqlite:////tmp/airflow/airflow.db"

    from airflow.models import DagBag

    with tempfile.TemporaryDirectory(prefix="conformdag-", dir="/tmp") as staging:
        dag_folder = Path(staging) / "dags"
        dag_folder.mkdir()
        _stage_sources(repository_root, manifest, dag_folder)
        dagbag_options = {
            "dag_folder": str(dag_folder),
            "include_examples": False,
            "safe_mode": False,
        }
        supported_options = inspect.signature(DagBag).parameters
        dagbag = DagBag(
            **{name: value for name, value in dagbag_options.items() if name in supported_options}
        )
        import_errors = normalize_import_errors(
            dagbag.import_errors,
            dag_folder,
            Path(staging),
        )
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
