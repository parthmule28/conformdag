"""Fix engine tests: payloads, codemods, the verification loop, and the CLI."""

import ast
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

from conformdag.analysis import SourceFile, SourceModel, analyze_source
from conformdag.cli import app
from conformdag.evaluator import CHECK_EVALUATORS, EvaluationContext
from conformdag.fixing import run_fix
from conformdag.fixing.codemods import (
    AUTOFIX_KINDS,
    MANUAL_KINDS,
    PROPOSED_ONLY_KINDS,
    fix_move_statement,
    fix_owner,
    fix_retry_bounds,
    fix_tags,
    generate_spans,
    timedelta_import_span,
)
from conformdag.fixing.engine import ResidualFailure
from conformdag.fixing.specs import EditSpan, apply_spans
from conformdag.models import (
    AirflowProfile,
    EnforcementConfig,
    EnforcementType,
    ExecutionTimeoutConfig,
    Finding,
    FindingLocation,
    FindingStatus,
    LifecycleStatus,
    Ownership,
    Policy,
    PolicyConfiguration,
    PolicySource,
    RemediationAction,
    RemediationPayload,
    RemediationTarget,
    RequiredOwnerConfig,
    RequiredTagsConfig,
    RetryBoundsConfig,
    ScanReport,
    Severity,
)
from conformdag.scan import scan_repository
from conftest import VIOLATIONS_PY


def test_fixability_matrix_is_explicit_for_every_known_kind() -> None:
    assert (
        frozenset({"required-owner", "required-tags", "execution-timeout", "retry-bounds", "catchup-policy"})
        == AUTOFIX_KINDS
    )
    assert frozenset({"top-level-io"}) == PROPOSED_ONLY_KINDS
    assert (
        frozenset(
            {
                "forbidden-operators",
                "idempotence",
                "orchestration-boundary",
                "sensitive-logging",
                "approved-abstractions",
                "ruff-air",
                "start-date-freshness",
                "module-scope-variables",
                "dynamic-dag-factory",
            }
        )
        == MANUAL_KINDS
    )
    assert not AUTOFIX_KINDS & PROPOSED_ONLY_KINDS
    assert not AUTOFIX_KINDS & MANUAL_KINDS


def test_catchup_policy_codemod_replaces_catchup_kwarg() -> None:
    source = "from airflow import DAG\ndag = DAG(dag_id='x', catchup=True)\n"
    payload = RemediationPayload(
        fix_kind="catchup-policy",
        action=RemediationAction.SET_KWARG,
        kwarg="catchup",
        target=RemediationTarget(line=2, column=0, enclosing="dag", node="dag-call"),
        value="False",
    )

    generated = generate_spans(source, payload)

    assert generated is not None
    spans, needs_import = generated
    assert len(spans) == 1
    assert needs_import is False
    updated = apply_spans(source, spans)
    assert "catchup=False" in updated
    assert "catchup=True" not in updated


def test_findings_carry_remediation_payloads(build_repository: Callable[[Path], Path], tmp_path: Path) -> None:
    root = build_repository(tmp_path)

    report = scan_repository(root, root / "policies/pack.yaml")

    payloads = {
        finding.policy_id: finding.fix
        for finding in report.findings
        if finding.fix is not None and finding.status.value == "FAIL"
    }
    owner = payloads["AIR-DET-001"]
    assert owner.action is RemediationAction.ADD_OWNER
    assert owner.kwarg == "owner"
    assert owner.value == "analytics"
    assert owner.target is not None and owner.target.node == "dag-call"
    tags = payloads["AIR-DET-002"]
    assert tags.action is RemediationAction.ADD_TAGS
    assert tags.value == '["domain:analytics", "owner"]'
    timeout = payloads["AIR-DET-003"]
    assert timeout.action is RemediationAction.SET_KWARG
    assert timeout.kwarg == "execution_timeout"
    assert timeout.value == "86400"
    retry = payloads["AIR-DET-004"]
    assert retry.action is RemediationAction.SET_KWARG
    assert retry.kwarg == "retries"
    assert retry.value == "5"


def test_dry_run_writes_nothing_and_prints_verified_diff(
    build_repository: Callable[[Path], Path], tmp_path: Path
) -> None:
    root = build_repository(tmp_path)
    before = (root / "dags/violations.py").read_text(encoding="utf-8")

    outcome = run_fix(root, root / "policies/pack.yaml")

    assert (root / "dags/violations.py").read_text(encoding="utf-8") == before
    assert len(outcome.patches) == 1
    patch = outcome.patches[0]
    assert patch.path == "dags/violations.py"
    assert "-        retries=9," in patch.diff
    assert "+        retries=5," in patch.diff
    assert "owner='analytics'" in patch.updated
    assert "timedelta(seconds=86400)" in patch.updated
    assert "tags=['domain:analytics', 'owner']" in patch.updated
    assert outcome.clean
    assert outcome.verification_report is not None
    residual_policies = [
        finding.policy_id for finding in outcome.verification_report.findings if finding.status.value == "FAIL"
    ]
    assert residual_policies == []


