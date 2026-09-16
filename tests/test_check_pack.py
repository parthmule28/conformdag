"""Tests for the expanded check vocabulary and TaskFlow analysis."""

from collections.abc import Callable
from pathlib import Path

from conformdag.analysis import SourceFile, SourceModel, analyze_source
from conformdag.evaluator import CHECK_EVALUATORS, EvaluationContext
from conformdag.models import (
    AirflowProfile,
    CatchupPolicyConfig,
    DynamicDagFactoryConfig,
    EnforcementConfig,
    EnforcementType,
    FindingStatus,
    LifecycleStatus,
    ModuleScopeVariablesConfig,
    Ownership,
    Policy,
    PolicyConfiguration,
    PolicySource,
    RemediationAction,
    SensitiveLoggingConfig,
    Severity,
    StartDateFreshnessConfig,
)
from conformdag.policy import load_policy_pack
from conformdag.scan import scan_repository

TASKFLOW_DAG = '''\
"""Modern TaskFlow DAG."""

from datetime import datetime

from airflow.sdk import DAG, Variable
from airflow.sdk import task

API_TOKEN = Variable.get("api_token")

with DAG(
    dag_id="modern",
    start_date=datetime(2023, 1, 1),
    catchup=True,
) as dag:

    @task(retries=99)
    def extract():
        return API_TOKEN

    @task
    def load(x):
        return x

    extract() >> load
'''

SECRETS_DAG = '''\
"""DAG with a hardcoded secret."""

from airflow.providers.standard.operators.bash import BashOperator

from airflow.sdk import DAG

DATABASE_PASSWORD = "hunter2"

with DAG(dag_id="secrets", schedule=None) as dag:
    task = BashOperator(task_id="t", bash_command="echo hi")
'''

DYNAMIC_DAG = '''\
"""Module-scope DAG factory loop."""

from airflow.sdk import DAG

for index in range(50):
    DAG(dag_id=f"generated_{index}", schedule=None)
'''


def _source_model(source: str) -> SourceModel:
    source_file = SourceFile(
        path=Path("dags/x.py"),
        relative_path="dags/x.py",
        content=source,
        content_hash="c" * 64,
    )
    model, issue = analyze_source(source_file)
    assert model is not None, "source must parse"
    assert issue is None
    return model


def _evaluate(config: PolicyConfiguration, check: str, source: str):
    policy = Policy(
        id="AIR-TST-001",
        title="test",
        version="1.0.0",
        status=LifecycleStatus.ACTIVE,
        severity=Severity.HIGH,
        airflow_profiles=[AirflowProfile.AIRFLOW_3_3_0],
        ownership=Ownership(owner="platform"),
        source=PolicySource(
            document=Path("standards/dags.md"),
            section="Standards",
            content_hash="d" * 64,
        ),
        invariant="test invariant",
        enforcement=EnforcementConfig(type=EnforcementType.DETERMINISTIC, deterministic_checks=[check]),
        configuration=config,
    )
    model = _source_model(source)
    context = EvaluationContext(policy, [model])
    findings = CHECK_EVALUATORS[check].evaluate(context)
    return findings, model


def test_taskflow_tasks_are_visible_to_the_analyzer() -> None:
    model = _source_model(TASKFLOW_DAG)

    taskflow_tasks = [task for task in model.tasks if task.taskflow]
    assert len(taskflow_tasks) == 2
    extract = next(task for task in taskflow_tasks if task.task_id == "extract")
    assert extract.values.get("retries") == 99
    assert all(task.dag_name is None for task in taskflow_tasks)


def test_taskflow_retry_bounds_are_enforced(build_repository: Callable[[Path], Path], tmp_path: Path) -> None:
    root = build_repository(tmp_path)
    source = root / "dags" / "taskflow.py"
    source.write_text(TASKFLOW_DAG, encoding="utf-8")

    report = scan_repository(root, root / "policies/pack.yaml")

    retry_findings = [
        finding
        for finding in report.findings
        if finding.policy_id == "AIR-DET-004" and finding.status == FindingStatus.FAIL
    ]
    assert retry_findings, "retry-bounds must catch TaskFlow retries=99"
    fix = retry_findings[0].fix
    assert fix is not None and fix.action == RemediationAction.SET_KWARG


def test_start_date_freshness_catches_stale_and_naive_dates() -> None:
    findings, _ = _evaluate(StartDateFreshnessConfig(), "start-date-freshness", TASKFLOW_DAG)

    assert len(findings) == 1
    explanation = findings[0].explanation or ""
    assert "2023-01-01" in explanation
    assert findings[0].fix is not None
    assert findings[0].fix.action == RemediationAction.MANUAL


def test_catchup_policy_catches_enabled_catchup() -> None:
    findings, _ = _evaluate(CatchupPolicyConfig(), "catchup-policy", TASKFLOW_DAG)

    assert len(findings) == 1
    fix = findings[0].fix
    assert fix is not None
    assert fix.action == RemediationAction.SET_KWARG
    assert fix.kwarg == "catchup"
    assert fix.value == "False"


def test_module_scope_variables_catches_variable_get() -> None:
    findings, _ = _evaluate(
        ModuleScopeVariablesConfig(patterns=["Variable.get"]),
        "module-scope-variables",
        'from airflow.sdk import Variable\nTOKEN = Variable.get("t")\n',
    )

    assert len(findings) == 1
    assert findings[0].fix is not None
    assert findings[0].fix.action == RemediationAction.MOVE_STATEMENT


def test_sensitive_logging_catches_hardcoded_secrets() -> None:
    findings, _ = _evaluate(
        SensitiveLoggingConfig(),
        "sensitive-logging",
        'PASSWORD = "hunter2"\nGREETING = "hello"\n',
    )

    assert len(findings) == 1
    assert "PASSWORD" in (findings[0].explanation or "")


def test_dynamic_dag_factory_catches_loop_generated_dags() -> None:
    findings, _ = _evaluate(DynamicDagFactoryConfig(), "dynamic-dag-factory", DYNAMIC_DAG)

    assert len(findings) == 1
    assert findings[0].fix is not None
    assert findings[0].fix.action == RemediationAction.MANUAL


def test_allow_catchup_config_suppresses_findings() -> None:
    findings, _ = _evaluate(CatchupPolicyConfig(allow_catchup=True), "catchup-policy", TASKFLOW_DAG)

    assert findings == []


def test_new_checks_flow_through_the_full_scan(build_repository: Callable[[Path], Path], tmp_path: Path) -> None:
    root = build_repository(tmp_path)
    source = root / "dags" / "taskflow.py"
    source.write_text(TASKFLOW_DAG, encoding="utf-8")

    report = scan_repository(root, root / "policies/pack.yaml")

    flagged_policies = {
        finding.policy_id
        for finding in report.findings
        if finding.status == FindingStatus.FAIL and not finding.suppressed
    }
    assert "AIR-DET-001" in flagged_policies
    assert report.complete


def test_org_pack_includes_the_new_check_kinds() -> None:
    pack = load_policy_pack(Path("policies/pack.yaml"), Path("."))
    kinds = {policy.configuration.kind for policy in pack.policies}
    required_kinds = {
        "start-date-freshness",
        "catchup-policy",
        "module-scope-variables",
        "dynamic-dag-factory",
    }

    assert required_kinds <= kinds
    for policy in pack.policies:
        if policy.configuration.kind in required_kinds:
            assert policy.status.value == "ACTIVE"
