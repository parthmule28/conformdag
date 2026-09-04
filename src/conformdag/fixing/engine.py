"""Verify-by-rescan fix orchestration over an isolated patched copy."""

from __future__ import annotations

import io
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml import YAML

from conformdag.analysis import discover_python_files
from conformdag.config import load_project_config
from conformdag.fixing.codemods import (
    AUTOFIX_KINDS,
    PROPOSED_ONLY_KINDS,
    generate_spans,
    timedelta_import_span,
)
from conformdag.fixing.specs import EditSpan, apply_spans, render_unified_diff
from conformdag.models import (
    EnforcementType,
    Finding,
    FindingStatus,
    ProjectConfig,
    RemediationAction,
    ScanReport,
)
from conformdag.policy import resolve_configured_policy_pack, select_policy_pack
from conformdag.scan import scan_repository

MAX_FIX_ITERATIONS = 3


def _empty_patches() -> list[FilePatch]:
    return []


def _empty_strings() -> list[str]:
    return []


def _empty_proposed_moves() -> list[ProposedMove]:
    return []


def _empty_not_fixable() -> list[NotFixable]:
    return []


def _empty_residuals() -> list[ResidualFailure]:
    return []


@dataclass(frozen=True)
class FilePatch:
    """A verified patch for one file, with its deterministic unified diff."""

    path: str
    original: str
    updated: str
    diff: str


@dataclass(frozen=True)
class ProposedMove:
    """A proposed-only structural move diff that is never applied."""

    path: str
    diff: str
    policy_id: str


@dataclass(frozen=True)
class NotFixable:
    """A finding the fixability matrix marks as manual."""

    policy_id: str
    path: str
    fix_kind: str
    reason: str


@dataclass(frozen=True)
class ResidualFailure:
    """A fixable finding whose patch failed generation or verification."""

    policy_id: str
    path: str
    fix_kind: str
    iterations: int


@dataclass
class FixOutcome:
    """Complete fix-engine result for one run."""

    apply: bool
    initial_report: ScanReport
    patches: list[FilePatch] = field(default_factory=_empty_patches)
    applied_files: list[str] = field(default_factory=_empty_strings)
    proposed_moves: list[ProposedMove] = field(default_factory=_empty_proposed_moves)
    not_fixable: list[NotFixable] = field(default_factory=_empty_not_fixable)
    residuals: list[ResidualFailure] = field(default_factory=_empty_residuals)
    verification_report: ScanReport | None = None

    @property
    def clean(self) -> bool:
        return not self.residuals


def _is_autofix_target(finding: Finding) -> bool:
    payload = finding.fix
    return (
        finding.status is FindingStatus.FAIL
        and not finding.suppressed
        and finding.enforcement is EnforcementType.DETERMINISTIC
        and payload is not None
        and payload.action is not RemediationAction.MANUAL
        and payload.fix_kind in AUTOFIX_KINDS
    )


def _autofix_targets_by_file(report: ScanReport) -> dict[str, list[Finding]]:
    targets: dict[str, list[Finding]] = {}
    for finding in report.findings:
        if finding.location.file is None or not _is_autofix_target(finding):
            continue
        targets.setdefault(finding.location.file.as_posix(), []).append(finding)
    return targets


