"""Versioned benchmark manifest and fixture verification primitives."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import Field
from ruamel.yaml import YAML

from conformdag.analysis import SourceFile, analyze_source
from conformdag.evaluator import evaluate_deterministic
from conformdag.models import ConformModel, FindingStatus, PolicyPack
from conformdag.policy import load_policy_pack


class BenchmarkValidationError(ValueError):
    """Raised when a benchmark manifest or fixture cannot be trusted."""

    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        super().__init__("; ".join(issues))


class BenchmarkLicense(ConformModel):
    name: str
    url: str | None = None
    attribution: str | None = None


class BenchmarkSourceAdmission(ConformModel):
    source_id: str
    kind: Literal["synthetic", "public"]
    url: str
    revision: str
    paths: list[str] = Field(default_factory=list)
    license: BenchmarkLicense
    redistribution: Literal["redistributable", "fetch-only", "derived-only"]
    transformation: str
    privacy_review: str
    secrets_review: str
    derived_from: list[str] = Field(default_factory=list)


class BenchmarkExpectedLocation(ConformModel):
    file: str | None = None
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)


class BenchmarkCase(ConformModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]+$")
    fixture: Path
    fixture_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    policy_id: str
    source_id: str
    label: Literal[
        "violation",
        "valid",
        "safe-counterexample",
        "ambiguous",
        "exception",
        "adversarial",
    ]
    expected_applicable: bool
    expected_status: FindingStatus
    expected_location: BenchmarkExpectedLocation | None = None
    expected_evidence: str | None = None
    mutation_recipe: str | None = None
    seed: int | None = None


class BenchmarkManifest(ConformModel):
    schema_version: Literal["1"] = "1"
    dataset_id: str
    dataset_version: str
    license: BenchmarkLicense
    policy_versions: dict[str, str] = Field(default_factory=dict)
    policy_contract_hashes: dict[str, str] = Field(default_factory=dict)
    enforcement_hashes: dict[str, str] = Field(default_factory=dict)
    source_admissions: list[BenchmarkSourceAdmission] = Field(default_factory=list)
    cases: list[BenchmarkCase] = Field(min_length=1)


@dataclass(frozen=True)
class BenchmarkCaseResult:
    """Normalized result for one offline deterministic benchmark case."""

    case_id: str
    policy_id: str
    expected_status: str
    actual_status: str
    passed: bool
    finding_count: int
    error: str | None = None


@dataclass(frozen=True)
class BenchmarkRunResult:
    """Offline benchmark outcome with stable, machine-readable fields."""

    dataset_id: str
    dataset_version: str
    benchmark_identity: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    cases: list[BenchmarkCaseResult]

    @property
    def passed(self) -> bool:
        return self.failed_cases == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "benchmark_identity": self.benchmark_identity,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "passed": self.passed,
            "cases": [asdict(case) for case in self.cases],
        }


def _read_yaml(path: Path) -> Any:
    yaml = YAML(typ="safe")
    try:
        with path.open("r", encoding="utf-8") as stream:
            return yaml.load(stream)  # pyright: ignore[reportUnknownMemberType]
    except OSError as exc:
        raise BenchmarkValidationError([f"cannot read benchmark manifest {path}: {exc}"]) from exc
    except Exception as exc:
        raise BenchmarkValidationError([f"invalid YAML in {path}: {exc}"]) from exc


def load_benchmark_manifest(path: Path, repository_root: Path | None = None) -> BenchmarkManifest:
    """Load a manifest and verify every referenced fixture's content hash."""
    raw = _read_yaml(path)
    if not isinstance(raw, dict):
        raise BenchmarkValidationError([f"benchmark manifest {path} must contain a YAML mapping"])
    try:
        manifest = BenchmarkManifest.model_validate(raw)
    except ValueError as exc:
        raise BenchmarkValidationError([str(exc)]) from exc

    root = (repository_root or path.parent).resolve()
    issues: list[str] = []
    case_ids: set[str] = set()
    source_ids = {source.source_id for source in manifest.source_admissions}
    if len(source_ids) != len(manifest.source_admissions):
        issues.append("duplicate benchmark source admission ID")
    for case in manifest.cases:
        if case.id in case_ids:
            issues.append(f"duplicate benchmark case ID: {case.id}")
        case_ids.add(case.id)
        if case.source_id not in source_ids:
            issues.append(f"{case.id}: unknown source admission: {case.source_id}")
        fixture = case.fixture if case.fixture.is_absolute() else root / case.fixture
        if not fixture.is_file():
            issues.append(f"{case.id}: fixture does not exist: {fixture}")
            continue
        actual_hash = hashlib.sha256(fixture.read_bytes()).hexdigest()
        if actual_hash.lower() != case.fixture_sha256.lower():
            issues.append(
                f"{case.id}: fixture hash mismatch "
                f"(expected {case.fixture_sha256}, got {actual_hash})"
            )
    if issues:
        raise BenchmarkValidationError(issues)
    return manifest