def test_apply_writes_verified_patches_and_rescan_is_clean(
    build_repository: Callable[[Path], Path], tmp_path: Path
) -> None:
    root = build_repository(tmp_path)

    outcome = run_fix(root, root / "policies/pack.yaml", apply=True)

    assert outcome.applied_files == ["dags/violations.py"]
    updated = (root / "dags/violations.py").read_text(encoding="utf-8")
    assert "owner='analytics'" in updated
    assert "retries=5" in updated
    report = scan_repository(root, root / "policies/pack.yaml")
    failing = {finding.policy_id for finding in report.findings if finding.status.value == "FAIL"}
    assert not failing & {"AIR-DET-001", "AIR-DET-003", "AIR-DET-004"}


def test_codemods_are_byte_identical_across_runs(build_repository: Callable[[Path], Path], tmp_path: Path) -> None:
    first = build_repository(tmp_path / "first")
    second = build_repository(tmp_path / "second")

    first_outcome = run_fix(first, first / "policies/pack.yaml")
    second_outcome = run_fix(second, second / "policies/pack.yaml")
    assert [patch.diff for patch in first_outcome.patches] == [patch.diff for patch in second_outcome.patches]


def test_forbidden_operators_are_reported_not_fixable(build_repository: Callable[[Path], Path], tmp_path: Path) -> None:
    root = build_repository(tmp_path)
    (root / "dags/forbidden.py").write_text(
        "from airflow.operators.python import PythonOperator\n"
        "\n"
        "with DAG(dag_id='forbidden', schedule=None) as dag:\n"
        "    task = PythonOperator(task_id='task', python_callable=lambda: None)\n",
        encoding="utf-8",
    )

    outcome = run_fix(root, root / "policies/pack.yaml")

    manual = [item for item in outcome.not_fixable if item.policy_id == "AIR-DET-006"]
    assert len(manual) == 1
    assert manual[0].fix_kind == "forbidden-operators"
    assert manual[0].reason == "not auto-fixable; apply the replacement guidance"


def test_proposed_move_is_never_applied(build_repository: Callable[[Path], Path], tmp_path: Path) -> None:
    root = build_repository(tmp_path)
    (root / "dags/module_io.py").write_text(
        "import boto3\n"
        "from airflow.sdk import DAG\n"
        "from airflow.providers.standard.operators.python import PythonOperator\n"
        "\n"
        "CLIENT = boto3.client('s3')\n"
        "\n"
        "\n"
        "def _fetch():\n"
        "    return CLIENT.get_object(Bucket='x', Key='y')\n"
        "\n"
        "\n"
        "with DAG(dag_id='module_io', schedule=None) as dag:\n"
        "    fetch = PythonOperator(task_id='fetch', python_callable=_fetch)\n",
        encoding="utf-8",
    )

    outcome = run_fix(root, root / "policies/pack.yaml", apply=True)

    assert [move.path for move in outcome.proposed_moves] == ["dags/module_io.py"]
    assert outcome.proposed_moves[0].policy_id == "AIR-DET-005"
    updated = (root / "dags/module_io.py").read_text(encoding="utf-8")
    assert "CLIENT = boto3.client('s3')" in updated
    ast.parse(updated)


def test_proposed_move_requires_following_task_function(
    build_repository: Callable[[Path], Path], tmp_path: Path
) -> None:
    root = build_repository(tmp_path)
    (root / "dags/no_helper.py").write_text(
        "import boto3\n"
        "from airflow.sdk import DAG\n"
        "\n"
        "CLIENT = boto3.client('s3')\n"
        "\n"
        "with DAG(dag_id='no_helper', schedule=None) as dag:\n"
        "    pass\n",
        encoding="utf-8",
    )

    outcome = run_fix(root, root / "policies/pack.yaml")

    assert outcome.proposed_moves == []
    assert any(item.policy_id == "AIR-DET-005" and item.path == "dags/no_helper.py" for item in outcome.not_fixable)


def test_timedelta_import_is_inserted_when_missing(build_repository: Callable[[Path], Path], tmp_path: Path) -> None:
    root = build_repository(tmp_path)
    source = root / "dags/violations.py"
    source.write_text(VIOLATIONS_PY, encoding="utf-8")

    outcome = run_fix(root, root / "policies/pack.yaml", apply=True)

    updated = source.read_text(encoding="utf-8")
    assert "from datetime import timedelta\n" in updated
    assert "timedelta(seconds=86400)" in updated
    ast.parse(updated)
    assert outcome.clean