def run_fix(
    repository_root: Path,
    policy_pack: Path | None = None,
    *,
    apply: bool = False,
    max_iterations: int = MAX_FIX_ITERATIONS,
) -> FixOutcome:
    """Scan, generate deterministic patches, verify by re-scan, and optionally apply.

    The engine never mutates the repository during verification: patches are
    applied to an isolated temporary copy that is re-scanned with the same scan
    engine until clean or ``max_iterations`` is reached. Only verified patches
    are returned, and only verified patches are written when ``apply`` is set.

    Args:
        repository_root: Root of the repository to scan and fix.
        policy_pack: Explicit policy pack path or bundled alias; defaults to the
            project configuration's pack.
        apply: Write verified patches to the real sources when True.
        max_iterations: Upper bound on patch-and-rescan refinement rounds.

    Returns:
        A complete FixOutcome with verified patches, proposed-only moves,
        not-fixable findings, and residual failures.
    """
    root = repository_root.resolve()
    config = load_project_config(root / "conformdag.yaml")
    pack_path = resolve_configured_policy_pack(
        policy_pack if policy_pack is not None else config.scan.policy_pack,
        scan_root=root,
        from_cli=policy_pack is not None,
    )
    _ = select_policy_pack(pack_path, root)

    files, _ = discover_python_files(
        root,
        config.scan.include,
        config.scan.exclude,
        config.scan.follow_internal_symlinks,
    )
    original = {source.relative_path: source.content for source in files}
    initial_report = scan_repository(root, pack_path)

    outcome = FixOutcome(apply=apply, initial_report=initial_report)
    _record_not_fixable(outcome, initial_report)
    _record_proposed_moves(outcome, original)

    targets = _autofix_targets_by_file(initial_report)
    if targets:
        verified, residuals, verification = _verify_patches(config, pack_path, original, initial_report, max_iterations)
        outcome.residuals = residuals
        outcome.verification_report = verification
        _finalize_patches(outcome, original, verified)
        if apply and verified:
            outcome.applied_files = _apply_verified(root, verified)
    return outcome


def _patch_candidates(
    original: dict[str, str],
    patched: dict[str, str],
    open_targets: dict[str, list[Finding]],
    iteration: int,
) -> tuple[dict[str, str], list[ResidualFailure]]:
    """Generate patched content for every open target file from its current text."""
    candidates: dict[str, str] = {}
    residuals: list[ResidualFailure] = []
    for relative, findings in sorted(open_targets.items()):
        source = patched.get(relative, original.get(relative))
        if source is None:
            continue
        spans: list[EditSpan] = []
        needs_import = False
        for finding in findings:
            payload = finding.fix
            result = generate_spans(source, payload) if payload is not None else None
            if result is None:
                residuals.append(
                    ResidualFailure(
                        policy_id=finding.policy_id,
                        path=relative,
                        fix_kind=payload.fix_kind if payload else "unknown",
                        iterations=iteration,
                    )
                )
                continue
            finding_spans, import_needed = result
            spans.extend(finding_spans)
            needs_import = needs_import or import_needed
        if not spans:
            continue
        if needs_import:
            spans.append(timedelta_import_span(source))
        candidates[relative] = apply_spans(source, spans)
    return candidates, residuals


def _verify_patches(
    config: ProjectConfig,
    pack_path: Path,
    original: dict[str, str],
    initial_report: ScanReport,
    max_iterations: int,
) -> tuple[dict[str, str], list[ResidualFailure], ScanReport | None]:
    """Iteratively patch and re-scan an isolated copy, keeping only verified files."""
    patched: dict[str, str] = {}
    verified: dict[str, str] = {}
    residuals: list[ResidualFailure] = []
    latest: ScanReport | None = None

    for iteration in range(1, max_iterations + 1):
        open_targets = {
            relative: findings
            for relative, findings in _autofix_targets_by_file(latest or initial_report).items()
            if relative not in verified
        }
        candidates, generation_residuals = _patch_candidates(original, patched, open_targets, iteration)
        residuals.extend(generation_residuals)
        if not candidates:
            break
        patched.update(candidates)
        latest = _scan_patched_copy(config, pack_path, original, patched)
        clean_files = {relative for relative in candidates if relative not in _autofix_targets_by_file(latest)}
        verified.update((relative, patched[relative]) for relative in clean_files)
        if not set(candidates) - set(verified):
            break

    _record_unverified_residuals(patched, verified, latest, max_iterations, residuals)
    return verified, _dedup_residuals(residuals), latest


def _record_unverified_residuals(
    patched: dict[str, str],
    verified: dict[str, str],
    latest: ScanReport | None,
    max_iterations: int,
    residuals: list[ResidualFailure],
) -> None:
    if latest is None:
        return
    remaining = _autofix_targets_by_file(latest)
    for relative in sorted(set(patched) - set(verified)):
        for finding in remaining.get(relative, []):
            payload = finding.fix
            residuals.append(
                ResidualFailure(
                    policy_id=finding.policy_id,
                    path=relative,
                    fix_kind=payload.fix_kind if payload else "unknown",
                    iterations=max_iterations,
                )
            )


