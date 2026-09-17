# P1 — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every known backend bug, ship the four DX commands, add quality gates + baselines, and add the `ruff-air` check kind — all test-first.

**Architecture:** Quality gates are data in the policy pack (`quality_gates:`), evaluated by one pure function (`conformdag.gates.evaluate_pack_gates`) shared by the CLI, platform runner, and GitHub Action. The `ruff-air` evaluator composes Ruff as a subprocess rule source that maps violations into the same finding/suppression machinery. All bug fixes stay inside existing modules.

**Tech Stack:** Python 3.12, pydantic v2 (discriminated unions), typer, FastAPI, SQLAlchemy + Alembic, ruff (as a tool AND as a composed rule source), pytest.

**Spec:** `docs/superpowers/specs/2026-09-05-p1-foundation-design.md`

## Global Constraints

- `mise run check` (format-check → lint → typecheck → test → validate:packs) green before every commit; `mise run test:coverage` ≥90%.
- Pyright strict, 0 errors; no `# type: ignore` — only `# pyright: ignore[reportUnknownMemberType]` on ruamel.yaml `.load()`/`.dump()`.
- Ruff: line-length 120, E501 ignored; test files may use S101/S106.
- After any `models.py` change: run `mise run schema:update` and commit `schemas/*.json` (CI checks sync via `mise run schema --check`).
- Default test command: `mise exec -- uv run pytest -m "not runtime"`; single test: `mise exec -- uv run pytest tests/<file>.py::<test> -x --tb=short`.
- Platform tests use SQLite (`create_session_factory("sqlite:///...")`); schema changes go through Alembic migrations only (never `create_all`).
- Named default factories for dataclass/pydantic list defaults (e.g. `def _empty_quality_gates() -> list[QualityGate]: return []`); no bare `field(default_factory=list)`.
- Conventional commits (`feat:`, `fix:`, `chore:`, `docs:`); one commit per task with test + implementation together.
- `cast()` over `# type: ignore`; catch specific exceptions (`OSError`, `ValueError`), never bare `except Exception` (the runner's `PERSISTENT_FAILURES` pattern is the model).
- Single scan engine: `scan_repository()` in `src/conformdag/scan.py` is the only evaluation path — never create a second pipeline.
- Branch for this work: `feat/policy-management` (already checked out, ahead of origin by 1 docs commit).

---

## Task 1: Quality-gate models

**Files:**
- Modify: `src/conformdag/models.py` (insert gate models after `PolicyConfiguration`, ~line 226; extend `PolicyPack` at line 246; extend `ScanReport` at line 382)
- Test: `tests/test_models.py`
- Regenerate: `schemas/*.json` (`mise run schema:update`)

**Interfaces:**
- Produces: `GateRule` discriminated union (members `NoNewFindingsRule`, `MaxSeverityRule`, `MaxFindingsRule`, `AlwaysBlockRule`, `FailureRateRule`), `QualityGate`, `GateRuleResult`, `GateResult`, `PolicyPack.quality_gates: list[QualityGate]`, `ScanReport.gate_result: GateResult | None = None`. Later tasks import these from `conformdag.models`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_models.py`:

```python
def test_quality_gate_rules_discriminate_by_type() -> None:
    gate = QualityGate.model_validate(
        {
            "id": "default",
            "rules": [
                {"type": "no-new-findings"},
                {"type": "max-severity", "severity": "high"},
                {"type": "max-findings", "count": 20},
                {"type": "always-block", "policy_ids": ["AIR-DET-005"]},
                {"type": "failure-rate", "max_percent": 10.0},
            ],
        }
    )
    assert [rule.type for rule in gate.rules] == [
        "no-new-findings",
        "max-severity",
        "max-findings",
        "always-block",
        "failure-rate",
    ]
    assert isinstance(gate.rules[1], MaxSeverityRule)
    assert gate.rules[1].severity is Severity.HIGH


def test_unknown_gate_rule_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        QualityGate.model_validate({"id": "x", "rules": [{"type": "nonsense"}]})


def test_policy_pack_accepts_quality_gates() -> None:
    pack = PolicyPack.model_validate(
        {
            "schema_version": "1",
            "id": "x",
            "version": "1",
            "policies": [],
            "quality_gates": [{"id": "default", "rules": [{"type": "max-findings", "count": 5}]}],
        }
    )
    assert len(pack.quality_gates) == 1
```

Add imports at the top of the file: `QualityGate, MaxSeverityRule, PolicyPack` (from `conformdag.models`) and `ValidationError` (from `pydantic`). Extend the existing `conformdag.models` import block rather than adding a new one.

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_models.py -x --tb=short`
Expected: FAIL with `ImportError: cannot import name 'QualityGate'`.

- [ ] **Step 3: Add the gate models to `models.py`**

Insert after the `PolicyConfiguration = Annotated[...]` block (before `class Policy`):

```python
def _empty_quality_gates() -> list[QualityGate]:
    return []


class NoNewFindingsRule(ConformModel):
    """Rule: no failing findings that are absent from the baseline scan."""

    type: Literal["no-new-findings"] = "no-new-findings"


class MaxSeverityRule(ConformModel):
    """Rule: no failing findings at or above the given severity."""

    type: Literal["max-severity"] = "max-severity"
    severity: Severity


class MaxFindingsRule(ConformModel):
    """Rule: fewer than ``count`` total failing findings."""

    type: Literal["max-findings"] = "max-findings"
    count: NonNegativeInt


class AlwaysBlockRule(ConformModel):
    """Rule: the listed policy ids always block, even when otherwise gated out."""

    type: Literal["always-block"] = "always-block"
    policy_ids: list[str] = Field(min_length=1)


class FailureRateRule(ConformModel):
    """Rule: failing findings below ``max_percent`` percent of all findings."""

    type: Literal["failure-rate"] = "failure-rate"
    max_percent: float = Field(ge=0.0, le=100.0)


GateRule = Annotated[
    NoNewFindingsRule | MaxSeverityRule | MaxFindingsRule | AlwaysBlockRule | FailureRateRule,
    Field(discriminator="type"),
]


class QualityGate(ConformModel):
    """One org-defined pass/fail decision over a scan's findings."""

    id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    rules: list[GateRule] = Field(min_length=1)


class GateRuleResult(ConformModel):
    """The outcome of one rule during gate evaluation."""

    rule_type: str
    passed: bool
    detail: str
    matching_findings: NonNegativeInt = 0


class GateResult(ConformModel):
    """The outcome of one gate: every rule must pass for the gate to pass."""

    gate_id: str
    passed: bool
    rules: list[GateRuleResult]
```

Then modify `PolicyPack` (add one field after `policies`):

```python
    quality_gates: list[QualityGate] = Field(default_factory=_empty_quality_gates)
```

Then modify `ScanReport` (add one field after `issues`):

```python
    gate_result: GateResult | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_models.py -x --tb=short`
Expected: PASS.

- [ ] **Step 5: Regenerate schemas and commit**

```bash
mise run schema:update
mise run schema --check
git add src/conformdag/models.py tests/test_models.py schemas/
git commit -m "feat: quality-gate models (5 rule types, pack + report schema)"
```

---

## Task 2: Gate evaluator

**Files:**
- Create: `src/conformdag/gates.py`
- Modify: `src/conformdag/reporting.py` (`has_blocking_failures` delegates to `gates.blocking_findings`)
- Test: `tests/test_gates.py` (new)

**Interfaces:**
- Consumes: `QualityGate`, `GateRule*`, `GateResult`, `GateRuleResult`, `ScanReport`, `FindingStatus`, `Severity`, `PolicyPack` from `conformdag.models`.
- Produces: `blocking_findings(report) -> list[Finding]`, `evaluate_gate(gate, report, baseline_report) -> GateResult`, `evaluate_pack_gates(pack, report, baseline_report) -> GateResult | None`, `validate_quality_gates(pack) -> list[str]`, `SEVERITY_ORDER: dict[Severity, int]`. Tasks 3–5 import these.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gates.py`:

```python
"""Quality-gate evaluation: pure-function tests for every rule type."""

from datetime import UTC, datetime
from pathlib import Path

from conformdag.gates import blocking_findings, evaluate_gate, evaluate_pack_gates, validate_quality_gates
from conformdag.models import (
    EnforcementType,
    Finding,
    FindingLocation,
    FindingStatus,
    PolicyPack,
    QualityGate,
    RunMetadata,
    ScanReport,
    Severity,
)


def _finding(policy_id: str, status: FindingStatus, fingerprint: str, *, suppressed: bool = False) -> Finding:
    return Finding(
        policy_id=policy_id,
        policy_version="1.0.0",
        status=status,
        severity=Severity.HIGH,
        enforcement=EnforcementType.DETERMINISTIC,
        location=FindingLocation(file=Path("dags/a.py"), start_line=1),
        fingerprint=fingerprint,
        suppressed=suppressed,
    )


def _report(*findings: Finding) -> ScanReport:
    return ScanReport(
        complete=True,
        result_fingerprint="f" * 64,
        findings=list(findings),
        run=RunMetadata(
            tool_version="0",
            policy_pack_id="x",
            policy_pack_version="1",
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    )


def _pack(*gates: QualityGate) -> PolicyPack:
    return PolicyPack(schema_version="1", id="x", version="1", policies=[], quality_gates=list(gates))


def test_no_new_findings_rule_compares_fingerprints_against_baseline() -> None:
    gate = QualityGate.model_validate({"id": "g", "rules": [{"type": "no-new-findings"}]})
    baseline = _report(_finding("AIR-DET-001", FindingStatus.FAIL, "known"))
    current = _report(
        _finding("AIR-DET-001", FindingStatus.FAIL, "known"), _finding("AIR-DET-002", FindingStatus.FAIL, "brand-new")
    )
    result = evaluate_gate(gate, current, baseline)
    assert not result.passed
    rule = result.rules[0]
    assert rule.rule_type == "no-new-findings"
    assert rule.matching_findings == 1

    only_known = _report(_finding("AIR-DET-001", FindingStatus.FAIL, "known"))
    assert evaluate_gate(gate, only_known, baseline).passed


def test_max_severity_blocks_at_or_above_threshold() -> None:
    gate = QualityGate.model_validate({"id": "g", "rules": [{"type": "max-severity", "severity": "high"}]})
    critical = _finding("A", FindingStatus.FAIL, "f1").model_copy(update={"severity": Severity.CRITICAL})
    assert not evaluate_gate(gate, _report(critical), None).passed

    medium = _finding("A", FindingStatus.FAIL, "f1").model_copy(update={"severity": Severity.MEDIUM})
    assert evaluate_gate(gate, _report(medium), None).passed


def test_max_findings_fails_at_the_count() -> None:
    gate = QualityGate.model_validate({"id": "g", "rules": [{"type": "max-findings", "count": 2}]})
    two = _report(_finding("A", FindingStatus.FAIL, "f1"), _finding("B", FindingStatus.FAIL, "f2"))
    assert not evaluate_gate(gate, two, None).passed
    assert evaluate_gate(gate, _report(_finding("A", FindingStatus.FAIL, "f1")), None).passed


def test_always_block_lists_policy_ids() -> None:
    gate = QualityGate.model_validate({"id": "g", "rules": [{"type": "always-block", "policy_ids": ["AIR-DET-005"]}]})
    assert not evaluate_gate(gate, _report(_finding("AIR-DET-005", FindingStatus.FAIL, "f1")), None).passed
    assert evaluate_gate(gate, _report(_finding("AIR-DET-001", FindingStatus.FAIL, "f2")), None).passed


def test_failure_rate_uses_failing_over_total() -> None:
    gate = QualityGate.model_validate({"id": "g", "rules": [{"type": "failure-rate", "max_percent": 50.0}]})
    half = _report(
        _finding("A", FindingStatus.FAIL, "f1"),
        _finding("B", FindingStatus.PASS, "f2"),
    )
    assert not evaluate_gate(gate, half, None).passed

    clean = _report(_finding("B", FindingStatus.PASS, "f2"))
    assert evaluate_gate(gate, clean, None).passed
    assert evaluate_gate(gate, _report(), None).passed


def test_suppressed_findings_never_block() -> None:
    gate = QualityGate.model_validate({"id": "g", "rules": [{"type": "max-findings", "count": 0}]})
    assert evaluate_gate(gate, _report(_finding("A", FindingStatus.FAIL, "f1", suppressed=True)), None).passed


def test_all_gates_must_pass_and_first_failure_is_reported() -> None:
    pack = _pack(
        QualityGate.model_validate({"id": "ok", "rules": [{"type": "max-findings", "count": 0}]}),
        QualityGate.model_validate({"id": "strict", "rules": [{"type": "max-findings", "count": 1}]}),
    )
    result = evaluate_pack_gates(pack, _report(_finding("A", FindingStatus.FAIL, "f1")), None)
    assert result is not None
    assert result.gate_id == "ok"
    assert not result.passed


def test_pack_without_gates_evaluates_to_none() -> None:
    assert evaluate_pack_gates(_pack(), _report(), None) is None


def test_validate_quality_gates_rejects_duplicate_ids_and_unknown_policies() -> None:
    pack = _pack(
        QualityGate.model_validate({"id": "g", "rules": [{"type": "max-findings", "count": 1}]}),
        QualityGate.model_validate({"id": "g", "rules": [{"type": "max-findings", "count": 2}]}),
    )
    issues = validate_quality_gates(pack)
    assert any("unique" in issue for issue in issues)

    referencing = _pack(
        QualityGate.model_validate({"id": "g", "rules": [{"type": "always-block", "policy_ids": ["AIR-DET-999"]}]})
    )
    assert any("AIR-DET-999" in issue for issue in validate_quality_gates(referencing))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_gates.py -x --tb=short`
Expected: FAIL with `ModuleNotFoundError: No module named 'conformdag.gates'`.

- [ ] **Step 3: Implement `src/conformdag/gates.py`**

```python
"""Quality-gate evaluation: turn findings into org-defined pass/fail decisions."""

from __future__ import annotations

from conformdag.models import (
    AlwaysBlockRule,
    FailureRateRule,
    Finding,
    FindingStatus,
    GateResult,
    GateRuleResult,
    GateRule,
    MaxFindingsRule,
    MaxSeverityRule,
    NoNewFindingsRule,
    PolicyPack,
    QualityGate,
    ScanReport,
    Severity,
)

SEVERITY_ORDER: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


def blocking_findings(report: ScanReport) -> list[Finding]:
    """Return unsuppressed failing findings the legacy exit code blocks on."""
    return [
        finding
        for finding in report.findings
        if finding.status is FindingStatus.FAIL
        and not finding.suppressed
        and (finding.enforcement.value == "deterministic" or finding.blocking)
    ]


def _evaluate_rule(rule: GateRule, report: ScanReport, baseline_report: ScanReport | None) -> GateRuleResult:
    if isinstance(rule, NoNewFindingsRule):
        baseline_fingerprints = (
            {finding.fingerprint for finding in baseline_report.findings} if baseline_report is not None else set()
        )
        new = [finding for finding in blocking_findings(report) if finding.fingerprint not in baseline_fingerprints]
        return GateRuleResult(
            rule_type=rule.type,
            passed=not new,
            detail=f"{len(new)} new failing finding(s) since the baseline",
            matching_findings=len(new),
        )
    if isinstance(rule, MaxSeverityRule):
        threshold = SEVERITY_ORDER[rule.severity]
        over = [f for f in blocking_findings(report) if SEVERITY_ORDER[f.severity] >= threshold]
        return GateRuleResult(
            rule_type=rule.type,
            passed=not over,
            detail=f"{len(over)} failing finding(s) at or above severity {rule.severity.value}",
            matching_findings=len(over),
        )
    if isinstance(rule, MaxFindingsRule):
        failing = blocking_findings(report)
        return GateRuleResult(
            rule_type=rule.type,
            passed=len(failing) < rule.count,
            detail=f"{len(failing)} failing finding(s), limit is {rule.count - 1}",
            matching_findings=len(failing),
        )
    if isinstance(rule, AlwaysBlockRule):
        blocked = [f for f in blocking_findings(report) if f.policy_id in rule.policy_ids]
        return GateRuleResult(
            rule_type=rule.type,
            passed=not blocked,
            detail=f"{len(blocked)} finding(s) for always-block policies {sorted(rule.policy_ids)}",
            matching_findings=len(blocked),
        )
    rate_rule = rule  # FailureRateRule
    total = len(report.findings)
    failing = len(blocking_findings(report))
    percent = (failing / total * 100.0) if total else 0.0
    return GateRuleResult(
        rule_type=rate_rule.type,
        passed=percent <= rate_rule.max_percent,
        detail=f"failure rate {percent:.1f}% (limit {rate_rule.max_percent}%)",
        matching_findings=failing,
    )


def evaluate_gate(gate: QualityGate, report: ScanReport, baseline_report: ScanReport | None) -> GateResult:
    """Evaluate one gate; the gate passes only when every rule passes."""
    results = [_evaluate_rule(rule, report, baseline_report) for rule in gate.rules]
    return GateResult(gate_id=gate.id, passed=all(result.passed for result in results), rules=results)


def evaluate_pack_gates(pack: PolicyPack, report: ScanReport, baseline_report: ScanReport | None) -> GateResult | None:
    """Evaluate all gates; return the first failing gate or the first gate overall.

    Returns None when the pack defines no gates (legacy behavior applies).
    """
    if not pack.quality_gates:
        return None
    results = [evaluate_gate(gate, report, baseline_report) for gate in pack.quality_gates]
    failing = next((result for result in results if not result.passed), None)
    return failing if failing is not None else results[0]


def validate_quality_gates(pack: PolicyPack) -> list[str]:
    """Return pack-level gate authoring errors (duplicate ids, unknown policies)."""
    issues: list[str] = []
    gate_ids = [gate.id for gate in pack.quality_gates]
    if len(gate_ids) != len(set(gate_ids)):
        issues.append("quality gate ids must be unique within a pack")
    policy_ids = {policy.id for policy in pack.policies}
    for gate in pack.quality_gates:
        for rule in gate.rules:
            if isinstance(rule, AlwaysBlockRule):
                missing = sorted(set(rule.policy_ids) - policy_ids)
                if missing:
                    issues.append(f"gate {gate.id!r} references unknown policy ids: {', '.join(missing)}")
    return issues
```

Note: `FailureRateRule` is imported but used only via the fallthrough `rate_rule` — that's fine; pyright strict narrows `rule` to `FailureRateRule` after all the `isinstance` branches because the union is exhausted. Keep the import.

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_gates.py -x --tb=short`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/conformdag/gates.py tests/test_gates.py
git commit -m "feat: quality-gate evaluator (blocking-findings core, 5 rule types)"
```

---

## Task 3: Gate validation wiring

**Files:**
- Modify: `src/conformdag/cli.py` (`validate_policies`, line 151)
- Modify: `src/conformdag/platform/packs.py` (`PackService.validate_pack`, line 102)
- Test: `tests/test_cli.py`, `tests/test_platform.py`

**Interfaces:**
- Consumes: `validate_quality_gates` from `conformdag.gates` (Task 2).

- [ ] **Step 1: Write the failing tests**

In `tests/test_cli.py` add:

```python
def test_validate_policies_rejects_unknown_gate_policy_references(tmp_path: Path) -> None:
    (tmp_path / "policies").mkdir()
    (tmp_path / "standards").mkdir()
    (tmp_path / "standards/dag-authoring.md").write_text("# DAG Authoring Standards\n", encoding="utf-8")
    (tmp_path / "policies/pack.yaml").write_text(
        "schema_version: '1'\n"
        "id: x\n"
        "version: '1'\n"
        "policies: []\n"
        "quality_gates:\n"
        "  - id: default\n"
        "    rules:\n"
        "      - type: always-block\n"
        "        policy_ids: [AIR-DET-999]\n",
        encoding="utf-8",
    )
    (tmp_path / "conformdag.yaml").write_text('config_version: "1"\n', encoding="utf-8")

    result = CliRunner().invoke(app, ["validate-policies", "--path", str(tmp_path / "policies" / "pack.yaml")])

    assert result.exit_code != 0
    assert "AIR-DET-999" in result.stdout
```

Check the existing `validate_policies` signature first: it takes `path: Path | None`. The `--path` value is the pack path. Note the existing community test passes `"community"` as `--path`, so a resolved pack path works too.

In `tests/test_platform.py` add:

```python
def test_pack_validate_reports_gate_errors(client: TestClient, tmp_path: Path) -> None:
    pack_path = tmp_path / "pack.yaml"
    pack_path.write_text(
        "schema_version: '1'\n"
        "id: x\n"
        "version: '1'\n"
        "policies: []\n"
        "quality_gates:\n"
        "  - id: a\n"
        "    rules:\n"
        "      - type: max-findings\n"
        "        count: 1\n"
        "  - id: a\n"
        "    rules:\n"
        "      - type: max-findings\n"
        "        count: 2\n",
        encoding="utf-8",
    )
    factory, _ = _platform_state(client)
    service = PackService({})
    service.register("test", pack_path)

    result = service.validate_pack("test")

    assert not result["valid"]
    assert any("unique" in error for error in result["errors"])
```

This test needs `PackService` imported in `tests/test_platform.py` — add `from conformdag.platform.packs import PackService` to its imports.

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_cli.py::test_validate_policies_rejects_unknown_gate_policy_references tests/test_platform.py::test_pack_validate_reports_gate_errors -x --tb=short`
Expected: FAIL (gate errors are not reported today).

- [ ] **Step 3: Wire gate validation**

In `src/conformdag/cli.py`:
- Add `from conformdag.gates import validate_quality_gates` to the imports.
- In `validate_policies`, after `pack = select_policy_pack(resolved, Path.cwd())`, add:

```python
    gate_issues = validate_quality_gates(pack)
    if gate_issues:
        _fail(PolicyValidationError(gate_issues))
```

In `src/conformdag/platform/packs.py`:
- Add `from conformdag.gates import validate_quality_gates` to the imports.
- Replace the body of `validate_pack` with:

```python
    def validate_pack(self, pack_name: str) -> dict[str, Any]:
        pack_path = self._require_pack(pack_name)
        try:
            pack = load_policy_pack(pack_path, pack_path.parent)
        except PolicyValidationError as exc:
            return {"valid": False, "errors": str(exc).split("; ")}
        issues = validate_quality_gates(pack)
        return {"valid": not issues, "errors": issues}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_cli.py::test_validate_policies_rejects_unknown_gate_policy_references tests/test_platform.py::test_pack_validate_reports_gate_errors -x --tb=short`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/conformdag/cli.py src/conformdag/platform/packs.py tests/test_cli.py tests/test_platform.py
git commit -m "feat: gate authoring errors fail pack validation (CLI + platform)"
```

---

## Task 4: CLI gate integration + `--baseline` option

**Files:**
- Modify: `src/conformdag/cli.py` (`scan` command; add `BASELINE_OPTION`; gate-driven exit codes)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `evaluate_pack_gates` (Task 2), `select_policy_pack` (already imported), `ScanReport` model.
- Produces: `--baseline PATH` option; `report.gate_result` in JSON output; exit code 1 iff gate fails (legacy `has_blocking_failures` behavior when the pack has no gates).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py` (imports needed: `hashlib`, `yaml`, `Any` — check existing imports; `json` and `Path` are already there):

```python
def _write_gate_repo(tmp_path: Path, *, with_gate: bool, owner: str | None) -> Path:
    """Create a repo + pack with one owner policy and (optionally) a max-findings gate."""
    (tmp_path / "dags").mkdir()
    owner_kwarg = f", owner='{owner}'" if owner else ""
    (tmp_path / "dags/dag.py").write_text(
        f"from airflow import DAG\ndag = DAG(dag_id='x'{owner_kwarg})\n", encoding="utf-8"
    )
    (tmp_path / "standards").mkdir()
    document = tmp_path / "standards/dag-authoring.md"
    document.write_text("# DAG Authoring Standards\n\n## Ownership and metadata\n", encoding="utf-8")
    content_hash = hashlib.sha256(document.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    pack: dict[str, Any] = {
        "schema_version": "1",
        "id": "x",
        "version": "1",
        "policies": [
            {
                "id": "AIR-TST-001",
                "title": "owner",
                "version": "1.0.0",
                "status": "ACTIVE",
                "severity": "high",
                "airflow_profiles": ["3.3.0"],
                "ownership": {"owner": "platform"},
                "source": {
                    "document": "standards/dag-authoring.md",
                    "section": "Ownership and metadata",
                    "version": "1",
                    "content_hash": content_hash,
                },
                "invariant": "Every DAG declares an owner.",
                "safe_path": "An owner is present.",
                "enforcement": {"type": "deterministic", "deterministic_checks": ["effective-owner"], "blocking": True},
                "configuration": {"kind": "required-owner", "allowed_values": ["platform"]},
            }
        ],
    }
    if with_gate:
        pack["quality_gates"] = [{"id": "default", "rules": [{"type": "max-findings", "count": 1}]}]
    (tmp_path / "pack.yaml").write_text(yaml.safe_dump(pack), encoding="utf-8")
    (tmp_path / "conformdag.yaml").write_text('config_version: "1"\n', encoding="utf-8")
    return tmp_path


def test_scan_exits_zero_when_gate_passes_despite_findings(tmp_path: Path) -> None:
    root = _write_gate_repo(tmp_path, with_gate=True, owner=None)

    result = CliRunner().invoke(
        app, ["scan", "--path", str(root), "--policy-pack", str(root / "pack.yaml"), "--format", "json"]
    )

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["gate_result"]["gate_id"] == "default"
    assert report["gate_result"]["passed"] is True


def test_scan_exits_one_when_gate_fails(tmp_path: Path) -> None:
    root = _write_gate_repo(tmp_path, with_gate=True, owner=None)
    (tmp_path / "dags" / "dag.py").write_text("from airflow import DAG\ndag = DAG(dag_id='x')\n", encoding="utf-8")
    second = tmp_path / "dags" / "dag2.py"
    second.write_text("from airflow import DAG\ndag2 = DAG(dag_id='y')\n", encoding="utf-8")

    result = CliRunner().invoke(
        app, ["scan", "--path", str(root), "--policy-pack", str(root / "pack.yaml"), "--format", "json"]
    )

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["gate_result"]["passed"] is False


def test_scan_without_gates_keeps_legacy_exit_code(tmp_path: Path) -> None:
    root = _write_gate_repo(tmp_path, with_gate=False, owner=None)

    result = CliRunner().invoke(
        app, ["scan", "--path", str(root), "--policy-pack", str(root / "pack.yaml"), "--format", "json"]
    )

    assert result.exit_code == 1
    assert "gate_result" not in json.loads(result.stdout)


def test_scan_baseline_satisfies_no_new_findings(tmp_path: Path) -> None:
    root = _write_gate_repo(tmp_path, with_gate=False, owner=None)
    baseline = CliRunner().invoke(
        app,
        [
            "scan",
            "--path",
            str(root),
            "--policy-pack",
            str(root / "pack.yaml"),
            "--format",
            "json",
            "--output",
            str(root / "baseline.json"),
        ],
    )
    assert baseline.exit_code == 1
    pack = yaml.safe_load((root / "pack.yaml").read_text(encoding="utf-8"))
    pack["quality_gates"] = [{"id": "default", "rules": [{"type": "no-new-findings"}]}]
    (root / "pack.yaml").write_text(yaml.safe_dump(pack), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "scan",
            "--path",
            str(root),
            "--policy-pack",
            str(root / "pack.yaml"),
            "--baseline",
            str(root / "baseline.json"),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["gate_result"]["passed"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_cli.py -k "gate or baseline" -x --tb=short`
Expected: FAIL — `test_scan_exits_zero_when_gate_passes_despite_findings` fails with exit code 1 (legacy behavior), the others fail similarly.

- [ ] **Step 3: Implement CLI gate integration**

In `src/conformdag/cli.py`:
- Add imports: `from conformdag.gates import evaluate_pack_gates`.
- Add after `SEMANTIC_STRUCTURED_OUTPUT_OPTION` (~line 90):

```python
BASELINE_OPTION = typer.Option(
    None,
    "--baseline",
    help="Path to a baseline scan report JSON used by quality-gate rules.",
)
```

- Add the parameter to `scan`: after `semantic_structured_output: bool | None = SEMANTIC_STRUCTURED_OUTPUT_OPTION,` add `baseline: Path | None = BASELINE_OPTION,`.
- After `config = load_project_config(root / "conformdag.yaml")` (~line 334), load the pack object next to the existing `selected_pack` handling:

```python
    try:
        pack = select_policy_pack(selected_pack, root)
    except PolicyValidationError as exc:
        _fail(exc)
```

- After `report = normalize_report(report)` (near the end of the runtime block, before `output_report = report`), add:

```python
    baseline_report: ScanReport | None = None
    if baseline is not None:
        try:
            baseline_report = ScanReport.model_validate(json.loads(baseline.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            _fail(ValueError(f"cannot load baseline report {baseline}: {exc}"))
    gate_result = evaluate_pack_gates(pack, report, baseline_report)
    if gate_result is not None:
        report = report.model_copy(update={"gate_result": gate_result})
```

- Replace the final exit-code block:

```python
    if any(issue.fatal for issue in report.issues):
        raise typer.Exit(code=3)
    if gate_result is not None:
        if not gate_result.passed:
            raise typer.Exit(code=1)
    elif has_blocking_failures(report):
        raise typer.Exit(code=1)
```

- Add `ScanReport` to the `conformdag.models` import in cli.py.

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_cli.py -k "gate or baseline" -x --tb=short`
Expected: PASS.

- [ ] **Step 5: Full CLI suite + commit**

Run: `mise exec -- uv run pytest tests/test_cli.py -q`
Expected: PASS (existing terminal/json/sarif tests are unaffected — the repo under test has no DAG files and the default pack has no gates, so exit codes stay legacy).

```bash
git add src/conformdag/cli.py tests/test_cli.py
git commit -m "feat: scan evaluates quality gates and accepts a baseline report"
```

---

## Task 5: Platform baselines + gate persistence

**Files:**
- Create: `src/conformdag/platform/migrations/versions/0002_repository_baseline.py`
- Modify: `src/conformdag/platform/db.py` (`RepositoryRow`)
- Modify: `src/conformdag/platform/app.py` (`set_baseline` endpoint, `list_repositories`, `scan_status`)
- Modify: `src/conformdag/platform/runner.py` (gate evaluation before ingest)
- Test: `tests/test_platform.py`

**Interfaces:**
- Consumes: `evaluate_pack_gates` (Task 2), `load_policy_pack` from `conformdag.policy`.
- Produces: `PUT /api/v1/repos/{repository_id}/baseline` with body `{"scan_id": "..."}`; `RepositoryRow.baseline_scan_id`; `report_json["gate_result"]` persisted for platform scans; `list_repositories` includes `baseline_scan_id`; `scan_status` includes `gate_passed: bool | None`.

- [ ] **Step 1: Write the migration**

Create `src/conformdag/platform/migrations/versions/0002_repository_baseline.py`:

```python
"""repository baseline: baseline_scan_id column on repos

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("repos", sa.Column("baseline_scan_id", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("repos", "baseline_scan_id")
```

- [ ] **Step 2: Add the column to `RepositoryRow`**

In `src/conformdag/platform/db.py`, after `airflow_profile`:

```python
    baseline_scan_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

- [ ] **Step 3: Write the failing endpoint tests**

In `tests/test_platform.py` add:

```python
def test_baseline_set_and_listed(client: TestClient, tmp_path: Path) -> None:
    repository_id = _register(client, tmp_path)
    with _platform_state(client)[0]() as session:
        session.add(ScanRow(id="scan1", repository_id=repository_id, status="succeeded", result_fingerprint="f" * 64))
        session.commit()

    response = _as_httpx(client).put(
        "/api/v1/repos/{}/baseline".format(repository_id),
        json={"scan_id": "scan1"},
        headers={"Authorization": "Bearer secret-token"},
    )
    assert response.status_code == 200

    listed = _get(client, "/api/v1/repos").json()
    repo = next(row for row in listed if row["id"] == repository_id)
    assert repo["baseline_scan_id"] == "scan1"


def test_baseline_rejects_scan_from_another_repository(client: TestClient, tmp_path: Path) -> None:
    repository_id = _register(client, tmp_path)
    with _platform_state(client)[0]() as session:
        session.add(
            ScanRow(id="scan9", repository_id="somewhere-else", status="succeeded", result_fingerprint="f" * 64)
        )
        session.commit()

    response = _as_httpx(client).put(
        "/api/v1/repos/{}/baseline".format(repository_id),
        json={"scan_id": "scan9"},
        headers={"Authorization": "Bearer secret-token"},
    )
    assert response.status_code == 404
```

Note: `_register` (existing helper, line 89) registers a repo named `core-dags` at `tmp_path/repo`.

Also add the runner gate test (end-to-end, mirrors `test_worker_executes_queued_scan_end_to_end`):

```python
def test_runner_persists_gate_result(platform_env: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "standards").mkdir()
    (tmp_path / "standards/dag-authoring.md").write_text(
        "# DAG Authoring Standards\n\n## Ownership and metadata\n", encoding="utf-8"
    )
    document = tmp_path / "standards/dag-authoring.md"
    content_hash = hashlib.sha256(document.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    (tmp_path / "dags").mkdir()
    (tmp_path / "dags/dag.py").write_text("from airflow import DAG\ndag = DAG(dag_id='x')\n", encoding="utf-8")
    pack: dict[str, Any] = {
        "schema_version": "1",
        "id": "x",
        "version": "1",
        "quality_gates": [{"id": "default", "rules": [{"type": "max-findings", "count": 1}]}],
        "policies": [
            {
                "id": "AIR-TST-001",
                "title": "owner",
                "version": "1.0.0",
                "status": "ACTIVE",
                "severity": "high",
                "airflow_profiles": ["3.3.0"],
                "ownership": {"owner": "platform"},
                "source": {
                    "document": "standards/dag-authoring.md",
                    "section": "Ownership and metadata",
                    "version": "1",
                    "content_hash": content_hash,
                },
                "invariant": "Every DAG declares an owner.",
                "safe_path": "An owner is present.",
                "enforcement": {"type": "deterministic", "deterministic_checks": ["effective-owner"], "blocking": True},
                "configuration": {"kind": "required-owner", "allowed_values": ["platform"]},
            }
        ],
    }
    (tmp_path / "pack.yaml").write_text(yaml.safe_dump(pack), encoding="utf-8")
    (tmp_path / "conformdag.yaml").write_text('config_version: "1"\n', encoding="utf-8")

    factory = create_session_factory(platform_env)
    with factory() as session:
        session.add(RepositoryRow(id="repo1", name="r", path=str(tmp_path), policy_pack=str(tmp_path / "pack.yaml")))
        session.add(ScanRow(id="scan1", repository_id="repo1", status="queued"))
        session.commit()

    handled = run_worker_once(factory, platform_env, WorkerSettings(retention_keep=50))

    assert handled == "scan1"
    with factory() as session:
        scan = session.get(ScanRow, "scan1")
        assert scan is not None and scan.status == "succeeded"
        assert scan.report_json is not None
        gate = scan.report_json.get("gate_result")
        assert isinstance(gate, dict)
        assert gate["gate_id"] == "default"
        assert gate["passed"] is False
```

This test needs `hashlib` and `yaml` imports added to `tests/test_platform.py`.

- [ ] **Step 4: Run tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_platform.py -k "baseline or gate_result" -x --tb=short`
Expected: FAIL — endpoint missing (404) / `gate_result` absent from the persisted report.

- [ ] **Step 5: Implement the endpoint**

In `src/conformdag/platform/app.py`:
- Add a request model near `SuppressionUpdate`:

```python
class BaselineSetRequest(BaseModel):
    """Selection payload marking one scan as a repository's baseline."""

    scan_id: str
```

- Add the handler near `scan_history`:

```python
def set_baseline(request: Request, repository_id: str, payload: BaselineSetRequest) -> dict[str, str]:
    """Mark one finished scan as the baseline for its repository."""
    factory = _factory(request)
    with factory() as session:
        repository = session.get(RepositoryRow, repository_id)
        if repository is None:
            raise HTTPException(status_code=404, detail="repository not registered")
        scan = session.get(ScanRow, payload.scan_id)
        if scan is None or scan.repository_id != repository_id:
            raise HTTPException(status_code=404, detail="scan not found for this repository")
        repository.baseline_scan_id = payload.scan_id
        session.commit()
        return {"repository_id": repository_id, "baseline_scan_id": payload.scan_id}
```

- Register the route in `create_app` (after the scans routes):

```python
    app.put(API_PREFIX + "/repos/{repository_id}/baseline", dependencies=[Depends(require_admin)])(set_baseline)
```

- In `list_repositories`, add `"baseline_scan_id": row.baseline_scan_id,` to the returned dict.
- In `scan_status`, add `"gate_passed": scan.report_json.get("gate_result", {}).get("passed") if scan.report_json else None,` to the returned dict.

- [ ] **Step 6: Implement runner gate evaluation**

In `src/conformdag/platform/runner.py`:
- Add imports: `from conformdag.gates import evaluate_pack_gates`, `from conformdag.policy import load_policy_pack`, `from conformdag.models import ScanReport`.
- In `execute_scan`, replace the block from `_ingest(session, scan, normalize_report(report))` through `session.commit()` with:

```python
        gate_result = None
        if pack is not None:
            loaded_pack = None
            try:
                loaded_pack = load_policy_pack(Path(pack), Path(repository.path))
            except (ValueError, OSError):
                loaded_pack = None
            if loaded_pack is not None:
                baseline_report = None
                if repository.baseline_scan_id is not None:
                    baseline_scan = session.get(ScanRow, repository.baseline_scan_id)
                    if baseline_scan is not None and baseline_scan.report_json is not None:
                        baseline_report = ScanReport.model_validate(baseline_scan.report_json)
                gate_result = evaluate_pack_gates(loaded_pack, report, baseline_report)
        normalized = normalize_report(report)
        if gate_result is not None:
            normalized = normalized.model_copy(update={"gate_result": gate_result})
        _ingest(session, scan, normalized)
        scan.status = "succeeded"
        scan.finished_at = utcnow()
        session.commit()
        return 0
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_platform.py -k "baseline or gate_result" -x --tb=short`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/conformdag/platform/migrations/versions/0002_repository_baseline.py src/conformdag/platform/db.py src/conformdag/platform/app.py src/conformdag/platform/runner.py tests/test_platform.py
git commit -m "feat: platform baselines and gate persistence (migration 0002)"
```

---

## Task 6: `ruff-air` check kind

**Files:**
- Create: `src/conformdag/ruff_adapter.py`
- Modify: `src/conformdag/models.py` (`RuffAirConfig` + `PolicyConfiguration` union member)
- Modify: `src/conformdag/evaluator.py` (`EvaluationContext.repository_root`, `CHECK_EVALUATORS["ruff-air"]`, pass `repository_root` through `evaluate_deterministic`)
- Modify: `src/conformdag/scan.py` (pass `repository_root=root`; emit `RUFF_UNAVAILABLE` issue)
- Test: `tests/test_evaluator.py`, `tests/test_scan.py`
- Regenerate: `schemas/*.json`

**Interfaces:**
- Consumes: `EvaluationContext`, `structural_fingerprint`, `redact_evidence` (evaluator.py), `FindingStatus`, `RemediationPayload`, `RemediationAction`, `RemediationTarget` (models).
- Produces: `ruff_binary() -> str | None`, `run_ruff(repository_root: Path, rules: list[str]) -> list[dict[str, Any]] | None`, `RuffAirEvaluator` (policy_id `"AIR-DET-012"`), check kind `"ruff-air"`. Ruff JSON violations map: `filename` → relative path, `location.row` → line, `code` + `message` → evidence, fingerprint `ruff:{code}:{row}`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_evaluator.py` add (imports: `pytest`, `RuffAirEvaluator`, `ruff_adapter` module — check existing import style):

```python
def test_ruff_air_evaluator_maps_violations_to_findings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = _source_model("from airflow import DAG\ndag = DAG(dag_id='x')\n")
    policy = _policy("AIR-TST-002", "ruff-air")
    context = EvaluationContext(policy, [model], repository_root=tmp_path)
    payload = [
        {
            "filename": "dags/dag.py",
            "location": {"row": 2, "column": 7},
            "code": "AIR002",
            "message": "`dag` lacks a schedule argument",
        }
    ]

    monkeypatch.setattr("conformdag.evaluator.run_ruff", lambda *args: payload)

    findings = CHECK_EVALUATORS["ruff-air"].evaluate(context)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.policy_id == "AIR-TST-002"
    assert finding.status is FindingStatus.FAIL
    assert finding.location.file == Path("dags/dag.py")
    assert finding.location.start_line == 2
    assert "AIR002" in (finding.explanation or "")


def test_ruff_air_evaluator_skips_when_binary_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = _source_model("from airflow import DAG\ndag = DAG(dag_id='x')\n")
    policy = _policy("AIR-TST-002", "ruff-air")
    context = EvaluationContext(policy, [model], repository_root=tmp_path)

    monkeypatch.setattr("conformdag.evaluator.run_ruff", lambda *args: None)

    assert CHECK_EVALUATORS["ruff-air"].evaluate(context) == []
```

The existing `_source_model`/`_policy`-style helpers in `tests/test_evaluator.py` — reuse whatever equivalent helpers that file has (it builds `Policy` + `SourceModel` for evaluator tests; mirror its helper names, adjusting if needed).

In `tests/test_scan.py` add:

```python
def test_scan_reports_ruff_unavailable_issue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "dags").mkdir()
    (tmp_path / "dags/dag.py").write_text(
        "from airflow import DAG\ndag = DAG(dag_id='x', owner='platform')\n", encoding="utf-8"
    )
    (tmp_path / "standards").mkdir()
    document = tmp_path / "standards/dag-authoring.md"
    document.write_text("# DAG Authoring Standards\n\n## Ownership and metadata\n", encoding="utf-8")
    content_hash = hashlib.sha256(document.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    (tmp_path / "pack.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "1",
                "id": "x",
                "version": "1",
                "policies": [
                    {
                        "id": "AIR-TST-002",
                        "title": "ruff",
                        "version": "1.0.0",
                        "status": "ACTIVE",
                        "severity": "medium",
                        "airflow_profiles": ["3.3.0"],
                        "ownership": {"owner": "platform"},
                        "source": {
                            "document": "standards/dag-authoring.md",
                            "section": "Ownership and metadata",
                            "version": "1",
                            "content_hash": content_hash,
                        },
                        "invariant": "Ruff AIR violations are reported.",
                        "safe_path": "No AIR violations.",
                        "enforcement": {
                            "type": "deterministic",
                            "deterministic_checks": ["ruff-air"],
                            "blocking": True,
                        },
                        "configuration": {"kind": "ruff-air", "rules": ["AIR002"]},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "conformdag.yaml").write_text('config_version: "1"\n', encoding="utf-8")

    monkeypatch.setattr("conformdag.scan.ruff_binary", lambda: None)

    report = scan_repository(tmp_path, tmp_path / "pack.yaml")

    assert any(issue.code == "RUFF_UNAVAILABLE" for issue in report.issues)
```

And the real-ruff integration test (same file):

```python
@pytest.mark.skipif(ruff_binary() is None, reason="ruff binary not installed")
def test_ruff_air_integration_catches_air002(tmp_path: Path) -> None:
    (tmp_path / "dags").mkdir()
    (tmp_path / "dags/dag.py").write_text("from airflow import DAG\ndag = DAG(dag_id='x')\n", encoding="utf-8")
    (tmp_path / "standards").mkdir()
    document = tmp_path / "standards/dag-authoring.md"
    document.write_text("# DAG Authoring Standards\n\n## Ownership and metadata\n", encoding="utf-8")
    content_hash = hashlib.sha256(document.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    pack = {
        "schema_version": "1",
        "id": "x",
        "version": "1",
        "policies": [
            {
                "id": "AIR-TST-002",
                "title": "ruff",
                "version": "1.0.0",
                "status": "ACTIVE",
                "severity": "medium",
                "ownership": {"owner": "platform"},
                "source": {
                    "document": "standards/dag-authoring.md",
                    "section": "Ownership and metadata",
                    "version": "1",
                    "content_hash": content_hash,
                },
                "invariant": "Ruff AIR violations are reported.",
                "safe_path": "No AIR violations.",
                "enforcement": {"type": "deterministic", "deterministic_checks": ["ruff-air"], "blocking": True},
                "configuration": {"kind": "ruff-air", "rules": ["AIR002"]},
            }
        ],
    }
    (tmp_path / "pack.yaml").write_text(yaml.safe_dump(pack), encoding="utf-8")
    (tmp_path / "conformdag.yaml").write_text('config_version: "1"\n', encoding="utf-8")

    report = scan_repository(tmp_path, tmp_path / "pack.yaml")

    ruff_findings = [f for f in report.findings if f.policy_id == "AIR-TST-002"]
    assert any("AIR002" in (f.explanation or "") for f in ruff_findings)
```

Check the imports at the top of `tests/test_scan.py` for `hashlib`/`yaml`/`pytest` and add them as needed.

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_evaluator.py -k ruff tests/test_scan.py -k "ruff" -x --tb=short`
Expected: FAIL (check kind `ruff-air` not in `CHECK_EVALUATORS`).

- [ ] **Step 3: Add the `RuffAirConfig` model**

In `src/conformdag/models.py`, add after `DynamicDagFactoryConfig`:

```python
class RuffAirConfig(ConformModel):
    kind: Literal["ruff-air"] = "ruff-air"
    rules: list[str] = Field(min_length=1)
```

And add `| RuffAirConfig` to the `PolicyConfiguration` union (before the closing `,` — add to the end of the member list):

```python
    | DynamicDagFactoryConfig
    | RuffAirConfig,
```

- [ ] **Step 4: Create `src/conformdag/ruff_adapter.py`**

```python
"""Ruff AIR adapter: compose Ruff violations into ConformDAG findings.

Ruff is invoked once per scan as a subprocess with --output-format json.
Violations map into the same finding/suppression machinery as every other
deterministic check; Ruff never writes to sources (verify-by-rescan model).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

from conformdag.models import (
    EnforcementType,
    Finding,
    FindingEvidence,
    FindingLocation,
    FindingStatus,
    RemediationAction,
    RemediationPayload,
    RemediationTarget,
    RuffAirConfig,
)

RUNNER_TIMEOUT_SECONDS = 120.0


def ruff_binary() -> str | None:
    """Return the resolved ruff binary path, or None when unavailable."""
    return shutil.which("ruff")


def run_ruff(repository_root: Path, rules: list[str]) -> list[dict[str, Any]] | None:
    """Run ruff with the selected rules; return parsed JSON or None on failure.

    Returns None when ruff is unavailable, times out, or errors — callers
    degrade to no findings rather than crashing the scan.
    """
    binary = ruff_binary()
    if binary is None:
        return None
    try:
        process = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [
                binary,
                "check",
                "--select",
                ",".join(rules),
                "--output-format",
                "json",
                str(repository_root),
            ],
            capture_output=True,
            text=True,
            timeout=RUNNER_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if process.returncode not in (0, 1):  # 0 = clean, 1 = violations found
        return None
    try:
        return cast(list[dict[str, Any]], json.loads(process.stdout or "[]"))
    except json.JSONDecodeError:
        return None
```

- [ ] **Step 5: Register the evaluator**

In `src/conformdag/evaluator.py`:
- Add `repository_root: Path | None = None` to `EvaluationContext` (after `airflow_profile`).
- Add imports: `from pathlib import Path` (check whether already imported), `from conformdag.models import RuffAirConfig`, `from conformdag.ruff_adapter import run_ruff, ruff_binary`.

Add the evaluator class before `CHECK_EVALUATORS`:

```python
class RuffAirEvaluator:
    """Deterministic check kind: ``ruff-air`` (composed Ruff AIR violations)."""

    policy_id = "AIR-DET-012"

    def evaluate(self, context: EvaluationContext) -> list[Finding]:
        configuration = cast(RuffAirConfig, context.policy.configuration)
        if context.repository_root is None:
            return []
        violations = run_ruff(context.repository_root, configuration.rules)
        if not violations:
            return []
        scanned = {str(model.source.relative_path) for model in context.models}
        findings: list[Finding] = []
        for violation in violations:
            relative = str(violation.get("filename", ""))
            location = violation.get("location", {})
            row = int(location.get("row", 0)) if isinstance(location, dict) else 0
            code = str(violation.get("code", "AIR"))
            message = str(violation.get("message", ""))
            if relative not in scanned or row <= 0:
                continue
            findings.append(
                Finding(
                    policy_id=context.policy.id,
                    policy_version=context.policy.version,
                    status=FindingStatus.FAIL,
                    severity=context.policy.severity,
                    enforcement=EnforcementType.DETERMINISTIC,
                    location=FindingLocation(file=Path(relative), start_line=row, end_line=row),
                    evidence=FindingEvidence(text=redact_evidence(message), start_line=row, end_line=row),
                    explanation=message,
                    remediation=context.policy.safe_path,
                    fix=RemediationPayload(
                        fix_kind="ruff-air",
                        action=RemediationAction.MANUAL,
                        target=RemediationTarget(line=row, column=0, node="statement"),
                        hint=f"run: ruff check --select {code} --fix",
                    ),
                    fingerprint=structural_fingerprint(
                        context.policy, relative, f"ruff:{code}:{row}", FindingStatus.FAIL
                    ),
                )
            )
        return findings
```

- Register it: add `"ruff-air": RuffAirEvaluator(),` to `CHECK_EVALUATORS` and `"AIR-DET-012": CHECK_EVALUATORS["ruff-air"],` to `LEGACY_POLICY_EVALUATORS`.
- In `evaluate_deterministic`, add a `repository_root: Path | None = None` parameter, and pass it into every `EvaluationContext(...)` construction (search `EvaluationContext(` in evaluator.py; there is exactly one call site inside `evaluate_deterministic`). Also add `"ruff-air"` to `MANUAL_KINDS` in `src/conformdag/fixing/codemods.py`.

- [ ] **Step 6: Wire scan.py**

In `src/conformdag/scan.py`:
- Add `from conformdag.ruff_adapter import ruff_binary`.
- Change the `evaluate_deterministic(...)` call (~line 106) to pass `repository_root=root`.
- After the `try:` block that computes `findings, evaluated, skipped`, add:

```python
    ruff_policies = [
        policy
        for policy in pack.policies
        if policy.status.value == "ACTIVE" and any(check == "ruff-air" for check in policy.enforcement.deterministic_checks)
    ]
    if ruff_policies and ruff_binary() is None:
        issues.append(
            RunIssue(
                code="RUFF_UNAVAILABLE",
                message="ruff binary not found; the ruff-air check was skipped",
                phase="deterministic",
                fatal=False,
            )
        )
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_evaluator.py -k ruff tests/test_scan.py -k "ruff" -x --tb=short`
Expected: PASS. Then run `mise run schema:update && mise run schema --check` and commit the regenerated schemas.

- [ ] **Step 8: Commit**

```bash
git add src/conformdag/ruff_adapter.py src/conformdag/models.py src/conformdag/evaluator.py src/conformdag/scan.py src/conformdag/fixing/codemods.py tests/test_evaluator.py tests/test_scan.py schemas/
git commit -m "feat: ruff-air check kind composes Ruff AIR violations as findings"
```

---

## Task 7: Org pack completion (4 new ACTIVE policies)

**Files:**
- Modify: `policies/pack.yaml`
- Test: `tests/test_check_pack.py` (or extend `validate:packs` coverage — the pack is validated by `mise run validate:packs` and the existing pack tests)
- Possibly adjust: `tests/test_roundtrip.py` expectations (see Step 4)

**Interfaces:**
- Consumes: evaluators already registered in `CHECK_EVALUATORS` (start-date-freshness, catchup-policy, module-scope-variables, dynamic-dag-factory). All four must reference `standards/dag-authoring.md`, section `"Execution safety"`, hash `5d787d525046bab834a504d24649a119eb7a992829cc29d1809894becd3647ab` (verified: this is the SHA-256 of the current document).

- [ ] **Step 1: Write the failing test**

In `tests/test_check_pack.py` add:

```python
def test_org_pack_includes_the_new_check_kinds() -> None:
    pack = load_policy_pack(Path("policies/pack.yaml"), Path("."))
    kinds = {policy.configuration.kind for policy in pack.policies}
    assert {"start-date-freshness", "catchup-policy", "module-scope-variables", "dynamic-dag-factory"} <= kinds
    for policy in pack.policies:
        if policy.configuration.kind in {
            "start-date-freshness",
            "catchup-policy",
            "module-scope-variables",
            "dynamic-dag-factory",
        }:
            assert policy.status.value == "ACTIVE"
```

(Check the file's existing imports for `load_policy_pack`; add if missing.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `mise exec -- uv run pytest tests/test_check_pack.py::test_org_pack_includes_the_new_check_kinds -x --tb=short`
Expected: FAIL (kinds absent).

- [ ] **Step 3: Add the four policies**

Append to `policies/pack.yaml` (same document hash and section as existing Execution-safety policies):

```yaml
  - id: AIR-DET-007
    title: DAG start_date is fresh and timezone-aware
    version: 1.0.0
    status: ACTIVE
    severity: medium
    airflow_profiles: ["3.3.0"]
    ownership: {owner: platform}
    source: {document: standards/dag-authoring.md, section: "Execution safety", version: "1", content_hash: 5d787d525046bab834a504d24649a119eb7a992829cc29d1809894becd3647ab}
    invariant: Every DAG declares a start_date no older than the policy window and timezone-aware.
    safe_path: start_date is recent and carries an explicit timezone.
    enforcement: {type: deterministic, deterministic_checks: [start-date-freshness], blocking: true}
    configuration: {kind: start-date-freshness, max_age_years: 2, require_timezone: true}
  - id: AIR-DET-008
    title: DAG catchup is disabled
    version: 1.0.0
    status: ACTIVE
    severity: high
    airflow_profiles: ["3.3.0"]
    ownership: {owner: platform}
    source: {document: standards/dag-authoring.md, section: "Execution safety", version: "1", content_hash: 5d787d525046bab834a504d24649a119eb7a992829cc29d1809894becd3647ab}
    invariant: DAGs do not enable catchup with a stale start_date (backfill bomb).
    safe_path: catchup is False or explicitly approved.
    enforcement: {type: deterministic, deterministic_checks: [catchup-policy], blocking: true}
    configuration: {kind: catchup-policy, allow_catchup: false}
  - id: AIR-DET-009
    title: Module scope avoids Airflow Variable access
    version: 1.0.0
    status: ACTIVE
    severity: medium
    airflow_profiles: ["3.3.0"]
    ownership: {owner: platform}
    source: {document: standards/dag-authoring.md, section: "Execution safety", version: "1", content_hash: 5d787d525046bab834a504d24649a119eb7a992829cc29d1809894becd3647ab}
    invariant: Module-level code does not read Airflow Variables on every scheduler parse.
    safe_path: Variable access happens inside task bodies or via Jinja templates.
    enforcement: {type: deterministic, deterministic_checks: [module-scope-variables], blocking: true}
    configuration: {kind: module-scope-variables, patterns: [Variable.get]}
  - id: AIR-DET-011
    title: Module scope avoids DAG factory loops
    version: 1.0.0
    status: ACTIVE
    severity: medium
    airflow_profiles: ["3.3.0"]
    ownership: {owner: platform}
    source: {document: standards/dag-authoring.md, section: "Execution safety", version: "1", content_hash: 5d787d525046bab834a504d24649a119eb7a992829cc29d1809894becd3647ab}
    invariant: DAGs are not generated by module-scope loops.
    safe_path: Dynamic task mapping or committed config-driven generation is used instead.
    enforcement: {type: deterministic, deterministic_checks: [dynamic-dag-factory], blocking: true}
    configuration: {kind: dynamic-dag-factory, allow: false}
```

- [ ] **Step 4: Run the full suite and adjust affected expectations**

These policies change scan outcomes for every consumer of the default pack. Run:

```bash
mise run validate:packs
mise exec -- uv run pytest -m "not runtime" -x --tb=short
```

Expected: green, or failures ONLY in tests asserting old outcomes. For each failure, decide case-by-case:
- If the test asserted a finding count / outcome on a fixture that now legitimately has new findings: update the expectation to the new correct behavior (document the change in the commit message).
- If a test asserts `gate`/fix behavior that is now different (e.g. `tests/test_roundtrip.py` — new autofix/manual findings may change fix outcomes for benchmark cases): update expected outcomes to the verified new results, never weaken the assertion blindly.

Do not proceed until the whole suite passes.

- [ ] **Step 5: Commit**

```bash
git add policies/pack.yaml tests/test_check_pack.py
git commit -m "feat: org pack ships start-date-freshness, catchup-policy, module-scope-variables, dynamic-dag-factory"
```

(Include any adjusted test files in the same commit.)

---

## Task 8: Fixability matrix + catchup codemod

**Files:**
- Modify: `src/conformdag/fixing/codemods.py` (`AUTOFIX_KINDS`, `MANUAL_KINDS`, `FIXERS`, new `fix_catchup`)
- Test: `tests/test_fixing.py`

**Interfaces:**
- Consumes: `_fix_dag_kwarg` (existing, line 138), `RemediationPayload`/`RemediationAction` (models).
- Produces: `"catchup-policy"` key in `FIXERS`; `"catchup-policy"` in `AUTOFIX_KINDS`; `"start-date-freshness"`, `"module-scope-variables"`, `"sensitive-logging"`, `"dynamic-dag-factory"` in `MANUAL_KINDS`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_fixing.py` add:

```python
def test_catchup_policy_codemod_replaces_catchup_kwarg() -> None:
    source = "from airflow import DAG\ndag = DAG(dag_id='x', catchup=True)\n"
    payload = RemediationPayload(
        fix_kind="catchup-policy",
        action=RemediationAction.SET_KWARG,
        kwarg="catchup",
        target=RemediationTarget(line=2, column=0, enclosing="dag", node="dag-call"),
        value="False",
    )

    spans, needs_import = generate_spans(source, payload)

    assert spans is not None and len(spans) == 1
    assert needs_import is False
    updated = apply_spans(source, spans)
    assert "catchup=False" in updated
    assert "catchup=True" not in updated
```

(Check the existing imports in `tests/test_fixing.py`; `generate_spans`, `apply_spans`, `RemediationPayload`, `RemediationAction`, `RemediationTarget` may already be imported — extend the existing import blocks.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `mise exec -- uv run pytest tests/test_fixing.py::test_catchup_policy_codemod_replaces_catchup_kwarg -x --tb=short`
Expected: FAIL — `generate_spans` returns None (`catchup-policy` missing from FIXERS).

- [ ] **Step 3: Update the fixability matrix and register the codemod**

In `src/conformdag/fixing/codemods.py`:
- Add `"catchup-policy"` to `AUTOFIX_KINDS`.
- Add `"start-date-freshness"`, `"module-scope-variables"`, `"sensitive-logging"`, `"dynamic-dag-factory"` to `MANUAL_KINDS`.
- Add a codemod after `fix_retry_bounds`:

```python
def fix_catchup(source: str, payload: RemediationPayload, tree: ast.Module | None = None) -> list[EditSpan] | None:
    return _fix_dag_kwarg(source, payload, "catchup", "False", tree)
```

- Add `"catchup-policy": fix_catchup,` to the `FIXERS` dict.

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_fixing.py -x --tb=short`
Expected: PASS (plus the full suite stays green — run `mise exec -- uv run pytest -m "not runtime" -q`).

- [ ] **Step 5: Commit**

```bash
git add src/conformdag/fixing/codemods.py tests/test_fixing.py
git commit -m "fix: register catchup-policy codemod and new kinds in the fixability matrix"
```

---

## Task 9: Atomic pack writes + dead-code removal

**Files:**
- Modify: `src/conformdag/platform/packs.py` (`_write_pack`, remove `compute_content_hash`)
- Test: `tests/test_platform.py`

**Interfaces:**
- Produces: `_write_pack` writes `<name>.tmp` then `os.replace()`; removes `compute_content_hash` (unused — verified via repo-wide grep).

- [ ] **Step 1: Write the failing tests**

In `tests/test_platform.py` add (imports: `PolicyPack` from models, `_write_pack` from `conformdag.platform.packs`, `pytest`):

```python
def test_write_pack_is_atomic_on_replace_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pack_path = tmp_path / "pack.yaml"
    pack_path.write_text("original content\n", encoding="utf-8")
    pack = PolicyPack.model_validate({"schema_version": "1", "id": "x", "version": "1", "policies": []})

    def boom(source: Path, target: Path) -> None:
        raise OSError("simulated crash mid-write")

    monkeypatch.setattr(packs_module.os, "replace", boom)

    with pytest.raises(OSError):
        packs_module._write_pack(pack, pack_path)

    assert pack_path.read_text(encoding="utf-8") == "original content\n"
    assert not (tmp_path / "pack.yaml.tmp").exists()


def test_write_pack_replaces_atomically_and_leaves_no_tmp(tmp_path: Path) -> None:
    pack_path = tmp_path / "pack.yaml"
    pack_path.write_text("stale\n", encoding="utf-8")
    pack = PolicyPack.model_validate({"schema_version": "1", "id": "x", "version": "1", "policies": []})

    packs_module._write_pack(pack, pack_path)

    assert not (tmp_path / "pack.yaml.tmp").exists()
    reloaded = load_policy_pack(pack_path, tmp_path)
    assert reloaded.id == "x"
```

Add `import conformdag.platform.packs as packs_module` and `from conformdag.platform.packs import _write_pack` as needed, plus `from conformdag.policy import load_policy_pack` if not already imported.

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_platform.py -k write_pack -x --tb=short`
Expected: FAIL — `_write_pack` has no `tmp` path and no atomic replace.

- [ ] **Step 3: Implement atomic writes**

In `src/conformdag/platform/packs.py`:
- Add `import io`, `import os` to the imports.
- Replace `_write_pack`:

```python
def _write_pack(pack: PolicyPack, path: Path) -> None:
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.preserve_quotes = True
    data = pack.model_dump(mode="json")
    buffer = io.StringIO()
    yaml.dump(data, buffer)  # pyright: ignore[reportUnknownMemberType]
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(buffer.getvalue(), encoding="utf-8")
    try:
        os.replace(tmp_path, path)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise
```

- Delete the `compute_content_hash` function (verified unused across src/ and tests/).

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_platform.py -k write_pack -x --tb=short`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/conformdag/platform/packs.py tests/test_platform.py
git commit -m "fix: atomic pack writes and dead-code removal (B2, B9/B10)"
```

---

## Task 10: Pack-service wiring from the workspace

**Files:**
- Modify: `src/conformdag/platform/app.py` (`create_app`, `load_workspace_file`, new `_register_workspace_packs`)
- Test: `tests/test_platform.py`

**Interfaces:**
- Consumes: `load_workspace`, `WorkspaceFile`, `WorkspaceError` from `conformdag.platform.workspace`.
- Produces: packs registered as `name` (from `policy_packs`) and `repo/<name>` (from `repositories[].policy_pack`) at startup (when a workspace file exists) and on `/workspace/load`.

- [ ] **Step 1: Write the failing test**

In `tests/test_platform.py` add:

```python
def test_create_app_registers_workspace_packs_at_startup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    packs_dir = tmp_path / "packs"
    packs_dir.mkdir()
    (packs_dir / "org.yaml").write_text("schema_version: '1'\nid: org\nversion: '1'\npolicies: []\n", encoding="utf-8")
    (tmp_path / "conformdag-workspace.yaml").write_text(
        f"schema_version: '1'\nrepositories: []\npolicy_packs:\n  - name: org\n    path: {packs_dir / 'org.yaml'}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    factory = create_session_factory(f"sqlite:///{tmp_path / 'db.sqlite'}")
    app = create_app(factory, PlatformSettings(dsn="sqlite:///unused", admin_token="secret-token"))
    client = TestClient(app)

    response = _get(client, "/api/v1/packs")

    assert response.status_code == 200
    entries = response.json()
    assert any(entry["name"] == "org" and entry["id"] == "org" for entry in entries)
```

Note: `create_app` runs Alembic upgrade lazily via `create_session_factory` — check `create_session_factory`'s behavior: it upgrades on creation, so the sqlite file gets the schema. `monkeypatch.chdir(tmp_path)` makes `load_workspace()` (default path) resolve to the fixture workspace file.

- [ ] **Step 2: Run the test to verify it fails**

Run: `mise exec -- uv run pytest tests/test_platform.py::test_create_app_registers_workspace_packs_at_startup -x --tb=short`
Expected: FAIL — `/api/v1/packs` returns `[]`.

- [ ] **Step 3: Wire pack registration**

In `src/conformdag/platform/app.py`:
- Extend the workspace import: `from conformdag.platform.workspace import WorkspaceError, WorkspaceFile, load_workspace`.
- Add a module-level helper near `_factory`:

```python
def _register_workspace_packs(service: PackService, workspace: WorkspaceFile) -> None:
    """Register every workspace pack (and per-repo pack) with the pack service."""
    for pack in workspace.policy_packs:
        service.register(pack.name, pack.path)
    for repository in workspace.repositories:
        if repository.policy_pack is not None:
            service.register(f"repo/{repository.name}", repository.policy_pack)
```

- In `create_app`, after `app.state.pack_service = PackService()`:

```python
    try:
        workspace, _ = load_workspace()
    except WorkspaceError:
        pass
    else:
        _register_workspace_packs(app.state.pack_service, workspace)
```

- In `load_workspace_file`, after loading the workspace, add `_register_workspace_packs(request.app.state.pack_service, workspace)` before the commit/return.

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_platform.py -k "workspace or packs" -x --tb=short`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/conformdag/platform/app.py tests/test_platform.py
git commit -m "fix: wire policy packs from the workspace file into PackService (B1)"
```

---

## Task 11: HTTP timeout on PR creation

**Files:**
- Modify: `src/conformdag/agent/pr.py`
- Test: `tests/test_agent.py`

**Interfaces:**
- Produces: `REQUEST_TIMEOUT: Final[float] = 120.0` and `_build_client(api_url: str, token: str, transport: httpx.BaseTransport | None = None) -> httpx.Client` with `timeout=httpx.Timeout(REQUEST_TIMEOUT)`.

- [ ] **Step 1: Write the failing test**

In `tests/test_agent.py` add (imports: `httpx`, `MockTransport`, `pr` module):

```python
def test_pr_client_sets_a_120s_timeout() -> None:
    from conformdag.agent import pr as pr_module

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"html_url": "https://github.com/x/pull/1"})

    client = pr_module._build_client("https://api.github.com", "token", transport=httpx.MockTransport(handler))

    assert client.timeout == httpx.Timeout(120.0)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `mise exec -- uv run pytest tests/test_agent.py::test_pr_client_sets_a_120s_timeout -x --tb=short`
Expected: FAIL (`_build_client` doesn't exist).

- [ ] **Step 3: Add the timeout**

In `src/conformdag/agent/pr.py`:
- Add `from typing import Final` to imports (check existing).
- After `API_VERSION` (or near module constants):

```python
REQUEST_TIMEOUT: Final[float] = 120.0
```

- Add the client factory and use it:

```python
def _build_client(api_url: str, token: str, transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(
        base_url=api_url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
        },
        transport=transport,
        timeout=httpx.Timeout(REQUEST_TIMEOUT),
    )
```

- In `open_pull_request`, replace the inline `with httpx.Client(...) as client:` block with `with _build_client(self.api_url, self.token, transport=self.transport) as client:`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_agent.py -x --tb=short`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/conformdag/agent/pr.py tests/test_agent.py
git commit -m "fix: 120s HTTP timeout on PR creation (B5)"
```

---

## Task 12: Worker graceful shutdown

**Files:**
- Modify: `src/conformdag/platform/worker.py`
- Test: `tests/test_platform.py`

**Interfaces:**
- Produces: module-level `_shutdown_requested: threading.Event`, `install_signal_handlers()`, `request_shutdown()`; `run_worker` drains the in-flight scan and exits instead of looping.

- [ ] **Step 1: Write the failing tests**

In `tests/test_platform.py` add (imports: `import threading`, `import time`, `import os`, `import signal`, `import importlib`):

```python
def test_worker_drains_inflight_scan_then_stops(platform_env: str, monkeypatch: pytest.MonkeyPatch) -> None:
    worker_module = importlib.import_module("conformdag.platform.worker")
    worker_module._shutdown_requested.clear()
    factory = create_session_factory(platform_env)
    started = threading.Event()

    def fake_once(*args: object, **kwargs: object) -> str:
        started.set()
        time.sleep(0.3)
        return "scan1"

    monkeypatch.setattr(worker_module, "run_worker_once", fake_once)
    completed: list[str] = []

    def run() -> None:
        worker_module.run_worker(factory, platform_env, WorkerSettings(poll_seconds=0.05))
        completed.append("done")

    thread = threading.Thread(target=run)
    thread.start()
    assert started.wait(timeout=5)
    worker_module.request_shutdown()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert completed == ["done"]


def test_signal_handler_requests_shutdown() -> None:
    worker_module = importlib.import_module("conformdag.platform.worker")
    worker_module._shutdown_requested.clear()
    worker_module.install_signal_handlers()

    os.kill(os.getpid(), signal.SIGTERM)

    assert worker_module._shutdown_requested.is_set()
    worker_module._shutdown_requested.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_platform.py -k "shutdown" -x --tb=short`
Expected: FAIL (no `_shutdown_requested`, no `install_signal_handlers`).

- [ ] **Step 3: Implement graceful shutdown**

In `src/conformdag/platform/worker.py`:
- Add imports: `import logging`, `import signal`, `import threading`.
- Add module-level state after `DEFAULT_MAX_ATTEMPTS`:

```python
_shutdown_requested = threading.Event()


def install_signal_handlers() -> None:
    """Request a graceful shutdown on SIGTERM/SIGINT (main thread only)."""
    signal.signal(signal.SIGTERM, lambda signum, frame: _shutdown_requested.set())
    signal.signal(signal.SIGINT, lambda signum, frame: _shutdown_requested.set())


def request_shutdown() -> None:
    """Ask the worker loop to stop after the in-flight scan completes."""
    _shutdown_requested.set()
```

- Replace `run_worker` with:

```python
def run_worker(session_factory: sessionmaker[Session], dsn: str, settings: WorkerSettings) -> None:
    """Run the durable worker loop until interrupted or shut down gracefully."""
    logger = logging.getLogger("conformdag.worker")
    try:
        install_signal_handlers()
    except ValueError:
        pass  # not the main thread; shutdown can still be requested programmatically
    while not _shutdown_requested.is_set():
        try:
            handled = run_worker_once(session_factory, dsn, settings)
            if handled is None and not _shutdown_requested.is_set():
                time.sleep(settings.poll_seconds)
        except KeyboardInterrupt:
            return
    logger.info("worker drained the in-flight scan and shut down", extra={"event": "worker_stopped"})
```

Note on the grace period: the in-flight subprocess already has a hard cap (`settings.timeout_seconds`, default 1800s) — that cap is the kill-after-grace-period. The loop never abandons a claimed scan.

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_platform.py -k "shutdown" -x --tb=short`
Expected: PASS. Then run the full platform file: `mise exec -- uv run pytest tests/test_platform.py -q`.

- [ ] **Step 5: Commit**

```bash
git add src/conformdag/platform/worker.py tests/test_platform.py
git commit -m "feat: worker drains the in-flight scan and shuts down gracefully (B6)"
```

---

## Task 13: Structured JSON logging

**Files:**
- Create: `src/conformdag/platform/logging.py`
- Modify: `src/conformdag/platform/app.py` (request logging middleware)
- Modify: `src/conformdag/platform/worker.py` (lifecycle log lines)
- Modify: `src/conformdag/platform/runner.py` (phase log lines)
- Test: `tests/test_platform.py`

**Interfaces:**
- Produces: `JsonFormatter(logging.Formatter)`, `install_json_logging() -> None`; middleware logs `conformdag.platform.request` with extras `request_id, method, path, status, duration_ms` and echoes `X-Request-ID` on responses.

- [ ] **Step 1: Write the failing tests**

In `tests/test_platform.py` add (imports: `import logging`, `import json` if missing):

```python
def test_json_formatter_emits_single_line_json() -> None:
    from conformdag.platform import logging as platform_logging

    formatter = platform_logging.JsonFormatter()
    record = logging.LogRecord("conformdag.worker", logging.INFO, "worker.py", 10, "scan started", None, None)
    record.scan_id = "scan1"

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "conformdag.worker"
    assert payload["message"] == "scan started"
    assert payload["scan_id"] == "scan1"


def test_request_middleware_logs_and_echoes_request_id(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="conformdag.platform.request"):
        response = _get(client, "/api/v1/health")

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")
    assert any(record.request_id == response.headers["X-Request-ID"] for record in caplog.records)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_platform.py -k "json_formatter or request_middleware" -x --tb=short`
Expected: FAIL (module missing / no X-Request-ID header).

- [ ] **Step 3: Implement the formatter**

Create `src/conformdag/platform/logging.py`:

```python
"""Structured JSON logging for the platform tier (no new dependencies)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

RESERVED_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
        "message",
    }
)


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON objects with extra fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in RESERVED_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def install_json_logging() -> None:
    """Attach the JSON formatter to the root logger exactly once."""
    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler.formatter, JsonFormatter):
            return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)
```

- [ ] **Step 4: Add the request middleware**

In `src/conformdag/platform/app.py`:
- Add imports: `import logging`, `import time`, `import uuid`, `from collections.abc import Awaitable, Callable`.
- Inside `create_app` (before the route registrations):

```python
    @app.middleware("http")
    async def request_logging_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        response.headers["X-Request-ID"] = request_id
        logging.getLogger("conformdag.platform.request").info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
```

- [ ] **Step 5: Add worker/runner log lines**

In `src/conformdag/platform/worker.py`: inside `run_worker_once`, log `"scan_claimed"` after a successful claim (extra `scan_id`) and `"scan_finished"` before return (extra `scan_id`, `error` when present). In `src/conformdag/platform/runner.py`: log `"scan_started"` / `"scan_completed"` around the `scan_repository` call in `execute_scan` (extra `scan_id`).

- [ ] **Step 6: Run tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_platform.py -k "json_formatter or request_middleware" -x --tb=short`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/conformdag/platform/logging.py src/conformdag/platform/app.py src/conformdag/platform/worker.py src/conformdag/platform/runner.py tests/test_platform.py
git commit -m "feat: structured JSON logging with request middleware (B7)"
```

---

## Task 14: Findings + history pagination

**Files:**
- Modify: `src/conformdag/platform/app.py` (`scan_findings`, `scan_history`)
- Test: `tests/test_platform.py`

**Interfaces:**
- Produces: `limit: Annotated[int, Query(ge=1, le=500)] = 50` and `offset: Annotated[int, Query(ge=0)] = 0` query params on both endpoints, applied via `.limit().offset()`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_platform.py` add:

```python
def test_findings_endpoint_paginates(client: TestClient, tmp_path: Path) -> None:
    repository_id = _register(client, tmp_path)
    with _platform_state(client)[0]() as session:
        scan = ScanRow(id="scan1", repository_id=repository_id, status="succeeded", result_fingerprint="f" * 64)
        session.add(scan)
        for index in range(3):
            session.add(
                FindingRow(
                    scan_id="scan1",
                    repository_id=repository_id,
                    policy_id="AIR-DET-001",
                    policy_version="1.0.0",
                    status="FAIL",
                    severity="high",
                    file_path=f"dags/f{index}.py",
                    start_line=index + 1,
                    fingerprint=f"{index:064d}",
                    suppressed=False,
                )
            )
        session.commit()

    page_one = _get(client, "/api/v1/scans/scan1/findings?limit=2").json()
    page_two = _get(client, "/api/v1/scans/scan1/findings?limit=2&offset=2").json()

    assert len(page_one) == 2
    assert len(page_two) == 1
    assert page_one[0]["file_path"] == "dags/f0.py"
    assert page_two[0]["file_path"] == "dags/f2.py"


def test_findings_endpoint_rejects_bad_limit(client: TestClient) -> None:
    response = _get(client, "/api/v1/scans/anything/findings?limit=0")
    assert response.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_platform.py -k "paginates or bad_limit" -x --tb=short`
Expected: FAIL (limit ignored → 3 rows; limit=0 → 200 today).

- [ ] **Step 3: Add pagination**

In `src/conformdag/platform/app.py`:
- Add `Query` to the fastapi import: `from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response`.
- Change `scan_findings` signature to:

```python
def scan_findings(
    request: Request,
    scan_id: str,
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, object]]:
```

and apply `.limit(limit).offset(offset)` before `.all()`.

- Change `scan_history` signature the same way (keeping the existing `repository_id: str` parameter) and apply the same `.limit(limit).offset(offset)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_platform.py -k "paginates or bad_limit" -x --tb=short`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/conformdag/platform/app.py tests/test_platform.py
git commit -m "feat: pagination on scan findings and history (F5)"
```

---

## Task 15: CORS middleware

**Files:**
- Modify: `src/conformdag/platform/app.py` (`PlatformSettings`, `load_settings`, `create_app`)
- Test: `tests/test_platform.py`

**Interfaces:**
- Produces: `PlatformSettings.cors_origins: list[str] = ["http://localhost:5173"]`; env `CONFORMDAG_PLATFORM_CORS_ORIGINS` (comma-separated); `CORSMiddleware` with `allow_methods=["*"]`, `allow_headers=["*"]`, `allow_credentials=True`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_platform.py` add:

```python
def test_cors_preflight_allows_configured_origin(client: TestClient) -> None:
    response = _as_httpx(client).options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_rejects_unknown_origin(client: TestClient) -> None:
    response = _as_httpx(client).options(
        "/api/v1/health",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_platform.py -k cors -x --tb=short`
Expected: FAIL (no CORS headers).

- [ ] **Step 3: Add CORS support**

In `src/conformdag/platform/app.py`:
- Add import: `from fastapi.middleware.cors import CORSMiddleware`.
- Add `cors_origins: list[str] = ["http://localhost:5173"]` to `PlatformSettings`.
- In `load_settings`:

```python
    cors_raw = os.environ.get("CONFORMDAG_PLATFORM_CORS_ORIGINS", "http://localhost:5173")
    origins = [origin.strip() for origin in cors_raw.split(",") if origin.strip()]
    return PlatformSettings(dsn=dsn, admin_token=token, retention_keep=retention, cors_origins=origins)
```

- In `create_app`, after `app.state.settings = settings`:

```python
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_platform.py -k cors -x --tb=short`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/conformdag/platform/app.py tests/test_platform.py
git commit -m "feat: CORS middleware with configurable origins (B14)"
```

---

## Task 16: TaskFlow DAG matching inside `with DAG(...)`

**Files:**
- Modify: `src/conformdag/analysis.py` (`_ModelVisitor.__init__` + new `visit_With` + `_check_taskflow_decorator`)
- Modify: `tests/test_check_pack.py` (update the existing `dag_name is None` assertion for the `with DAG` case)
- Test: `tests/test_analysis.py`

**Interfaces:**
- Consumes: `_qualified_name` (existing).
- Produces: `_ModelVisitor._with_dag_stack: list[str]`; TaskFlow `TaskRecord.dag_name` resolves to the enclosing `with DAG(...) as <name>:` variable when present.

- [ ] **Step 1: Write the failing test**

In `tests/test_analysis.py` add:

```python
def test_taskflow_task_inside_with_dag_gets_dag_name() -> None:
    source = (
        "from airflow.decorators import task\n"
        "from airflow import DAG\n\n"
        "with DAG(dag_id='x') as dag:\n"
        "    @task\n"
        "    def extract():\n"
        "        return 1\n"
    )
    source_file = SourceFile(
        path=Path("dags/x.py"),
        relative_path="dags/x.py",
        content=source,
        content_hash="c" * 64,
    )

    model, issue = analyze_source(source_file)

    assert model is not None
    assert issue is None
    taskflow = [task for task in model.tasks if task.taskflow]
    assert len(taskflow) == 1
    assert taskflow[0].dag_name == "dag"
```

(Check `tests/test_analysis.py` for the existing `SourceFile`/`analyze_source` import pattern and mirror it.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `mise exec -- uv run pytest tests/test_analysis.py::test_taskflow_task_inside_with_dag_gets_dag_name -x --tb=short`
Expected: FAIL — `dag_name is None`.

- [ ] **Step 3: Track enclosing `with DAG` contexts**

In `src/conformdag/analysis.py`, in `_ModelVisitor.__init__`, add `self._with_dag_stack: list[str] = []`. Add the visitor method (next to `visit_Assign`):

```python
    def visit_With(self, node: ast.With) -> None:
        entered: list[str] = []
        for item in node.items:
            context = item.context_expr
            name = None
            if (
                isinstance(context, ast.Call)
                and _qualified_name(context.func) is not None
                and _qualified_name(context.func).rsplit(".", 1)[-1] == "DAG"
            ):
                if item.optional_vars is not None and isinstance(item.optional_vars, ast.Name):
                    name = item.optional_vars.id
                self._with_dag_stack.append(name or "")
                entered.append(name or "")
        self.generic_visit(node)
        for _ in entered:
            self._with_dag_stack.pop()
```

In `_check_taskflow_decorator`, replace `dag_name=None,` with:

```python
                    dag_name=self._with_dag_stack[-1] if self._with_dag_stack else None,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_analysis.py -x --tb=short`
Expected: PASS.

Then run `tests/test_check_pack.py`: its `test_taskflow_tasks_are_visible_to_the_analyzer` fixture wraps tasks in `with DAG(dag_id="secrets", schedule=None) as dag:` — update the assertion `assert all(task.dag_name is None for task in taskflow_tasks)` to `assert all(task.dag_name == "dag" for task in taskflow_tasks)`, and include that file in the commit.

- [ ] **Step 5: Commit**

```bash
git add src/conformdag/analysis.py tests/test_analysis.py tests/test_check_pack.py
git commit -m "fix: TaskFlow tasks inside with DAG(...) resolve their dag_name (B11)"
```

---

## Task 17: Span-application hardening in the fix engine

**Files:**
- Modify: `src/conformdag/fixing/engine.py` (`_patch_candidates`)
- Test: `tests/test_fixing.py`

**Interfaces:**
- Consumes: `apply_spans` (raises `ValueError` on overlapping spans), `EditSpan`.
- Produces: `_patch_candidates` deduplicates identical spans, converts overlapping-span `ValueError`s into `ResidualFailure`s, and never crashes the scan.

- [ ] **Step 1: Write the failing test**

In `tests/test_fixing.py` add:

```python
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
    monkeypatch.setattr(
        engine_module,
        "generate_spans",
        lambda source, payload: (
            [
                EditSpan(1, 0, 1, 8, "replaced"),
                EditSpan(1, 3, 1, 4, "overlap"),
            ],
            False,
        ),
    )
    monkeypatch.setattr(engine_module, "timedelta_import_span", lambda source: EditSpan(1, 0, 1, 0, ""))

    candidates, residuals = engine_module._patch_candidates(original, {}, {"dags/a.py": [finding]}, 1)

    assert candidates == {}
    assert len(residuals) == 1
    assert residuals[0].policy_id == "AIR-TST-001"
    assert "overlap" in residuals[0].reason
```

Check `ResidualFailure`'s fields in `src/conformdag/fixing/engine.py` (lines 85–91): it currently has `policy_id, path, fix_kind, iterations` and no `reason` field — Step 3 adds `reason: str = ""`.

Also add:

```python
def test_patch_candidates_deduplicates_identical_spans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from conformdag.fixing import engine as engine_module

    original = {"dags/a.py": "from airflow import DAG\n"}
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
    monkeypatch.setattr(engine_module, "generate_spans", lambda source, payload: ([span, span], False))
    monkeypatch.setattr(engine_module, "timedelta_import_span", lambda source: EditSpan(1, 0, 1, 0, ""))

    candidates, residuals = engine_module._patch_candidates(original, {}, {"dags/a.py": [finding]}, 1)

    assert not residuals
    assert candidates["dags/a.py"].count("owner='platform'") == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_fixing.py -k "patch_candidates" -x --tb=short`
Expected: FAIL — the overlap case raises `ValueError` out of `_patch_candidates` (or the assertion about `reason` fails first).

- [ ] **Step 3: Harden `_patch_candidates`**

In `src/conformdag/fixing/engine.py`, in `_patch_candidates`, replace the `spans.extend(finding_spans)` accumulation and the final `apply_spans` call:

- Deduplicate before applying:

```python
        unique_spans: list[EditSpan] = []
        for span in spans:
            if span not in unique_spans:
                unique_spans.append(span)
```

- Wrap application:

```python
        if needs_import:
            import_span = timedelta_import_span(source)
            if import_span not in unique_spans:
                unique_spans.append(import_span)
        try:
            candidates[relative] = apply_spans(source, unique_spans)
        except ValueError as exc:
            residuals.append(
                ResidualFailure(
                    policy_id=",".join(sorted({finding.policy_id for finding in findings})),
                    path=relative,
                    fix_kind=",".join(sorted({finding.fix.fix_kind for finding in findings if finding.fix})),
                    iterations=iteration,
                    reason=f"overlapping edit spans: {exc}",
                )
            )
```

- Add `reason: str = ""` to the `ResidualFailure` dataclass (default last, so existing constructions remain valid).

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_fixing.py -x --tb=short && mise exec -- uv run pytest tests/test_roundtrip.py -x --tb=short`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/conformdag/fixing/engine.py tests/test_fixing.py
git commit -m "fix: fix engine treats overlapping spans as residuals instead of crashing (B12)"
```

---

## Task 18: Branch-name truncation for the agent pipeline

**Files:**
- Modify: `src/conformdag/agent/pipeline.py`
- Test: `tests/test_agent.py`

**Interfaces:**
- Produces: `BRANCH_MAX_LENGTH = 240`, `_branch_name(branch_prefix: str, applied_file: str) -> str` — truncates to ≤240 chars with an 8-char SHA-256 suffix for uniqueness.

- [ ] **Step 1: Write the failing test**

In `tests/test_agent.py` add:

```python
def test_branch_name_truncates_long_paths_with_hash_suffix() -> None:
    from conformdag.agent import pipeline as pipeline_module

    long_file = "/".join(["segment"] * 40) + ".py"
    branch = pipeline_module._branch_name("conformdag/fix", long_file)

    assert len(branch) <= 240
    assert branch.startswith("conformdag/fix")
    assert branch[-9] == "-"


def test_branch_name_keeps_short_paths_unchanged() -> None:
    from conformdag.agent import pipeline as pipeline_module

    branch = pipeline_module._branch_name("conformdag/fix", "dags/reporting.py")

    assert branch == "conformdag/fixdags-reporting.py"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_agent.py -k branch_name -x --tb=short`
Expected: FAIL (no `_branch_name`).

- [ ] **Step 3: Implement truncation**

In `src/conformdag/agent/pipeline.py`:
- Add `import hashlib` to imports.
- After `BRANCH_PREFIX` add `BRANCH_MAX_LENGTH = 240`.
- Add the helper:

```python
def _branch_name(branch_prefix: str, applied_file: str) -> str:
    """Build a git-legal branch name, truncating long paths with a hash suffix."""
    raw = f"{branch_prefix}{applied_file.replace('/', '-')}"
    if len(raw) <= BRANCH_MAX_LENGTH:
        return raw
    suffix = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    return f"{raw[: BRANCH_MAX_LENGTH - 9]}-{suffix}"
```

- Replace the `branch = f"{branch_prefix}{pipeline.applied_files[0].replace('/', '-')}"` line (line 99) with `branch = _branch_name(branch_prefix, pipeline.applied_files[0])`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_agent.py -x --tb=short`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/conformdag/agent/pipeline.py tests/test_agent.py
git commit -m "fix: truncate agent branch names to the git 255-char limit (B13)"
```

---

## Task 19: DX commands (`policy hash`, `policy new`, `doctor`, `init` workspace)

**Files:**
- Modify: `src/conformdag/cli.py` (extend `policy_app`, `init`, new `doctor` command)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `CHECK_EVALUATORS` (registry), `select_policy_pack`, `load_project_config`, `validate_policy_provenance`, `validate_quality_gates`, `Policy` model, `shutil.which`, `create_engine` (guarded platform import).
- Produces: `conformdag policy hash <document>`, `conformdag policy new <id> --kind <kind> [--document PATH]`, `conformdag doctor`, `conformdag init` (now also scaffolds a commented `conformdag-workspace.yaml`).

- [ ] **Step 1: Write the failing tests**

In `tests/test_cli.py` add (imports: `hashlib`, `shutil` — check existing):

```python
def test_policy_hash_prints_sha256_of_document(tmp_path: Path) -> None:
    document = tmp_path / "standards.md"
    document.write_text("hello\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["policy", "hash", str(document)])

    assert result.exit_code == 0
    assert result.stdout.strip() == hashlib.sha256(b"hello\n").hexdigest()


def test_policy_new_rejects_unknown_kind(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["policy", "new", "AIR-TST-999", "--kind", "nope"])

    assert result.exit_code != 0
    assert "unknown check kind" in result.stdout


def test_policy_new_scaffolds_valid_policy_block(tmp_path: Path) -> None:
    (tmp_path / "standards").mkdir()
    document = tmp_path / "standards" / "dag-authoring.md"
    document.write_text("# DAG Authoring Standards\n\n## Execution safety\n", encoding="utf-8")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["policy", "new", "AIR-TST-777", "--kind", "start-date-freshness"])

    monkeypatch.undo()
    assert result.exit_code == 0
    assert "AIR-TST-777" in result.stdout
    assert hashlib.sha256(document.read_text(encoding="utf-8").encode("utf-8")).hexdigest() in result.stdout
```

Note: prefer `tmp_path.monkeypatch`-free style — use `monkeypatch` fixture parameter instead: `def test_policy_new_scaffolds_valid_policy_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:` and `monkeypatch.chdir(tmp_path)` (auto-undo).

```python
def test_init_writes_workspace_scaffold(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["init", "--path", str(tmp_path)])

    assert result.exit_code == 0
    workspace = (tmp_path / "conformdag-workspace.yaml").read_text(encoding="utf-8")
    assert "schema_version" in workspace
    assert "policy_packs:" in workspace


def test_doctor_reports_healthy_tmp_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    CliRunner().invoke(app, ["init", "--path", str(tmp_path)])
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "config" in result.stdout
```

Note on `doctor` + docker: `shutil.which("docker")` may return None on CI/dev machines — the doctor report lists it as a warning, not a failure (exit code unaffected by docker absence; only warn). Make sure the test asserts only config/pack checks, not docker.

- [ ] **Step 2: Run tests to verify they fail**

Run: `mise exec -- uv run pytest tests/test_cli.py -k "policy_hash or policy_new or workspace_scaffold or doctor_reports" -x --tb=short`
Expected: FAIL (unknown commands / no workspace scaffold).

- [ ] **Step 3: Implement `policy hash` and `policy new`**

In `src/conformdag/cli.py`:
- Add imports: `import hashlib`, `import shutil`, `import sys` (check existing), `from ruamel.yaml import YAML` (for scaffold rendering), `from conformdag.evaluator import CHECK_EVALUATORS`, `from conformdag.gates import validate_quality_gates`, `from conformdag.policy import validate_policy_provenance`, `from conformdag.models import ScanReport` (if not already there), `from pathlib import Path` (already).
- In the `policy_app` section (after `policy_reference` or at the end of the policy commands):

```python
@policy_app.command("hash")
def policy_hash(document: str) -> None:
    """Print the SHA-256 provenance hash of a standards document."""
    path = Path(document)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        _fail(ValueError(f"cannot read document {document}: {exc}"))
    typer.echo(hashlib.sha256(text.encode("utf-8")).hexdigest())
```

- Also in `policy_app`:

```python
@policy_app.command("new")
def policy_new(
    policy_id: str,
    kind: str = typer.Option(..., "--kind", help="Check kind for the policy configuration."),
    document: str = typer.Option("standards/dag-authoring.md", "--document", help="Standards document for provenance."),
) -> None:
    """Print a valid policy block scaffold for a check kind."""
    if kind not in CHECK_EVALUATORS:
        _fail(ValueError(f"unknown check kind {kind!r}; known kinds: {', '.join(sorted(CHECK_EVALUATORS))}"))
    doc_path = Path(document)
    try:
        content_hash = hashlib.sha256(doc_path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    except OSError as exc:
        _fail(ValueError(f"cannot read document {document}: {exc}"))
    block: dict[str, object] = {
        "id": policy_id,
        "title": "TBD — describe the invariant in one line",
        "version": "1.0.0",
        "status": "ACTIVE",
        "severity": "medium",
        "airflow_profiles": ["3.3.0"],
        "ownership": {"owner": "platform"},
        "source": {"document": document, "section": "Standards", "version": "1", "content_hash": content_hash},
        "invariant": "TBD",
        "safe_path": "TBD",
        "enforcement": {"type": "deterministic", "deterministic_checks": [kind], "blocking": True},
        "configuration": {"kind": kind},
    }
    try:
        Policy.model_validate(block)
    except ValueError as exc:
        _fail(ValueError(f"scaffolded policy is invalid for kind {kind!r}: {exc}"))
    yaml = YAML()
    yaml.default_flow_style = False
    buffer = io.StringIO()
    yaml.dump(block, buffer)  # pyright: ignore[reportUnknownMemberType]
    typer.echo(buffer.getvalue(), nl=False)
```

(Add `import io` to cli.py imports.)

- [ ] **Step 4: Implement `doctor`**

In `src/conformdag/cli.py` add a new top-level command (near `worker_command`):

```python
@app.command("doctor")
def doctor() -> None:
    """Diagnose the local workspace: config, pack, registry, provenance, runtime."""
    root = Path.cwd()
    rows: list[tuple[str, bool, str]] = []

    config: ProjectConfig | None = None
    try:
        config = load_project_config(root / "conformdag.yaml")
        rows.append(("config", True, "conformdag.yaml parses"))
    except (OSError, ValueError) as exc:
        rows.append(("config", False, str(exc)))

    pack: PolicyPack | None = None
    try:
        pack = select_policy_pack(None, root)
        rows.append(("pack", True, f"{pack.id} {pack.version} ({len(pack.policies)} policies)"))
    except PolicyValidationError as exc:
        rows.append(("pack", False, str(exc)))

    if pack is not None and config is not None:
        unknown = sorted(
            {policy.configuration.kind for policy in pack.policies if policy.configuration.kind not in CHECK_EVALUATORS}
        )
        rows.append(
            (
                "registry",
                not unknown,
                "every policy kind is registered" if not unknown else f"unknown kinds: {', '.join(unknown)}",
            )
        )
        pack_path = resolve_configured_policy_pack(config.scan.policy_pack, scan_root=root, from_cli=False)
        provenance = validate_policy_provenance(pack, pack_path=pack_path, repository_root=root)
        rows.append(
            (
                "provenance",
                not provenance,
                "; ".join(provenance) if provenance else "all policy provenance resolves",
            )
        )
        gate_issues = validate_quality_gates(pack)
        rows.append(
            (
                "gates",
                not gate_issues,
                "; ".join(gate_issues) if gate_issues else "quality gates are well-formed",
            )
        )

    docker = shutil.which("docker")
    rows.append(
        (
            "docker",
            docker is not None,
            "docker binary found" if docker else "docker not found; runtime checks unavailable",
        )
    )

    for label, ok, detail in rows:
        console.print(f"[{'green' if ok else 'red'}]{'PASS' if ok else 'FAIL'}[/] {label}: {detail}")
    if any(not ok for _, ok, _ in rows):
        raise typer.Exit(code=1)
```

New imports for cli.py: `import shutil`, `from conformdag.evaluator import CHECK_EVALUATORS`, `from conformdag.gates import validate_quality_gates`, `from conformdag.policy import resolve_configured_policy_pack, validate_policy_provenance`, and `ProjectConfig` added to the existing `conformdag.models` import (it lives in `models.py`, line 468).

- [ ] **Step 5: Extend `init`**

In the `init` command's `files` dict, add:

```python
        root / "conformdag-workspace.yaml": (
            "# ConformDAG platform workspace (optional — only the platform reads this).\n"
            'schema_version: "1"\n'
            "# repositories:\n"
            "#   - name: core-dags\n"
            "#     path: ./dags-repo\n"
            "#     policy_pack: ./policies/pack.yaml\n"
            "# policy_packs:\n"
            "#   - name: org\n"
            "#     path: ./policies/pack.yaml\n"
        ),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `mise exec -- uv run pytest tests/test_cli.py -x --tb=short`
Expected: PASS (all existing CLI tests stay green — `init` adds a file, which the existing init tests don't forbid).

- [ ] **Step 7: Commit**

```bash
git add src/conformdag/cli.py tests/test_cli.py
git commit -m "feat: DX commands — policy hash/new, doctor, init workspace scaffold"
```

---

## Task 20: Full gate + spec self-review

- [ ] **Step 1: Run the entire local gate**

```bash
mise run check
mise run test:coverage
```

Expected: green and ≥90%. If `mise run check` surfaces lint/type issues in the new code, fix them in follow-up commits (one fix per commit where sensible).

- [ ] **Step 2: Spec coverage check**

Walk the spec's acceptance criteria against the tasks:
- B1–B14 closed: Task 10 (B1), 9 (B2/B9/B10), 7+8 (B3/B4/B8), 11 (B5), 12 (B6), 13 (B7), 14 (F5/F17 pagination — retention was already wired), 15 (B14), 16 (B11), 17 (B12), 18 (B13). ✓
- Four DX commands: Task 19. ✓
- `no-new-findings` + baseline demonstrated end to end: Task 4 test `test_scan_baseline_satisfies_no_new_findings` + Task 5 runner test. ✓
- `ruff-air` against a real AIR violation: Task 6 integration test. ✓
- Gates green: Step 1. ✓

- [ ] **Step 3: Push the branch**

```bash
git push origin feat/policy-management
```

(No PR unless the user asks — do not open one.)

- [ ] **Step 4: Report completion with evidence**

List the commits per task and the final `mise run check` / coverage numbers. Then per the roadmap, P1 is done and P2 (design system + UI surface) is the next sub-project — do not start P2 without the user's go-ahead.