def test_report_schema_stays_backward_compatible(build_repository: Callable[[Path], Path], tmp_path: Path) -> None:
    root = build_repository(tmp_path)
    report = scan_repository(root, root / "policies/pack.yaml")
    legacy_payload = report.model_dump(mode="json")
    for finding in legacy_payload["findings"]:
        finding.pop("fix", None)
    legacy_payload["report_version"] = "1"

    legacy = ScanReport.model_validate(legacy_payload)

    assert legacy.report_version == "1"
    assert all(finding.fix is None for finding in legacy.findings)
    assert ScanReport.model_validate(report.model_dump(mode="json")).report_version == "2"


def test_cli_fix_dry_run_keeps_sources_intact(build_repository: Callable[[Path], Path], tmp_path: Path) -> None:
    root = build_repository(tmp_path)

    result = CliRunner().invoke(
        app,
        ["fix", "--path", str(root), "--policy-pack", str(root / "policies/pack.yaml")],
    )

    assert result.exit_code == 0
    assert "fix dry-run: 1 verified patch(es)" in result.stderr
    assert "--- a/dags/violations.py" in result.stdout
    assert "owner='analytics'" in result.stdout


def test_cli_fix_apply_writes_and_exits_zero_when_clean(
    build_repository: Callable[[Path], Path], tmp_path: Path
) -> None:
    root = build_repository(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "fix",
            "--path",
            str(root),
            "--policy-pack",
            str(root / "policies/pack.yaml"),
            "--apply",
        ],
    )

    assert result.exit_code == 0
    assert "applied: dags/violations.py" in result.stderr
    assert "owner='analytics'" in (root / "dags/violations.py").read_text(encoding="utf-8")


def _policy(config: PolicyConfiguration, check: str, policy_id: str = "AIR-TST-001") -> Policy:
    return Policy(
        id=policy_id,
        title="Test policy",
        version="1.0.0",
        status=LifecycleStatus.ACTIVE,
        severity=Severity.HIGH,
        airflow_profiles=[AirflowProfile.AIRFLOW_3_3_0],
        ownership=Ownership(owner="platform"),
        source=PolicySource(
            document=Path("standards/dags.md"),
            section="Standards",
            content_hash="a" * 64,
        ),
        invariant="Test invariant.",
        enforcement=EnforcementConfig(type=EnforcementType.DETERMINISTIC, deterministic_checks=[check]),
        configuration=config,
    )


def _model(source: str) -> SourceModel:
    source_file = SourceFile(
        path=Path("dags/unit.py"),
        relative_path="dags/unit.py",
        content=source,
        content_hash="0" * 64,
    )
    model, issue = analyze_source(source_file)
    assert issue is None
    return cast(SourceModel, model)


def _single_finding(config: PolicyConfiguration, check: str, source: str) -> RemediationPayload | None:
    policy = _policy(config, check)
    context = EvaluationContext(policy, [_model(source)])
    findings = CHECK_EVALUATORS[check].evaluate(context)
    failing = [finding for finding in findings if finding.status.value == "FAIL"]
    assert failing, "expected a FAIL finding"
    return failing[0].fix


OWNER_SOURCE = "from airflow import DAG\ndag = DAG(dag_id='x')\n"
TAGS_SOURCE = "from airflow import DAG\ndag = DAG(dag_id='x', tags=['a'])\n"
TIMEOUT_SOURCE = (
    "from airflow import DAG\n"
    "from airflow.providers.standard.operators.empty import EmptyOperator\n"
    "with DAG(dag_id='x') as dag:\n"
    "    task = EmptyOperator(task_id='t', execution_timeout=60)\n"
)


def test_owner_payload_is_manual_without_allowed_values() -> None:
    payload = _single_finding(RequiredOwnerConfig(), "effective-owner", OWNER_SOURCE)

    assert payload is not None and payload.action is RemediationAction.MANUAL
    assert payload.hint is not None and "no allowed values" in payload.hint


def test_owner_payload_is_manual_with_pattern_only() -> None:
    payload = _single_finding(RequiredOwnerConfig(allowed_pattern="team-[a-z]+"), "effective-owner", OWNER_SOURCE)

    assert payload is not None and payload.action is RemediationAction.MANUAL
    assert payload.hint is not None and "pattern" in payload.hint


def test_owner_payload_sets_existing_owner() -> None:
    source = "from airflow import DAG\ndag = DAG(dag_id='x', owner='unknown')\n"
    payload = _single_finding(RequiredOwnerConfig(allowed_values=["platform"]), "effective-owner", source)

    assert payload is not None and payload.action is RemediationAction.SET_KWARG
    assert payload.value == "platform"
    spans = fix_owner(source, payload)
    assert spans is not None


