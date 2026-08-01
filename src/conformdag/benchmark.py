"""Versioned benchmark manifest and fixture verification primitives."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
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


def _empty_source_admissions() -> list[BenchmarkSourceAdmission]:
    return []


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
    source_admissions: list[BenchmarkSourceAdmission] = Field(
        default_factory=_empty_source_admissions
    )
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
class BenchmarkMetrics:
    """Normalized quality and operational metrics for one benchmark population."""

    applicable_cases: int
    violations: int
    valid_or_safe_counterexamples: int
    true_positives: int
    true_negatives: int
    false_positives: int
    false_negatives: int
    precision: float | None
    recall: float | None
    f1: float | None
    false_positive_rate: float | None
    false_negative_rate: float | None
    abstention_rate: float
    invalid_output_rate: float
    repeatability: float | None
    latency_seconds: float | None
    memory_bytes: int | None
    input_tokens: int | None
    output_tokens: int | None
    cost: float | None
    pricing_provenance: str | None
    cache_reuse_rate: float | None
    remediation_usefulness: float | None


@dataclass(frozen=True)
class BenchmarkQualityGate:
    """Per-population deterministic release-gate decision and explanation."""

    population: str
    passed: bool
    reasons: list[str]


@dataclass(frozen=True)
class BenchmarkBaseline:
    """Execution/provenance record for one benchmark baseline."""

    name: str
    mode: str
    status: str
    requested_model: str | None
    served_model: str | None
    prompt_hash: str | None
    cache_state: str
    reason: str | None = None


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
    metrics: dict[str, BenchmarkMetrics]
    quality_gates: list[BenchmarkQualityGate]
    baselines: list[BenchmarkBaseline]

    @property
    def passed(self) -> bool:
        return self.failed_cases == 0 and all(gate.passed for gate in self.quality_gates)

    def as_dict(self) -> dict[str, Any]:
        return {
            "report_version": "1",
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "benchmark_identity": self.benchmark_identity,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "passed": self.passed,
            "cases": [asdict(case) for case in self.cases],
            "metrics": {name: asdict(value) for name, value in self.metrics.items()},
            "quality_gates": [asdict(gate) for gate in self.quality_gates],
            "baselines": [asdict(baseline) for baseline in self.baselines],
        }


def render_benchmark_report(result: BenchmarkRunResult) -> str:
    """Render a concise human-readable benchmark report from normalized results."""
    lines = [
        "# ConformDAG Benchmark Report",
        "",
        f"- Dataset: `{result.dataset_id}` `{result.dataset_version}`",
        f"- Identity: `{result.benchmark_identity}`",
        f"- Result: **{'PASS' if result.passed else 'FAIL'}**",
        f"- Cases: {result.passed_cases}/{result.total_cases} passed",
        "",
        "## Deterministic metrics",
        "",
        "| Population | Cases | Precision | Recall | F1 | Gate |",
        "|---|---:|---:|---:|---:|---|",
    ]
    gate_by_name = {gate.population: gate for gate in result.quality_gates}
    for name, metrics in result.metrics.items():
        gate = gate_by_name[name]
        lines.append(
            f"| {name} | {metrics.applicable_cases} | "
            f"{metrics.precision if metrics.precision is not None else 'unknown'} | "
            f"{metrics.recall if metrics.recall is not None else 'unknown'} | "
            f"{metrics.f1 if metrics.f1 is not None else 'unknown'} | "
            f"{'PASS' if gate.passed else 'FAIL'} |"
        )
        if gate.reasons:
            lines.append(f"  - {name}: {'; '.join(gate.reasons)}")
    lines.extend(
        [
            "",
            "## Baselines",
            "",
            "| Baseline | Mode | Status | Reason |",
            "|---|---|---|---|",
        ]
    )
    for baseline in result.baselines:
        lines.append(
            f"| {baseline.name} | {baseline.mode} | {baseline.status} | {baseline.reason or ''} |"
        )
    lines.append("")
    return "\n".join(lines)


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


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _metrics(
    cases: list[BenchmarkCaseResult],
    labels: dict[str, str],
    elapsed_seconds: float,
) -> BenchmarkMetrics:
    violations = sum(labels[case.case_id] == "violation" for case in cases)
    valid = sum(labels[case.case_id] in {"valid", "safe-counterexample"} for case in cases)
    true_positives = sum(
        labels[case.case_id] == "violation" and case.actual_status == "FAIL" for case in cases
    )
    true_negatives = sum(
        labels[case.case_id] in {"valid", "safe-counterexample"} and case.actual_status == "PASS"
        for case in cases
    )
    false_positives = sum(
        labels[case.case_id] in {"valid", "safe-counterexample"} and case.actual_status == "FAIL"
        for case in cases
    )
    false_negatives = sum(
        labels[case.case_id] == "violation" and case.actual_status != "FAIL" for case in cases
    )
    precision = _ratio(true_positives, true_positives + false_positives)
    recall = _ratio(true_positives, true_positives + false_negatives)
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else None
    )
    count = len(cases)
    return BenchmarkMetrics(
        applicable_cases=count,
        violations=violations,
        valid_or_safe_counterexamples=valid,
        true_positives=true_positives,
        true_negatives=true_negatives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=precision,
        recall=recall,
        f1=f1,
        false_positive_rate=_ratio(false_positives, false_positives + true_negatives),
        false_negative_rate=_ratio(false_negatives, false_negatives + true_positives),
        abstention_rate=sum(case.actual_status == "NEEDS_REVIEW" for case in cases) / count,
        invalid_output_rate=sum(case.actual_status == "ERROR" for case in cases) / count,
        repeatability=None,
        latency_seconds=elapsed_seconds,
        memory_bytes=None,
        input_tokens=None,
        output_tokens=None,
        cost=None,
        pricing_provenance="not-applicable: deterministic offline baseline",
        cache_reuse_rate=None,
        remediation_usefulness=None,
    )


def _quality_gate(population: str, metrics: BenchmarkMetrics) -> BenchmarkQualityGate:
    reasons: list[str] = []
    if metrics.applicable_cases < 40:
        reasons.append("fewer than 40 applicable cases")
    if metrics.violations < 20:
        reasons.append("fewer than 20 violation cases")
    if metrics.valid_or_safe_counterexamples < 20:
        reasons.append("fewer than 20 valid or safe-counterexample cases")
    if metrics.precision is None or metrics.precision < 0.95:
        reasons.append("precision below 0.95")
    if metrics.recall is None or metrics.recall < 0.90:
        reasons.append("recall below 0.90")
    return BenchmarkQualityGate(population, not reasons, reasons)


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
    labels = {case.id: case.label for case in manifest.cases}
    started = perf_counter()

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
    elapsed = perf_counter() - started
    by_policy = {
        policy_id: [case for case in results if case.policy_id == policy_id]
        for policy_id in sorted({case.policy_id for case in manifest.cases})
    }
    metrics = {
        policy_id: _metrics(cases, labels, elapsed) for policy_id, cases in by_policy.items()
    }
    metrics["aggregate"] = _metrics(results, labels, elapsed)
    quality_gates = [
        _quality_gate(policy_id, policy_metrics) for policy_id, policy_metrics in metrics.items()
    ]
    baselines = [
        BenchmarkBaseline(
            name="deterministic",
            mode="deterministic-only",
            status="executed",
            requested_model=None,
            served_model=None,
            prompt_hash=None,
            cache_state="not-applicable",
        ),
        *[
            BenchmarkBaseline(
                name=name,
                mode=mode,
                status="not_executed",
                requested_model=None,
                served_model=None,
                prompt_hash=None,
                cache_state="not-used",
                reason="provider configuration was not supplied; benchmark is offline by default",
            )
            for name, mode in (
                ("llm-only", "llm-only"),
                ("hybrid", "hybrid"),
                ("generic-reviewer", "generic-reviewer"),
            )
        ],
    ]
    return BenchmarkRunResult(
        dataset_id=manifest.dataset_id,
        dataset_version=manifest.dataset_version,
        benchmark_identity=benchmark_identity(manifest),
        total_cases=len(results),
        passed_cases=passed,
        failed_cases=len(results) - passed,
        cases=results,
        metrics=metrics,
        quality_gates=quality_gates,
        baselines=baselines,
    )
