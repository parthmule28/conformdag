"""Build and execute one real Dockerized Airflow runtime profile."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from conformdag.models import AirflowProfile, FindingStatus, RuntimeManifest
from conformdag.runtime import DockerRunner, RuntimePhaseError


def main() -> int:
    raw_profile = os.environ.get("CONFORMDAG_RUNTIME_PROFILE")
    if raw_profile not in {profile.value for profile in AirflowProfile}:
        print("CONFORMDAG_RUNTIME_PROFILE must be 2.11.2 or 3.3.0", file=sys.stderr)
        return 2

    profile = AirflowProfile(raw_profile)
    root = Path.cwd().resolve()
    dockerfile = root / "runtime" / f"airflow-{profile.value}" / "Dockerfile"
    image = f"conformdag-airflow-smoke:{profile.value}"
    runner = DockerRunner()
    try:
        runner.require_daemon()
        build = runner.run(
            ["build", "-f", str(dockerfile), "-t", image, str(root)],
            timeout_seconds=1800,
        )
        if build.returncode != 0:
            raise RuntimePhaseError(build.stderr.strip() or "runtime image build failed")

        with tempfile.TemporaryDirectory(prefix="conformdag-runtime-") as temporary:
            repository = Path(temporary)
            dags = repository / "dags"
            dags.mkdir()
            (dags / "smoke.py").write_text(
                "import pendulum\n"
                "from airflow import DAG\n"
                "from airflow.operators.empty import EmptyOperator\n"
                "with DAG(dag_id='conformdag_runtime_smoke', "
                "start_date=pendulum.datetime(2024, 1, 1, tz='UTC'), "
                "schedule=None, catchup=False) as dag:\n"
                "    EmptyOperator(task_id='start')\n",
                encoding="utf-8",
            )
            manifest = RuntimeManifest(
                repository_root=repository,
                include=["dags/**/*.py"],
                exclude=["**/.git/**"],
                policy_ids=["AIR-DET-001"],
                airflow_profile=profile,
                image=image,
                supported_profile=True,
                network_enabled=False,
                timeout_seconds=60,
            )
            observations = runner.run_manifest(manifest, image, timeout_seconds=90)

        if not observations or any(
            observation.status is FindingStatus.ERROR for observation in observations
        ):
            raise RuntimePhaseError("runtime smoke test did not return a successful observation")
    except RuntimePhaseError as exc:
        print(f"runtime smoke test failed: {exc}", file=sys.stderr)
        return 1

    print(f"Airflow {profile.value} runtime smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