def _dedup_residuals(
    residuals: list[ResidualFailure],
) -> list[ResidualFailure]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[ResidualFailure] = []
    for item in residuals:
        identity = (item.policy_id, item.path, item.fix_kind)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(item)
    return unique


def _project_config_text(config: ProjectConfig) -> str:
    payload: dict[str, object] = {
        "config_version": "1",
        "scan": {
            "include": config.scan.include,
            "exclude": config.scan.exclude,
            "follow_internal_symlinks": config.scan.follow_internal_symlinks,
        },
    }
    if config.runtime.airflow_version is not None:
        payload["runtime"] = {"airflow_version": config.runtime.airflow_version.value}
    stream = io.StringIO()
    yaml = YAML()
    yaml.dump(payload, stream)  # pyright: ignore[reportUnknownMemberType]
    return stream.getvalue()


def _scan_patched_copy(
    config: ProjectConfig,
    pack_path: Path,
    original: dict[str, str],
    patched: dict[str, str],
) -> ScanReport:
    """Re-scan the isolated patched copy with the same single scan engine."""
    contents = {**original, **patched}
    with tempfile.TemporaryDirectory(prefix="conformdag-verify-") as temp:
        temp_root = Path(temp)
        (temp_root / "conformdag.yaml").write_text(_project_config_text(config), encoding="utf-8")
        for relative, content in contents.items():
            target = temp_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return scan_repository(temp_root, pack_path)


def _record_not_fixable(outcome: FixOutcome, report: ScanReport) -> None:
    for finding in report.findings:
        payload = finding.fix
        if (
            finding.status is not FindingStatus.FAIL
            or finding.suppressed
            or finding.enforcement is not EnforcementType.DETERMINISTIC
            or payload is None
            or payload.action is not RemediationAction.MANUAL
            or payload.fix_kind in PROPOSED_ONLY_KINDS
        ):
            continue
        outcome.not_fixable.append(
            NotFixable(
                policy_id=finding.policy_id,
                path=finding.location.file.as_posix() if finding.location.file else "",
                fix_kind=payload.fix_kind,
                reason=payload.hint or payload.action.value,
            )
        )


def _record_proposed_moves(outcome: FixOutcome, contents: dict[str, str]) -> None:
    for finding in outcome.initial_report.findings:
        payload = finding.fix
        relative = finding.location.file.as_posix() if finding.location.file else None
        if (
            finding.status is not FindingStatus.FAIL
            or finding.suppressed
            or payload is None
            or payload.fix_kind not in PROPOSED_ONLY_KINDS
            or payload.action is not RemediationAction.MOVE_STATEMENT
            or relative is None
            or relative not in contents
        ):
            continue
        result = generate_spans(contents[relative], payload)
        if result is None:
            outcome.not_fixable.append(
                NotFixable(
                    policy_id=finding.policy_id,
                    path=relative,
                    fix_kind=payload.fix_kind,
                    reason="no safe structural move could be proposed",
                )
            )
            continue
        spans, _ = result
        updated = apply_spans(contents[relative], spans)
        outcome.proposed_moves.append(
            ProposedMove(
                path=relative,
                diff=render_unified_diff(relative, contents[relative], updated),
                policy_id=finding.policy_id,
            )
        )


def _finalize_patches(
    outcome: FixOutcome,
    contents: dict[str, str],
    verified: dict[str, str],
) -> None:
    for relative in sorted(verified):
        if verified[relative] == contents.get(relative):
            continue
        outcome.patches.append(
            FilePatch(
                path=relative,
                original=contents[relative],
                updated=verified[relative],
                diff=render_unified_diff(relative, contents[relative], verified[relative]),
            )
        )


def _apply_verified(root: Path, verified: dict[str, str]) -> list[str]:
    for relative, content in verified.items():
        (root / relative).write_text(content, encoding="utf-8")
    return sorted(verified)