def test_tags_payload_is_manual_for_disallowed_values() -> None:
    payload = _single_finding(
        RequiredTagsConfig(required_keys=["domain"], allowed_values={"domain": ["data"]}),
        "tags",
        "from airflow import DAG\ndag = DAG(dag_id='x', tags=['domain:nope'])\n",
    )

    assert payload is not None and payload.action is RemediationAction.MANUAL


def test_timeout_payload_is_manual_without_bounds() -> None:
    source = (
        "from airflow import DAG\n"
        "from airflow.providers.standard.operators.empty import EmptyOperator\n"
        "with DAG(dag_id='x') as dag:\n"
        "    task = EmptyOperator(task_id='t')\n"
    )
    payload = _single_finding(ExecutionTimeoutConfig(), "effective-timeout", source)

    assert payload is not None and payload.action is RemediationAction.MANUAL


def test_timeout_payload_clamps_to_max() -> None:
    payload = _single_finding(
        ExecutionTimeoutConfig(min_seconds=1, max_seconds=30), "effective-timeout", TIMEOUT_SOURCE
    )

    assert payload is not None and payload.action is RemediationAction.SET_KWARG
    assert payload.value == "30"


def test_retry_payload_is_manual_for_non_numeric_retries() -> None:
    source = (
        "from airflow import DAG\n"
        "from airflow.providers.standard.operators.empty import EmptyOperator\n"
        "with DAG(dag_id='x') as dag:\n"
        "    task = EmptyOperator(task_id='t', retries='many')\n"
    )
    payload = _single_finding(RetryBoundsConfig(max_retries=5), "retry-bounds", source)

    assert payload is not None and payload.action is RemediationAction.MANUAL


def test_retry_payload_clamps_delay_only() -> None:
    source = (
        "from datetime import timedelta\n"
        "from airflow import DAG\n"
        "from airflow.providers.standard.operators.empty import EmptyOperator\n"
        "with DAG(dag_id='x') as dag:\n"
        "    task = EmptyOperator(task_id='t', retries=2, retry_delay=timedelta(seconds=7200))\n"
    )
    payload = _single_finding(RetryBoundsConfig(max_retries=5, max_delay_seconds=3600), "retry-bounds", source)

    assert payload is not None
    assert payload.action is RemediationAction.SET_KWARG
    assert payload.kwarg == "retry_delay"
    assert payload.value == "3600"
    spans = fix_retry_bounds(source, payload)
    assert spans is not None


def test_retry_payload_adds_missing_retries_when_zero_forbidden() -> None:
    source = (
        "from airflow import DAG\n"
        "from airflow.providers.standard.operators.empty import EmptyOperator\n"
        "with DAG(dag_id='x') as dag:\n"
        "    task = EmptyOperator(task_id='t')\n"
    )
    payload = _single_finding(RetryBoundsConfig(max_retries=5, allow_zero_retries=False), "retry-bounds", source)

    assert payload is not None
    assert payload.action is RemediationAction.ADD_KWARG
    assert payload.kwarg == "retries"
    assert payload.value == "1"


def test_owner_codemod_returns_none_without_dag_call() -> None:
    payload = RemediationPayload(
        fix_kind="required-owner",
        action=RemediationAction.ADD_OWNER,
        kwarg="owner",
        value="platform",
        target=None,
    )

    assert fix_owner("x = 1\n", payload) is None
    assert fix_owner("x = 1\n", payload.model_copy(update={"value": None})) is None


def test_owner_codemod_uses_repr_for_generated_literals() -> None:
    payload = RemediationPayload(
        fix_kind="required-owner",
        action=RemediationAction.ADD_OWNER,
        kwarg="owner",
        value='bad"owner',
        target=RemediationTarget(line=2, column=0, enclosing="dag", node="dag-call"),
    )
    source = "from airflow import DAG\ndag = DAG(dag_id='x')\n"

    spans = fix_owner(source, payload)

    assert spans is not None
    updated = apply_spans(source, spans)
    assert "owner='bad\"owner'" in updated
    ast.parse(updated)


def test_tags_codemod_extends_existing_list_and_rejects_non_list() -> None:
    source = "from airflow import DAG\ndag = DAG(dag_id='x', tags=['a'])\n"
    payload = RemediationPayload(
        fix_kind="required-tags",
        action=RemediationAction.ADD_TAGS,
        kwarg="tags",
        value='["b", "c"]',
    )

    spans = fix_tags(source, payload)
    assert spans is not None
    non_list = fix_tags("from airflow import DAG\ndag = DAG(dag_id='x', tags=TAGS)\n", payload)
    assert non_list is None
    bad_value = fix_tags(source, payload.model_copy(update={"value": "not-json"}))
    assert bad_value is None


