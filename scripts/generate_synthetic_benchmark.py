"""Generate the provenance-aware deterministic benchmark corpus."""

from __future__ import annotations

import hashlib
from pathlib import Path

from ruamel.yaml import YAML

from conformdag.benchmark import BenchmarkManifest, BenchmarkSourceAdmission
from conformdag.policy import load_policy_pack, policy_contract_hash, policy_enforcement_hash

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "benchmarks" / "synthetic"
PUBLIC_SOURCES = ROOT / "benchmarks" / "public-sources.yaml"

MUTATION_RECIPES = {
    "missing-owner-v1": "Remove the DAG owner field.",
    "missing-required-tags-v1": "Remove the required DAG tags.",
    "timeout-above-maximum-v1": "Set task execution timeout above the policy maximum.",
    "retry-bounds-exceeded-v1": "Set task retries and delay above policy bounds.",
    "module-scope-network-call-v1": "Add a module-scope outbound HTTP call.",
    "forbidden-operator-v1": "Replace the allowed operator with a forbidden operator.",
}


def _dag(name: str, *, owner: str | None = "platform", tags: bool = True) -> str:
    owner_text = f', owner="{owner}"' if owner is not None else ""
    tags_text = ', tags=["domain:data", "owner:platform"]' if tags else ""
    return f'from airflow import DAG\ndag = DAG("{name}"{owner_text}{tags_text})\n'


def _fixture(policy_id: str, index: int, violation: bool) -> tuple[str, str | None]:
    name = f"benchmark_{policy_id.lower().replace('-', '_')}_{index:02d}"
    if policy_id == "AIR-DET-001":
        return (
            _dag(name, owner=None if violation else "platform"),
            "missing-owner-v1" if violation else None,
        )
    if policy_id == "AIR-DET-002":
        return _dag(name, tags=not violation), "missing-required-tags-v1" if violation else None
    if policy_id == "AIR-DET-003":
        timeout = 86401 if violation else 3600
        return _dag(name) + (
            "from airflow.operators.empty import EmptyOperator\n"
            f'EmptyOperator(task_id="task", dag=dag, execution_timeout={timeout})\n'
        ), "timeout-above-maximum-v1" if violation else None
    if policy_id == "AIR-DET-004":
        retries = 6 if violation else 2
        delay = 3601 if violation else 60
        return _dag(name) + (
            "from airflow.operators.empty import EmptyOperator\n"
            f'EmptyOperator(task_id="task", dag=dag, retries={retries}, retry_delay={delay})\n'
        ), "retry-bounds-exceeded-v1" if violation else None
    if policy_id == "AIR-DET-005":
        return _dag(name) + (
            "import requests\n"
            + ('requests.get("https://example.invalid")\n' if violation else "value = 1\n")
        ), "module-scope-network-call-v1" if violation else None
    if policy_id == "AIR-DET-006":
        operator = "PythonOperator" if violation else "EmptyOperator"
        module = "airflow.operators.python" if violation else "airflow.operators.empty"
        return _dag(name) + (
            f'from {module} import {operator}\n{operator}(task_id="task", dag=dag)\n'
        ), "forbidden-operator-v1" if violation else None
    raise ValueError(f"unsupported deterministic policy: {policy_id}")


def main() -> None:
    pack = load_policy_pack(ROOT / "policies" / "pack.yaml", ROOT)
    deterministic = [policy for policy in pack.policies if policy.id.startswith("AIR-DET-")]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, object]] = []
    public_raw = YAML(typ="safe").load(PUBLIC_SOURCES.read_text(encoding="utf-8"))
    public_sources = [
        BenchmarkSourceAdmission.model_validate(item) for item in public_raw["sources"]
    ]
    synthetic_source = BenchmarkSourceAdmission(
        source_id="conformdag-synthetic-generator",
        kind="synthetic",
        url="https://github.com/parthmule28/conformdag",
        revision="synthetic-deterministic-v2",
        license={"name": "Apache-2.0", "url": "https://www.apache.org/licenses/LICENSE-2.0"},
        redistribution="redistributable",
        transformation=(
            "Project-owned fixtures generated from named deterministic recipes; "
            "recipe patterns were reviewed against the admitted public source references."
        ),
        privacy_review="Completed: generated source contains no organizational data.",
        secrets_review="Completed: generated source contains no credentials or secret material.",
        derived_from=[source.source_id for source in public_sources],
    )
    for policy in sorted(deterministic, key=lambda item: item.id):
        for index in range(1, 41):
            violation = index <= 20
            label = "violation" if violation else ("safe-counterexample" if index % 2 else "valid")
            content, recipe = _fixture(policy.id, index, violation)
            if recipe is not None and recipe not in MUTATION_RECIPES:
                raise ValueError(f"unregistered mutation recipe: {recipe}")
            relative = Path("fixtures") / policy.id.lower() / f"case-{index:02d}.py"
            fixture = OUTPUT / relative
            fixture.parent.mkdir(parents=True, exist_ok=True)
            fixture.write_text(content, encoding="utf-8")
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            cases.append(
                {
                    "id": f"{policy.id.lower()}-{index:02d}",
                    "fixture": relative.as_posix(),
                    "fixture_sha256": digest,
                    "policy_id": policy.id,
                    "source_id": synthetic_source.source_id,
                    "label": label,
                    "expected_applicable": True,
                    "expected_status": "FAIL" if violation else "PASS",
                    "expected_location": {"file": relative.as_posix()},
                    "expected_evidence": "synthetic fixture generated from the policy recipe",
                    "mutation_recipe": recipe,
                    "seed": index,
                }
            )
    manifest = BenchmarkManifest(
        dataset_id="conformdag-synthetic-deterministic",
        dataset_version="2026.08.1",
        license={"name": "Apache-2.0", "url": "https://www.apache.org/licenses/LICENSE-2.0"},
        policy_versions={policy.id: policy.version for policy in deterministic},
        policy_contract_hashes={
            policy.id: policy_contract_hash(policy) for policy in deterministic
        },
        enforcement_hashes={policy.id: policy_enforcement_hash(policy) for policy in deterministic},
        source_admissions=[*public_sources, synthetic_source],
        cases=cases,
    )
    yaml = YAML()
    yaml.default_flow_style = False
    with (OUTPUT / "manifest.yaml").open("w", encoding="utf-8") as stream:
        yaml.dump(manifest.model_dump(mode="json"), stream)


if __name__ == "__main__":
    main()
