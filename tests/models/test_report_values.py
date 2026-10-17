"""Report and configuration composition remain compatible across ownership moves."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, get_type_hints

import pytest

from conformdag.models import (
    ConformModel,
    ProjectConfig,
    ProjectRuntimeConfig,
    ProjectScanConfig,
    ProjectSemanticConfig,
    RunMetadata,
    RuntimeManifest,
    RuntimeObservation,
    ScanReport,
)


def _run() -> RunMetadata:
    return RunMetadata(
        tool_version="test", policy_pack_id="pack", policy_pack_version="1", timestamp=datetime(2026, 1, 1, tzinfo=UTC)
    )


@pytest.mark.parametrize("version", ["1", "2"])
def test_report_versions_keep_json_round_trip_and_field_order(version: Literal["1", "2"]) -> None:
    report = ScanReport(report_version=version, complete=True, result_fingerprint="unchanged", run=_run())
    assert list(ScanReport.model_fields) == [
        "report_version",
        "complete",
        "result_fingerprint",
        "files_scanned",
        "policies_evaluated",
        "policies_skipped",
        "findings",
        "runtime_observations",
        "issues",
        "gate_result",
        "run",
    ]
    payload = report.model_dump(mode="json")
    assert payload["report_version"] == version
    assert payload["run"]["timestamp"] == "2026-01-01T00:00:00Z"
    assert ScanReport.model_validate(payload) == report
    assert ScanReport.model_validate_json(report.model_dump_json()) == report


def test_report_and_run_collection_factories_are_independent() -> None:
    first = ScanReport(complete=True, result_fingerprint="unchanged", run=_run())
    second = ScanReport(complete=True, result_fingerprint="unchanged", run=_run())
    for name in (
        "files_scanned",
        "policies_evaluated",
        "policies_skipped",
        "findings",
        "runtime_observations",
        "issues",
    ):
        assert getattr(first, name) == []
        assert getattr(first, name) is not getattr(second, name)
    for name in ("input_hashes", "prompt_hashes", "semantic_runs", "resolved_configuration", "environment"):
        assert getattr(first.run, name) is not getattr(second.run, name)


@pytest.mark.parametrize(
    "model",
    [
        RunMetadata,
        ScanReport,
        RuntimeObservation,
        RuntimeManifest,
        ProjectScanConfig,
        ProjectSemanticConfig,
        ProjectRuntimeConfig,
        ProjectConfig,
    ],
)
def test_composed_annotations_resolve(model: type[ConformModel]) -> None:
    assert set(model.model_fields) <= get_type_hints(model).keys()