def test_tags_codemod_fills_empty_list() -> None:
    source = "from airflow import DAG\ndag = DAG(dag_id='x', tags=[])\n"
    payload = RemediationPayload(
        fix_kind="required-tags", action=RemediationAction.ADD_TAGS, kwarg="tags", value='["b"]'
    )

    spans = fix_tags(source, payload)

    assert spans is not None and len(spans) == 1


def test_timedelta_import_span_positions() -> None:
    with_import = "from datetime import timedelta\nx = 1\n"
    assert timedelta_import_span(with_import).start_line == 2
    docstring_only = '"""Doc."""\nx = 1\n'
    assert timedelta_import_span(docstring_only).start_line == 2
    shebang_only = "#!/usr/bin/env python\nx = 1\n"
    assert timedelta_import_span(shebang_only).start_line == 2
    plain = "x = 1\n"
    assert timedelta_import_span(plain).start_line == 1


def test_move_statement_handles_last_line_and_invalid_targets() -> None:
    source = "import boto3\n\nCLIENT = boto3.client('s3')\n\n\ndef _fetch():\n    return 1\n"
    payload = RemediationPayload(
        fix_kind="top-level-io",
        action=RemediationAction.MOVE_STATEMENT,
        target=None,
    )

    assert fix_move_statement(source, payload) is None
    positioned = RemediationPayload(
        fix_kind="top-level-io",
        action=RemediationAction.MOVE_STATEMENT,
        target=RemediationTarget(line=3, column=0, enclosing="boto3.client", node="statement"),
    )
    spans = fix_move_statement(source, positioned)
    assert spans is not None
    last_line = "import boto3\nCLIENT = boto3.client('s3')"
    assert fix_move_statement(last_line, positioned) is None


def test_generate_spans_returns_none_for_unknown_kind_and_failed_codemod() -> None:
    payload = RemediationPayload(fix_kind="no-such-kind", action=RemediationAction.ADD_KWARG, value="1")

    assert generate_spans("x = 1\n", payload) is None
    no_value = RemediationPayload(fix_kind="required-owner", action=RemediationAction.ADD_OWNER, kwarg="owner")
    assert generate_spans(OWNER_SOURCE, no_value) is None


def test_run_fix_returns_empty_outcome_for_clean_repository(
    build_repository: Callable[[Path], Path], tmp_path: Path
) -> None:
    root = build_repository(tmp_path)
    (root / "dags/violations.py").unlink()
    (root / "dags/clean.py").write_text(
        "from datetime import timedelta\n"
        "from airflow import DAG\n"
        "from airflow.providers.standard.operators.empty import EmptyOperator\n"
        "dag = DAG(dag_id='clean', owner='platform', tags=['domain:data', 'owner'])\n"
        "task = EmptyOperator(\n"
        "    task_id='t', retries=2,\n"
        "    execution_timeout=timedelta(seconds=300), retry_delay=timedelta(seconds=60)\n"
        ")\n",
        encoding="utf-8",
    )

    outcome = run_fix(root, root / "policies/pack.yaml")

    assert outcome.patches == []
    assert outcome.residuals == []
    assert outcome.verification_report is None
    assert outcome.clean


def test_generation_failure_becomes_residual(build_repository: Callable[[Path], Path], tmp_path: Path) -> None:
    root = build_repository(tmp_path)
    (root / "dags/var_tags.py").write_text(
        "from airflow import DAG\nTAGS = ['a']\ndag = DAG(dag_id='var', tags=TAGS)\n",
        encoding="utf-8",
    )

    outcome = run_fix(root, root / "policies/pack.yaml")

    residual = next((item for item in outcome.residuals if item.path == "dags/var_tags.py"), None)
    assert residual is not None
    assert residual.fix_kind == "required-tags"
    assert residual.iterations == 1


def test_apply_spans_rejects_overlapping_and_out_of_range_edits() -> None:
    source = "alpha\nbeta\n"
    overlapping = [
        EditSpan(1, 0, 1, 5, "ALPHA"),
        EditSpan(1, 3, 1, 5, "HA"),
    ]
    with pytest.raises(ValueError, match="overlapping edit spans"):
        apply_spans(source, overlapping)
    out_of_range = [EditSpan(9, 0, 9, 0, "x")]
    with pytest.raises(ValueError, match="outside source"):
        apply_spans(source, out_of_range)


