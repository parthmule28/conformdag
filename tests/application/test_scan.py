"""Tests for the reusable application scan workflow."""

from collections.abc import Callable, Sequence
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conformdag.analysis import ParseCache
from conformdag.application import BaselineInput, ScanExecutionResult, ScanInputError, ScanOptions, execute_scan
from conformdag.models import (
    AirflowProfile,
    Confidence,
    RunMetadata,
    ScanReport,
    SemanticRequest,
    SemanticResponse,
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
