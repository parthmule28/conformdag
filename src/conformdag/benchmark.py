"""Versioned benchmark manifest and fixture verification primitives."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field
from ruamel.yaml import YAML

from conformdag.models import ConformModel, FindingStatus


class BenchmarkValidationError(ValueError):
    """Raised when a benchmark manifest or fixture cannot be trusted."""

    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        super().__init__("; ".join(issues))


class BenchmarkLicense(ConformModel):
    name: str
    url: str | None = None
    attribution: str | None = None


class BenchmarkExpectedLocation(ConformModel):
    file: str | None = None
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)


class BenchmarkCase(ConformModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]+$")
    fixture: Path
    fixture_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    policy_id: str
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
    cases: list[BenchmarkCase] = Field(min_length=1)


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
    for case in manifest.cases:
        if case.id in case_ids:
            issues.append(f"duplicate benchmark case ID: {case.id}")
        case_ids.add(case.id)
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