def test_patch_candidates_converts_overlapping_spans_into_residuals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from conformdag.fixing import engine as engine_module

    original = {"dags/a.py": "line one\nline two\n"}
    finding = Finding(
        policy_id="AIR-TST-001",
        policy_version="1.0.0",
        status=FindingStatus.FAIL,
        severity=Severity.HIGH,
        enforcement=EnforcementType.DETERMINISTIC,
        location=FindingLocation(file=Path("dags/a.py"), start_line=1),
        fingerprint="f" * 64,
        fix=RemediationPayload(
            fix_kind="x",
            action=RemediationAction.SET_KWARG,
            target=RemediationTarget(line=1, column=0, node="dag-call"),
            value="False",
        ),
    )

    def generate_overlapping_spans(_source: str, _payload: RemediationPayload) -> tuple[list[EditSpan], bool]:
        return (
            [
                EditSpan(1, 0, 1, 8, "replaced"),
                EditSpan(1, 3, 1, 4, "overlap"),
            ],
            False,
        )

    monkeypatch.setattr(engine_module, "generate_spans", generate_overlapping_spans)

    def import_span(_source: str) -> EditSpan:
        return EditSpan(1, 0, 1, 0, "")

    monkeypatch.setattr(engine_module, "timedelta_import_span", import_span)

    patch_candidates = cast(
        "Callable[[dict[str, str], dict[str, str], dict[str, list[Finding]], int], tuple[dict[str, str], list[ResidualFailure]]]",
        engine_module.__dict__["_patch_candidates"],
    )
    candidates, residuals = patch_candidates(original, {}, {"dags/a.py": [finding]}, 1)

    assert candidates == {}
    assert len(residuals) == 1
    assert residuals[0].policy_id == "AIR-TST-001"
    assert "overlap" in residuals[0].reason


def test_patch_candidates_deduplicates_identical_spans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from conformdag.fixing import engine as engine_module

    original = {"dags/a.py": "from airflow import DAG\ndag = DAG()\n"}
    finding = Finding(
        policy_id="AIR-TST-001",
        policy_version="1.0.0",
        status=FindingStatus.FAIL,
        severity=Severity.HIGH,
        enforcement=EnforcementType.DETERMINISTIC,
        location=FindingLocation(file=Path("dags/a.py"), start_line=2),
        fingerprint="f" * 64,
        fix=RemediationPayload(
            fix_kind="x",
            action=RemediationAction.ADD_OWNER,
            target=RemediationTarget(line=2, column=0, enclosing="dag", node="dag-call"),
            value="platform",
        ),
    )
    span = EditSpan(2, 10, 2, 10, "owner='platform'")

    def generate_duplicate_spans(_source: str, _payload: RemediationPayload) -> tuple[list[EditSpan], bool]:
        return [span, span], False

    monkeypatch.setattr(engine_module, "generate_spans", generate_duplicate_spans)

    def import_span(_source: str) -> EditSpan:
        return EditSpan(1, 0, 1, 0, "")

    monkeypatch.setattr(engine_module, "timedelta_import_span", import_span)

    patch_candidates = cast(
        "Callable[[dict[str, str], dict[str, str], dict[str, list[Finding]], int], tuple[dict[str, str], list[ResidualFailure]]]",
        engine_module.__dict__["_patch_candidates"],
    )
    candidates, residuals = patch_candidates(original, {}, {"dags/a.py": [finding]}, 1)

    assert not residuals
    assert candidates["dags/a.py"].count("owner='platform'") == 1


def test_patch_candidates_converts_distinct_insertions_at_same_offset_into_residuals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from conformdag.fixing import engine as engine_module

    original = {"dags/a.py": "from airflow import DAG\ndag = DAG()\n"}
    finding = Finding(
        policy_id="AIR-TST-001",
        policy_version="1.0.0",
        status=FindingStatus.FAIL,
        severity=Severity.HIGH,
        enforcement=EnforcementType.DETERMINISTIC,
        location=FindingLocation(file=Path("dags/a.py"), start_line=2),
        fingerprint="f" * 64,
        fix=RemediationPayload(
            fix_kind="x",
            action=RemediationAction.ADD_OWNER,
            target=RemediationTarget(line=2, column=0, enclosing="dag", node="dag-call"),
            value="platform",
        ),
    )

    def generate_colliding_spans(_source: str, _payload: RemediationPayload) -> tuple[list[EditSpan], bool]:
        return [
            EditSpan(2, 10, 2, 10, ", owner='platform'"),
            EditSpan(2, 10, 2, 10, ", tags=['domain:data']"),
        ], False

    monkeypatch.setattr(engine_module, "generate_spans", generate_colliding_spans)

    def import_span(_source: str) -> EditSpan:
        return EditSpan(1, 0, 1, 0, "")

    monkeypatch.setattr(engine_module, "timedelta_import_span", import_span)

    patch_candidates = cast(
        "Callable[[dict[str, str], dict[str, str], dict[str, list[Finding]], int], tuple[dict[str, str], list[ResidualFailure]]]",
        engine_module.__dict__["_patch_candidates"],
    )
    candidates, residuals = patch_candidates(original, {}, {"dags/a.py": [finding]}, 1)

    assert candidates == {}
    assert len(residuals) == 1
    assert "conflicting edit spans" in residuals[0].reason


