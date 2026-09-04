"""Round-trip benchmark stage: fix violation cases and assert clean re-scans."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml import YAML

from conformdag.benchmark import BenchmarkManifest, BenchmarkValidationError
from conformdag.fixing import run_fix
from conformdag.fixing.codemods import AUTOFIX_KINDS
from conformdag.models import FindingStatus, PolicyPack
from conformdag.policy import load_policy_pack
from conformdag.scan import scan_repository


def _empty_cases() -> list[RoundtripCaseResult]:
    return []


@dataclass(frozen=True)
class RoundtripCaseResult:
    """Outcome of one inject-fix-verify round trip."""

    case_id: str
    policy_id: str
    passed: bool
    error: str | None = None


@dataclass
class RoundtripResult:
    """Aggregate round-trip stage result over the benchmark corpus."""

    total_cases: int = 0
    cases: list[RoundtripCaseResult] = field(default_factory=_empty_cases)

    @property
    def passed_cases(self) -> int:
        return sum(1 for case in self.cases if case.passed)

    @property
    def passed(self) -> bool:
        return bool(self.cases) and self.passed_cases == self.total_cases


def _fixable_policy_ids(pack: PolicyPack) -> set[str]:
    return {
        policy.id
        for policy in pack.policies
        if policy.enforcement.type.value in {"deterministic", "hybrid"} and policy.configuration.kind in AUTOFIX_KINDS
    }


def _corpus_config_text() -> str:
    return (
        'config_version: "1"\nscan:\n  include:\n    - "**/*.py"\n  exclude:\n    - "**/.venv/**"\n    - "**/.git/**"\n'
    )


def _run_case(
    case_id: str,
    policy_id: str,
    fixture: Path,
    pack_path: Path,
) -> RoundtripCaseResult:
    with tempfile.TemporaryDirectory(prefix="conformdag-roundtrip-") as temp:
        root = Path(temp)
        (root / "dags").mkdir()
        (root / "conformdag.yaml").write_text(_corpus_config_text(), encoding="utf-8")
        shutil.copyfile(fixture, root / "dags" / fixture.name)
        outcome = run_fix(root, pack_path, apply=True)
        if outcome.residuals:
            detail = ", ".join(f"{item.policy_id}:{item.fix_kind}" for item in outcome.residuals)
            return RoundtripCaseResult(
                case_id=case_id,
                policy_id=policy_id,
                passed=False,
                error=f"residual failures after fix: {detail}",
            )
        report = scan_repository(root, pack_path)
        if not report.complete:
            return RoundtripCaseResult(
                case_id=case_id,
                policy_id=policy_id,
                passed=False,
                error="re-scan of the fixed corpus is incomplete",
            )
        failing = {
            item.policy_id for item in report.findings if item.status is FindingStatus.FAIL and not item.suppressed
        }
        if policy_id in failing:
            return RoundtripCaseResult(
                case_id=case_id,
                policy_id=policy_id,
                passed=False,
                error=f"{policy_id} still fails after fix",
            )
        return RoundtripCaseResult(case_id=case_id, policy_id=policy_id, passed=True)


def run_fix_roundtrip(
    manifest_path: Path,
    pack_path: Path,
    corpus_root: Path,
) -> RoundtripResult:
    """Run the inject-fix-verify stage over every applicable violation case.

    Only violation cases of mechanically fixable policies participate; manual
    and proposed-only kinds are out of scope by the fixability matrix.

    Args:
        manifest_path: Path to the benchmark manifest YAML.
        pack_path: Path to the policy pack used for both scan and fix.
        corpus_root: Root directory containing the manifest's fixtures.

    Returns:
        A RoundtripResult with one outcome per participating case.

    Raises:
        BenchmarkValidationError: If the manifest cannot be read or validated.
    """
    try:
        raw_manifest = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BenchmarkValidationError([f"cannot read manifest: {exc}"]) from exc
    raw = YAML(typ="safe").load(raw_manifest)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if not isinstance(raw, dict):
        raise BenchmarkValidationError(["benchmark manifest must contain a YAML mapping"])
    try:
        manifest = BenchmarkManifest.model_validate(raw)
    except ValueError as exc:
        raise BenchmarkValidationError([str(exc)]) from exc
    pack = load_policy_pack(pack_path, corpus_root)
    fixable = _fixable_policy_ids(pack)

    result = RoundtripResult()
    for case in manifest.cases:
        if case.label != "violation" or not case.expected_applicable:
            continue
        if case.policy_id not in fixable:
            continue
        result.total_cases += 1
        fixture = corpus_root / case.fixture
        outcome = _run_case(case.id, case.policy_id, fixture, pack_path)
        result.cases.append(outcome)
    return result
