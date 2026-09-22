"""Tests for the reusable application scan workflow."""

from collections.abc import Callable, Sequence
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from conformdag.analysis import ParseCache
from conformdag.application import (
    BaselineInput,
    RuntimeExecutionError,
    ScanExecutionResult,
    ScanInputError,
    ScanOptions,
    execute_scan,
)
from conformdag.models import (
    AirflowProfile,
    Confidence,
    Finding,
    FindingStatus,
    ProjectRuntimeConfig,
    RunIssue,
    RunMetadata,
    RuntimeObservation,
    ScanReport,
    SemanticRequest,
    SemanticResponse,
    Suppression,
)
from conformdag.scan import SemanticProvider, scan_repository
from conformdag.semantic import SemanticProviderError


def _complete_report() -> ScanReport:
    return ScanReport(
        complete=True,
        result_fingerprint="core-result",
        findings=[],
        issues=[],
        run=RunMetadata(
            tool_version="test",
            policy_pack_id="test-pack",
            policy_pack_version="1",
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    )


class _SemanticProvider:
    def evaluate_many(
        self,
        requests: Sequence[SemanticRequest],
        max_concurrency: int = 4,
    ) -> list[SemanticResponse]:
        assert max_concurrency == 4
        return [
            SemanticResponse(
                status="NEEDS_REVIEW",
                evidence="bounded evidence",
                explanation="manual review is required",
                confidence=Confidence.MEDIUM,
                served_model="test-model",
                usage={"total_tokens": 10},
            )
            for _ in requests
        ]


class _FailingSemanticProvider:
    def evaluate_many(
        self,
        requests: Sequence[SemanticRequest],
        max_concurrency: int = 4,
    ) -> list[SemanticResponse]:
        raise SemanticProviderError("semantic service unavailable")


def _make_semantic_repository(build_repository: Callable[[Path], Path], root: Path) -> Path:
    repository = build_repository(root)
    (repository / "dags" / "violations.py").write_text(
        "from airflow import DAG\ndag = DAG(owner='platform')\n",
        encoding="utf-8",
    )
    return repository


def _count_core_calls(monkeypatch: pytest.MonkeyPatch, calls: list[int]) -> None:
    def counted_scan(
        repository_root: Path,
        policy_pack: Path | None = None,
        *,
        semantic_provider: SemanticProvider | None = None,
        semantic_provider_name: str | None = None,
        semantic_model: str | None = None,
        semantic_native_structured_output: bool | None = None,
        airflow_profile: AirflowProfile | None = None,
        parse_cache: ParseCache | None = None,
    ) -> ScanReport:
        calls.append(1)
        return scan_repository(
            repository_root,
            policy_pack,
            semantic_provider=semantic_provider,
            semantic_provider_name=semantic_provider_name,
            semantic_model=semantic_model,
            semantic_native_structured_output=semantic_native_structured_output,
            airflow_profile=airflow_profile,
            parse_cache=parse_cache,
        )

    monkeypatch.setattr("conformdag.application.scan.scan_repository", counted_scan)


class _FakeRuntimeExecutor:
    def __init__(
        self,
        events: list[str],
        *,
        observations: list[RuntimeObservation] | None = None,
        image_digest: str = "sha256:runtime-image",
        validation_error: ScanInputError | None = None,
        execution_error: Exception | None = None,
    ) -> None:
        self.events = events
        self.observations = observations if observations is not None else []
        self.image_digest = image_digest
        self.validation_error = validation_error
        self.execution_error = execution_error
        self.validation_args: tuple[Path, ProjectRuntimeConfig, list[str], list[str]] | None = None
        self.execution_args: tuple[Path, ProjectRuntimeConfig, list[str], list[str], list[str]] | None = None

    def validate(
        self,
        root: Path,
        config: ProjectRuntimeConfig,
        include: list[str],
        exclude: list[str],
    ) -> None:
        self.events.append("validate")
        self.validation_args = (root, config, include, exclude)
        if self.validation_error is not None:
            raise self.validation_error

    def execute(
        self,
        root: Path,
        config: ProjectRuntimeConfig,
        policy_ids: list[str],
        include: list[str],
        exclude: list[str],
    ) -> tuple[list[RuntimeObservation], str]:
        self.events.append("execute")
        self.execution_args = (root, config, policy_ids, include, exclude)
        if self.execution_error is not None:
            raise self.execution_error
        return self.observations, self.image_digest


def _configure_runtime_repository(root: Path) -> None:
    (root / "conformdag.yaml").write_text(
        'config_version: "1"\n'
        "scan:\n"
        "  policy_pack: policies/pack.yaml\n"
        "  include:\n"
        '    - "custom/**/*.py"\n'
        "  exclude:\n"
        '    - "custom/**/skip.py"\n',
        encoding="utf-8",
    )


def _install_core_stub(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    report: ScanReport,
) -> None:
    def fake_scan(
        repository_root: Path,
        policy_pack: Path | None = None,
        **kwargs: object,
    ) -> ScanReport:
        events.append("core")
        return report

    monkeypatch.setattr("conformdag.application.scan.scan_repository", fake_scan)


def _finding_from_repository(build_repository: Callable[[Path], Path], root: Path) -> Finding:
    repository = build_repository(root)
    report = scan_repository(repository)
    return next(finding for finding in report.findings if finding.policy_id == "AIR-DET-001")


def _suppression_for_finding(
    finding: Finding,
    current: datetime,
    *,
    reason: str,
    days_until_expiry: int = 1,
    fingerprint: str | None = None,
) -> Suppression:
    return Suppression(
        fingerprint=fingerprint or finding.fingerprint,
        policy_id=finding.policy_id,
        reason=reason,
        owner="platform",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        expires_at=current + timedelta(days=days_until_expiry),
    )


def test_scan_options_has_only_the_c06_fields() -> None:
    assert [item.name for item in fields(ScanOptions)] == [
        "repository_root",
        "policy_pack",
        "airflow_profile",
    ]
    options = ScanOptions(Path("repo"))
    assert options.policy_pack is None
    assert options.airflow_profile is None
    frozen_field = "policy_pack"
    with pytest.raises(FrozenInstanceError):
        setattr(options, frozen_field, Path("policies/pack.yaml"))


def test_baseline_input_defaults_to_no_baseline() -> None:
    assert [item.name for item in fields(BaselineInput)] == ["report", "fingerprints"]
    baseline = BaselineInput()
    assert baseline.report is None
    assert baseline.fingerprints is None
    frozen_field = "report"
    with pytest.raises(FrozenInstanceError):
        setattr(baseline, frozen_field, _complete_report())


def test_scan_execution_result_has_only_the_c06_fields() -> None:
    assert [item.name for item in fields(ScanExecutionResult)] == ["report", "gate_result"]
    result = ScanExecutionResult(report=_complete_report(), gate_result=None)
    frozen_field = "gate_result"
    with pytest.raises(FrozenInstanceError):
        setattr(result, frozen_field, None)


def test_execute_scan_calls_core_once_and_passes_semantic_inputs(
    build_repository: Callable[[Path], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = build_repository(tmp_path / "repo")
    calls: list[dict[str, object]] = []

    def fake_scan(
        repository_root: Path,
        policy_pack: Path | None = None,
        *,
        semantic_provider: SemanticProvider | None = None,
        semantic_provider_name: str | None = None,
        semantic_model: str | None = None,
        semantic_native_structured_output: bool | None = None,
        airflow_profile: AirflowProfile | None = None,
        parse_cache: ParseCache | None = None,
    ) -> ScanReport:
        calls.append(
            {
                "repository_root": repository_root,
                "policy_pack": policy_pack,
                "semantic_provider": semantic_provider,
                "semantic_provider_name": semantic_provider_name,
                "semantic_model": semantic_model,
                "semantic_native_structured_output": semantic_native_structured_output,
                "airflow_profile": airflow_profile,
                "parse_cache": parse_cache,
            }
        )
        return _complete_report()

    monkeypatch.setattr("conformdag.application.scan.scan_repository", fake_scan)
    provider = _SemanticProvider()
    profile = AirflowProfile.AIRFLOW_3_3_0

    result = execute_scan(
        ScanOptions(root, airflow_profile=profile),
        semantic_provider=provider,
        semantic_provider_name="test-provider",
        semantic_model="test-model",
        semantic_native_structured_output=True,
    )

    assert len(calls) == 1
    assert calls[0] == {
        "repository_root": root.resolve(),
        "policy_pack": None,
        "semantic_provider": provider,
        "semantic_provider_name": "test-provider",
        "semantic_model": "test-model",
        "semantic_native_structured_output": True,
        "airflow_profile": profile,
        "parse_cache": None,
    }
    assert result.report.complete is True


def test_execute_scan_rejects_semantic_provider_without_model_before_core_call(
    build_repository: Callable[[Path], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = build_repository(tmp_path / "repo")
    calls: list[int] = []
    _count_core_calls(monkeypatch, calls)

    with pytest.raises(ScanInputError, match="model"):
        execute_scan(ScanOptions(root), semantic_provider=_SemanticProvider())

    assert calls == []


def test_execute_scan_rejects_incomplete_baseline_before_core_call(
    build_repository: Callable[[Path], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = build_repository(tmp_path / "repo")
    calls: list[int] = []
    _count_core_calls(monkeypatch, calls)
    baseline_report = _complete_report().model_copy(update={"complete": False})

    with pytest.raises(ScanInputError, match="incomplete"):
        execute_scan(ScanOptions(root), baseline=BaselineInput(report=baseline_report))

    assert calls == []


def test_execute_scan_rejects_two_baseline_forms_before_core_call(
    build_repository: Callable[[Path], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = build_repository(tmp_path / "repo")
    calls: list[int] = []
    _count_core_calls(monkeypatch, calls)

    with pytest.raises(ScanInputError, match="both"):
        execute_scan(
            ScanOptions(root),
            baseline=BaselineInput(report=_complete_report(), fingerprints=frozenset({"existing"})),
        )

    assert calls == []


def test_execute_scan_runs_semantic_success_inside_one_core_call(
    build_repository: Callable[[Path], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _make_semantic_repository(build_repository, tmp_path / "semantic-repo")
    calls: list[int] = []
    _count_core_calls(monkeypatch, calls)

    result = execute_scan(
        ScanOptions(root),
        semantic_provider=_SemanticProvider(),
        semantic_provider_name="test-provider",
        semantic_model="test-model",
    )

    semantic_findings = [finding for finding in result.report.findings if finding.enforcement.value == "semantic"]
    assert calls == [1]
    assert len(semantic_findings) == 4
    assert result.report.run.semantic_provider == "test-provider"
    assert result.report.run.semantic_model == "test-model"
    assert len(result.report.run.semantic_runs) == 4
    assert all(run.usage == {"total_tokens": 10} for run in result.report.run.semantic_runs)


def test_execute_scan_reports_semantic_provider_failure_inside_one_core_call(
    build_repository: Callable[[Path], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _make_semantic_repository(build_repository, tmp_path / "semantic-repo")
    calls: list[int] = []
    _count_core_calls(monkeypatch, calls)

    result = execute_scan(
        ScanOptions(root),
        semantic_provider=_FailingSemanticProvider(),
        semantic_provider_name="test-provider",
        semantic_model="test-model",
    )

    provider_issues = [issue for issue in result.report.issues if issue.code == "SEMANTIC_PROVIDER_ERROR"]
    assert calls == [1]
    assert result.report.complete is False
    assert len(provider_issues) == 1
    assert provider_issues[0].fatal is True
    assert provider_issues[0].message == "semantic service unavailable"


def test_execute_scan_validates_then_executes_runtime_and_records_sorted_results(
    build_repository: Callable[[Path], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = build_repository(tmp_path / "repo")
    _configure_runtime_repository(root)
    events: list[str] = []
    core_report = _complete_report().model_copy(
        update={
            "policies_evaluated": ["POLICY-B", "POLICY-A"],
            "policies_skipped": ["POLICY-C", "POLICY-A"],
        }
    )
    _install_core_stub(monkeypatch, events, core_report)
    profile = AirflowProfile.AIRFLOW_3_3_0
    runtime_config = ProjectRuntimeConfig(enabled=True, airflow_version=profile, timeout_seconds=123)
    observations = [
        RuntimeObservation(policy_id="POLICY-Z", status=FindingStatus.PASS),
        RuntimeObservation(policy_id="POLICY-A", status=FindingStatus.FAIL, message="runtime finding failed"),
        RuntimeObservation(policy_id="POLICY-B", status=FindingStatus.PASS),
    ]
    executor = _FakeRuntimeExecutor(events, observations=observations)

    result = execute_scan(
        ScanOptions(root),
        runtime_config=runtime_config,
        runtime_executor=executor,
    )

    include = ["custom/**/*.py"]
    exclude = ["custom/**/skip.py"]
    assert events == ["validate", "core", "execute"]
    assert executor.validation_args == (root.resolve(), runtime_config, include, exclude)
    assert executor.execution_args == (
        root.resolve(),
        runtime_config,
        ["POLICY-A", "POLICY-B", "POLICY-C"],
        include,
        exclude,
    )
    assert [(item.policy_id, item.status) for item in result.report.runtime_observations] == [
        ("POLICY-A", FindingStatus.FAIL),
        ("POLICY-B", FindingStatus.PASS),
        ("POLICY-Z", FindingStatus.PASS),
    ]
    assert result.report.complete is True
    assert result.report.run.runtime_profile is profile
    assert result.report.run.runtime_image_digest == "sha256:runtime-image"
    assert result.report.run.resolved_configuration["runtime"] == {
        "enabled": True,
        "airflow_profile": "3.3.0",
        "supported_profile": True,
        "network_enabled": False,
        "timeout_seconds": 123,
    }


def test_execute_scan_skips_disabled_runtime(
    build_repository: Callable[[Path], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = build_repository(tmp_path / "repo")
    events: list[str] = []
    _install_core_stub(monkeypatch, events, _complete_report())
    executor = _FakeRuntimeExecutor(events)

    result = execute_scan(
        ScanOptions(root),
        runtime_config=ProjectRuntimeConfig(enabled=False),
        runtime_executor=executor,
    )

    assert events == ["core"]
    assert executor.validation_args is None
    assert executor.execution_args is None
    assert result.report.runtime_observations == []
    assert result.report.run.runtime_profile is None


def test_execute_scan_requires_executor_before_core_for_enabled_runtime(
    build_repository: Callable[[Path], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = build_repository(tmp_path / "repo")
    events: list[str] = []
    _install_core_stub(monkeypatch, events, _complete_report())

    with pytest.raises(ScanInputError, match="RuntimeExecutor"):
        execute_scan(
            ScanOptions(root),
            runtime_config=ProjectRuntimeConfig(enabled=True, airflow_version=AirflowProfile.AIRFLOW_3_3_0),
        )

    assert events == []


def test_execute_scan_runtime_validation_failure_prevents_core_call(
    build_repository: Callable[[Path], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = build_repository(tmp_path / "repo")
    events: list[str] = []
    _install_core_stub(monkeypatch, events, _complete_report())
    executor = _FakeRuntimeExecutor(events, validation_error=ScanInputError("invalid runtime manifest"))

    with pytest.raises(ScanInputError, match="invalid runtime manifest"):
        execute_scan(
            ScanOptions(root),
            runtime_config=ProjectRuntimeConfig(enabled=True, airflow_version=AirflowProfile.AIRFLOW_3_3_0),
            runtime_executor=executor,
        )

    assert events == ["validate"]


def test_execute_scan_runs_runtime_even_if_core_report_is_incomplete(
    build_repository: Callable[[Path], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = build_repository(tmp_path / "repo")
    events: list[str] = []
    incomplete_report = _complete_report().model_copy(
        update={
            "complete": False,
            "issues": [RunIssue(code="PARSE_ERROR", message="invalid source", phase="analysis", fatal=True)],
        }
    )
    _install_core_stub(monkeypatch, events, incomplete_report)
    executor = _FakeRuntimeExecutor(events)

    result = execute_scan(
        ScanOptions(root),
        runtime_config=ProjectRuntimeConfig(enabled=True, airflow_version=AirflowProfile.AIRFLOW_3_3_0),
        runtime_executor=executor,
    )

    assert events == ["validate", "core", "execute"]
    assert result.report.complete is False
    assert executor.execution_args is not None


def test_execute_scan_marks_error_observation_fatal_and_incomplete(
    build_repository: Callable[[Path], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = build_repository(tmp_path / "repo")
    events: list[str] = []
    _install_core_stub(monkeypatch, events, _complete_report())
    observation = RuntimeObservation(
        policy_id="AIR-RUN-001",
        status=FindingStatus.ERROR,
        message="runtime probe failed",
    )
    executor = _FakeRuntimeExecutor(events, observations=[observation])

    result = execute_scan(
        ScanOptions(root),
        runtime_config=ProjectRuntimeConfig(enabled=True, airflow_version=AirflowProfile.AIRFLOW_3_3_0),
        runtime_executor=executor,
    )

    runtime_issues = [issue for issue in result.report.issues if issue.code == "RUNTIME_OBSERVATION_ERROR"]
    assert events == ["validate", "core", "execute"]
    assert result.report.complete is False
    assert len(runtime_issues) == 1
    assert runtime_issues[0].message == "runtime probe failed"
    assert runtime_issues[0].fatal is True


def test_execute_scan_converts_runtime_execution_error_to_fatal_issue(
    build_repository: Callable[[Path], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = build_repository(tmp_path / "repo")
    events: list[str] = []
    _install_core_stub(monkeypatch, events, _complete_report())
    executor = _FakeRuntimeExecutor(events, execution_error=RuntimeExecutionError("runtime container failed"))

    result = execute_scan(
        ScanOptions(root),
        runtime_config=ProjectRuntimeConfig(enabled=True, airflow_version=AirflowProfile.AIRFLOW_3_3_0),
        runtime_executor=executor,
    )

    runtime_issues = [issue for issue in result.report.issues if issue.code == "RUNTIME_EXECUTION_ERROR"]
    assert events == ["validate", "core", "execute"]
    assert result.report.complete is False
    assert len(runtime_issues) == 1
    assert runtime_issues[0].message == "runtime container failed"
    assert runtime_issues[0].fatal is True


def test_execute_scan_does_not_swallow_unrelated_runtime_executor_errors(
    build_repository: Callable[[Path], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = build_repository(tmp_path / "repo")
    events: list[str] = []
    _install_core_stub(monkeypatch, events, _complete_report())
    executor = _FakeRuntimeExecutor(events, execution_error=ValueError("adapter bug"))

    with pytest.raises(ValueError, match="adapter bug"):
        execute_scan(
            ScanOptions(root),
            runtime_config=ProjectRuntimeConfig(enabled=True, airflow_version=AirflowProfile.AIRFLOW_3_3_0),
            runtime_executor=executor,
        )

    assert events == ["validate", "core", "execute"]


def test_execute_scan_operational_suppression_preserves_local_provenance(
    build_repository: Callable[[Path], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finding = _finding_from_repository(build_repository, tmp_path / "repo")
    current = datetime.now(UTC)
    local = _suppression_for_finding(finding, current, reason="repository-local waiver")
    operational = _suppression_for_finding(finding, current, reason="platform waiver")
    operational_only = _suppression_for_finding(
        finding,
        current,
        reason="platform-only waiver",
        fingerprint="operational-only-fingerprint",
    )
    locally_suppressed = finding.model_copy(update={"suppressed": True, "suppression": local})
    operational_finding = finding.model_copy(
        update={"fingerprint": "operational-only-fingerprint", "suppressed": False, "suppression": None}
    )
    core_report = _complete_report().model_copy(update={"findings": [locally_suppressed, operational_finding]})
    events: list[str] = []
    _install_core_stub(monkeypatch, events, core_report)

    result = execute_scan(
        ScanOptions(tmp_path / "repo"),
        operational_suppressions=[operational, operational_only],
    )

    results_by_fingerprint = {item.fingerprint: item for item in result.report.findings}
    assert events == ["core"]
    assert results_by_fingerprint[finding.fingerprint].suppressed is True
    assert results_by_fingerprint[finding.fingerprint].suppression is local
    assert results_by_fingerprint["operational-only-fingerprint"].suppressed is True
    assert results_by_fingerprint["operational-only-fingerprint"].suppression is operational_only
    assert result.report.issues == []


def test_execute_scan_operational_suppression_recovers_waived_evaluation_error(
    build_repository: Callable[[Path], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finding = _finding_from_repository(build_repository, tmp_path / "repo")
    unresolved = finding.model_copy(update={"status": FindingStatus.ERROR, "suppressed": False, "suppression": None})
    evaluation_issue = RunIssue(
        code="EVALUATION_ERROR",
        message="finding could not be evaluated",
        phase="evaluation",
        fatal=True,
    )
    core_report = _complete_report().model_copy(
        update={"complete": False, "findings": [unresolved], "issues": [evaluation_issue]}
    )
    events: list[str] = []
    _install_core_stub(monkeypatch, events, core_report)
    operational = _suppression_for_finding(finding, datetime.now(UTC), reason="approved operational waiver")

    result = execute_scan(ScanOptions(tmp_path / "repo"), operational_suppressions=[operational])

    assert events == ["core"]
    assert result.report.findings[0].suppressed is True
    assert result.report.findings[0].suppression is operational
    assert result.report.complete is True
    assert result.report.issues == []


def test_execute_scan_operational_waiver_keeps_unrelated_fatal_issues(
    build_repository: Callable[[Path], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finding = _finding_from_repository(build_repository, tmp_path / "repo")
    unresolved = finding.model_copy(update={"status": FindingStatus.ERROR, "suppressed": False, "suppression": None})
    evaluation_issue = RunIssue(
        code="EVALUATION_ERROR",
        message="finding could not be evaluated",
        phase="evaluation",
        fatal=True,
    )
    parse_issue = RunIssue(code="PARSE_ERROR", message="source did not parse", phase="analysis", fatal=True)
    core_report = _complete_report().model_copy(
        update={"complete": False, "findings": [unresolved], "issues": [evaluation_issue, parse_issue]}
    )
    events: list[str] = []
    _install_core_stub(monkeypatch, events, core_report)
    operational = _suppression_for_finding(finding, datetime.now(UTC), reason="approved operational waiver")

    result = execute_scan(ScanOptions(tmp_path / "repo"), operational_suppressions=[operational])

    assert events == ["core"]
    assert result.report.findings[0].suppressed is True
    assert result.report.complete is False
    assert [(issue.code, issue.fatal) for issue in result.report.issues] == [("PARSE_ERROR", True)]


def test_execute_scan_without_operational_suppressions_preserves_core_report_state(
    build_repository: Callable[[Path], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finding = _finding_from_repository(build_repository, tmp_path / "repo")
    local = _suppression_for_finding(finding, datetime.now(UTC), reason="repository-local waiver")
    locally_suppressed = finding.model_copy(update={"suppressed": True, "suppression": local})
    parse_issue = RunIssue(code="PARSE_ERROR", message="source did not parse", phase="analysis", fatal=True)
    core_report = _complete_report().model_copy(
        update={"complete": False, "findings": [locally_suppressed], "issues": [parse_issue]}
    )
    events: list[str] = []
    _install_core_stub(monkeypatch, events, core_report)

    result = execute_scan(ScanOptions(tmp_path / "repo"))

    assert events == ["core"]
    assert result.report.complete is False
    assert result.report.findings[0].suppressed is True
    assert result.report.findings[0].suppression is local
    assert result.report.issues == [parse_issue]