def test_patch_candidates_applies_findings_sequentially_with_distinct_anchors() -> None:
    from conformdag.fixing import engine as engine_module

    original = {"dags/a.py": "from airflow import DAG\ndag = DAG(dag_id='x')\n"}
    owner_finding = Finding(
        policy_id="AIR-TST-001",
        policy_version="1.0.0",
        status=FindingStatus.FAIL,
        severity=Severity.HIGH,
        enforcement=EnforcementType.DETERMINISTIC,
        location=FindingLocation(file=Path("dags/a.py"), start_line=2),
        fingerprint="f" * 64,
        fix=RemediationPayload(
            fix_kind="required-owner",
            action=RemediationAction.ADD_OWNER,
            kwarg="owner",
            target=RemediationTarget(line=2, column=0, enclosing="dag", node="dag-call"),
            value="platform",
        ),
    )
    tags_finding = Finding(
        policy_id="AIR-TST-002",
        policy_version="1.0.0",
        status=FindingStatus.FAIL,
        severity=Severity.HIGH,
        enforcement=EnforcementType.DETERMINISTIC,
        location=FindingLocation(file=Path("dags/a.py"), start_line=2),
        fingerprint="e" * 64,
        fix=RemediationPayload(
            fix_kind="required-tags",
            action=RemediationAction.ADD_TAGS,
            kwarg="tags",
            target=RemediationTarget(line=2, column=0, enclosing="dag", node="dag-call"),
            value='["domain:data"]',
        ),
    )

    patch_candidates = cast(
        "Callable[[dict[str, str], dict[str, str], dict[str, list[Finding]], int], tuple[dict[str, str], list[ResidualFailure]]]",
        engine_module.__dict__["_patch_candidates"],
    )
    candidates, residuals = patch_candidates(original, {}, {"dags/a.py": [owner_finding, tags_finding]}, 1)

    assert not residuals
    assert candidates == {
        "dags/a.py": "from airflow import DAG\ndag = DAG(dag_id='x', owner='platform', tags=['domain:data'])\n"
    }


def test_patch_candidates_converts_codemod_parse_failures_into_residuals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from conformdag.fixing import engine as engine_module

    original = {"dags/a.py": "from airflow import DAG\ndag = DAG()\n"}
    finding = Finding(
        policy_id="AIR-TST-001",
        policy_version="1.0.0",
        status=FindingStatus.FAIL,
        severity=Severity.HIGH,
        enforcement=EnforcementType.DETERMINISTIC,
        location=FindingLocation(file=Path("dags/a.py"), start_line=2),
        fingerprint="f" * 64,
        fix=RemediationPayload(
            fix_kind="x",
            action=RemediationAction.ADD_OWNER,
            target=RemediationTarget(line=2, column=0, enclosing="dag", node="dag-call"),
            value="platform",
        ),
    )

    def generate_parse_error(_source: str, _payload: RemediationPayload) -> tuple[list[EditSpan], bool]:
        raise SyntaxError("invalid syntax")

    monkeypatch.setattr(engine_module, "generate_spans", generate_parse_error)

    def import_span(_source: str) -> EditSpan:
        return EditSpan(1, 0, 1, 0, "")

    monkeypatch.setattr(engine_module, "timedelta_import_span", import_span)

    patch_candidates = cast(
        "Callable[[dict[str, str], dict[str, str], dict[str, list[Finding]], int], tuple[dict[str, str], list[ResidualFailure]]]",
        engine_module.__dict__["_patch_candidates"],
    )
    candidates, residuals = patch_candidates(original, {}, {"dags/a.py": [finding]}, 1)

    assert candidates == {}
    assert len(residuals) == 1
    assert "could not parse" in residuals[0].reason


def test_patch_candidates_converts_equal_coordinate_replacements_into_residuals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from conformdag.fixing import engine as engine_module

    original = {"dags/a.py": "line one\nline two\n"}
    finding = Finding(
        policy_id="AIR-TST-001",
        policy_version="1.0.0",
        status=FindingStatus.FAIL,
        severity=Severity.HIGH,
        enforcement=EnforcementType.DETERMINISTIC,
        location=FindingLocation(file=Path("dags/a.py"), start_line=1),
        fingerprint="f" * 64,
        fix=RemediationPayload(
            fix_kind="x",
            action=RemediationAction.SET_KWARG,
            target=RemediationTarget(line=1, column=0, node="dag-call"),
            value="False",
        ),
    )

    def generate_equal_range_spans(_source: str, _payload: RemediationPayload) -> tuple[list[EditSpan], bool]:
        return [
            EditSpan(1, 0, 1, 8, "replaced-a"),
            EditSpan(1, 0, 1, 8, "replaced-b"),
        ], False

    monkeypatch.setattr(engine_module, "generate_spans", generate_equal_range_spans)

    def import_span(_source: str) -> EditSpan:
        return EditSpan(1, 0, 1, 0, "")

    monkeypatch.setattr(engine_module, "timedelta_import_span", import_span)

    patch_candidates = cast(
        "Callable[[dict[str, str], dict[str, str], dict[str, list[Finding]], int], tuple[dict[str, str], list[ResidualFailure]]]",
        engine_module.__dict__["_patch_candidates"],
    )
    candidates, residuals = patch_candidates(original, {}, {"dags/a.py": [finding]}, 1)

    assert candidates == {}
    assert len(residuals) == 1
    assert "conflicting edit spans" in residuals[0].reason