def benchmark_manifest_payload(manifest: BenchmarkManifest) -> dict[str, Any]:
    """Return the normalized JSON-compatible manifest representation."""
    return manifest.model_dump(mode="json")


def benchmark_identity(manifest: BenchmarkManifest) -> str:
    """Return a stable identity that changes with policy or schema inputs."""
    payload = benchmark_manifest_payload(manifest)
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def run_deterministic_benchmark(
    manifest_path: Path,
    policy_pack_path: Path,
    repository_root: Path,
) -> BenchmarkRunResult:
    """Verify and execute a benchmark manifest using only local deterministic analysis."""
    fixture_root = manifest_path.parent.resolve()
    manifest = load_benchmark_manifest(manifest_path, fixture_root)
    pack: PolicyPack = load_policy_pack(policy_pack_path, repository_root.resolve())
    policies = {policy.id: policy for policy in pack.policies}
    results: list[BenchmarkCaseResult] = []

    for case in manifest.cases:
        policy = policies.get(case.policy_id)
        if policy is None:
            results.append(
                BenchmarkCaseResult(
                    case.id,
                    case.policy_id,
                    case.expected_status.value,
                    "ERROR",
                    False,
                    0,
                    "policy is not present in the selected policy pack",
                )
            )
            continue
        fixture = case.fixture if case.fixture.is_absolute() else fixture_root / case.fixture
        relative_path = fixture.relative_to(fixture_root).as_posix()
        source = SourceFile(
            path=fixture,
            relative_path=relative_path,
            content=fixture.read_text(encoding="utf-8"),
            content_hash=case.fixture_sha256,
        )
        model, parse_issue = analyze_source(source)
        if parse_issue or model is None:
            results.append(
                BenchmarkCaseResult(
                    case.id,
                    case.policy_id,
                    case.expected_status.value,
                    "ERROR",
                    False,
                    0,
                    parse_issue.message if parse_issue else "source analysis returned no model",
                )
            )
            continue
        findings, _, _ = evaluate_deterministic([policy], [model])
        statuses = {finding.status for finding in findings}
        actual = (
            FindingStatus.FAIL
            if FindingStatus.FAIL in statuses
            else FindingStatus.PASS
            if FindingStatus.PASS in statuses or not statuses
            else FindingStatus.NEEDS_REVIEW
            if FindingStatus.NEEDS_REVIEW in statuses
            else FindingStatus.ERROR
        )
        results.append(
            BenchmarkCaseResult(
                case.id,
                case.policy_id,
                case.expected_status.value,
                actual.value,
                actual is case.expected_status,
                len(findings),
            )
        )

    passed = sum(result.passed for result in results)
    return BenchmarkRunResult(
        dataset_id=manifest.dataset_id,
        dataset_version=manifest.dataset_version,
        benchmark_identity=benchmark_identity(manifest),
        total_cases=len(results),
        passed_cases=passed,
        failed_cases=len(results) - passed,
        cases=results,
    )