def test_apply_spans_rejects_distinct_zero_width_insertions_at_same_offset() -> None:
    spans = [EditSpan(1, 3, 1, 3, ', owner="a"'), EditSpan(1, 3, 1, 3, ', owner="b"')]
    with pytest.raises(ValueError, match="conflicting edit spans"):
        apply_spans("DAG()\n", spans)


def test_apply_spans_rejects_distinct_replacements_sharing_a_range() -> None:
    spans = [EditSpan(1, 0, 1, 5, "ALPHA"), EditSpan(1, 0, 1, 5, "OMEGA")]
    with pytest.raises(ValueError, match="conflicting edit spans"):
        apply_spans("alpha\n", spans)


def test_apply_spans_deduplicates_identical_spans() -> None:
    span = EditSpan(1, 3, 1, 3, ", owner='a'")

    assert apply_spans("DAG()\n", [span, span]) == "DAG, owner='a'()\n"


def test_incomplete_verification_never_applies(
    build_repository: Callable[[Path], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from conformdag.fixing import engine as engine_module

    root = build_repository(tmp_path)
    before = (root / "dags/violations.py").read_text(encoding="utf-8")

    def generate_malformed(_source: str, _payload: RemediationPayload) -> tuple[list[EditSpan], bool]:
        return [EditSpan(2, 0, 3, 0, "def broken(:\n")], False

    monkeypatch.setattr(engine_module, "generate_spans", generate_malformed)

    outcome = run_fix(root, root / "policies/pack.yaml", apply=True)

    assert outcome.applied_files == []
    assert outcome.residuals
    assert outcome.verification_report is not None
    assert outcome.verification_report.complete is False
    fatal_messages = {issue.message for issue in outcome.verification_report.issues if issue.fatal}
    assert all(residual.reason in fatal_messages for residual in outcome.residuals)
    assert all(residual.iterations == 1 for residual in outcome.residuals)
    after = (root / "dags/violations.py").read_text(encoding="utf-8")
    assert after == before
    ast.parse(after)


def test_apply_verified_refuses_unparsable_content(tmp_path: Path) -> None:
    from conformdag.fixing import engine as engine_module

    apply_verified = cast(
        "Callable[[Path, dict[str, str]], list[str]]",
        engine_module.__dict__["_apply_verified"],
    )

    with pytest.raises(ValueError, match="unparsable"):
        apply_verified(tmp_path, {"dags/bad.py": "def broken(:\n"})

    assert list(tmp_path.rglob("*")) == []


def test_apply_quotes_generated_owner_literals_safely(
    build_repository: Callable[[Path], Path],
    tmp_path: Path,
) -> None:
    root = build_repository(tmp_path)
    pack_path = root / "policies/pack.yaml"
    pack_text = pack_path.read_text(encoding="utf-8")
    pack_path.write_text(
        pack_text.replace(
            "allowed_values: [platform, data-engineering, analytics]",
            "allowed_values: ['bad\"owner']",
            1,
        ),
        encoding="utf-8",
    )

    outcome = run_fix(root, pack_path, apply=True)

    assert outcome.applied_files == ["dags/violations.py"]
    updated = (root / "dags/violations.py").read_text(encoding="utf-8")
    assert "owner='bad\"owner'" in updated
    ast.parse(updated)


def test_cli_fix_apply_reports_residual_with_exit_one(build_repository: Callable[[Path], Path], tmp_path: Path) -> None:
    root = build_repository(tmp_path)
    (root / "dags/var_tags.py").write_text(
        "from airflow import DAG\nTAGS = ['a']\ndag = DAG(dag_id='var', tags=TAGS)\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "fix",
            "--path",
            str(root),
            "--policy-pack",
            str(root / "policies/pack.yaml"),
            "--apply",
        ],
    )

    assert result.exit_code == 1
    assert "residual: AIR-DET-002 dags/var_tags.py" in result.stderr
