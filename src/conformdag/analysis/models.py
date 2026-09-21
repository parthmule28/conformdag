"""Typed source records produced by non-executing analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class ParseIssueCode(StrEnum):
    """Stable categories for source-discovery and parsing failures."""

    SYMLINK_EXCLUDED = "SYMLINK_EXCLUDED"
    EXTERNAL_SYMLINK_EXCLUDED = "EXTERNAL_SYMLINK_EXCLUDED"
    BROKEN_SYMLINK_EXCLUDED = "BROKEN_SYMLINK_EXCLUDED"
    SYMLINK_RESOLUTION_ERROR = "SYMLINK_RESOLUTION_ERROR"
    READ_ERROR = "READ_ERROR"
    INVALID_SOURCE = "INVALID_SOURCE"


class ValueState(StrEnum):
    """Resolution states for configuration values found in source."""

    ABSENT = "ABSENT"
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class SourceFile:
    """A selected source file and its immutable input digest."""

    path: Path
    relative_path: str
    content: str
    content_hash: str


@dataclass(frozen=True)
class ParseIssue:
    path: str
    message: str
    line: int | None = None
    code: ParseIssueCode = ParseIssueCode.INVALID_SOURCE


@dataclass(frozen=True)
class StaticValue:
    """A statically resolved value, an explicit null, or an unresolved expression."""

    state: ValueState
    value: object | None = None


@dataclass(frozen=True)
class ImportRecord:
    module: str
    alias: str | None
    line: int


@dataclass(frozen=True)
class CallRecord:
    qualified_name: str
    line: int
    column: int
    module_scope: bool
    uncertain: bool = False


def _empty_defaults() -> dict[str, object]:
    return {}


@dataclass
class DagRecord:
    line: int
    owner: str | None
    owner_source: str | None
    tags: tuple[str, ...]
    variable_name: str | None = None
    defaults: dict[str, object] = field(default_factory=_empty_defaults)
    unresolved_defaults: tuple[str, ...] = ()
    start_date: tuple[int, int, int] | None = None
    start_date_tz: bool | None = None
    catchup: bool | None = None
    schedule: str | None = None
    max_active_runs: int | None = None
    factory_function: str | None = None


@dataclass
class TaskRecord:
    line: int
    qualified_name: str
    task_id: str | None
    dag_name: str | None
    values: dict[str, object]
    taskflow: bool = False
    dag_line: int | None = None
    unresolved_kwargs: tuple[str, ...] = ()


def _empty_secrets() -> list[SecretAssignment]:
    return []


def _empty_constants() -> list[ConstantAssignment]:
    return []


def _empty_dynamic_loops() -> list[int]:
    return []


@dataclass(frozen=True)
class ConstantAssignment:
    """A module-scope constant assignment: name, value, and line."""

    line: int
    name: str
    value: object


@dataclass(frozen=True)
class SecretAssignment:
    """A module-scope assignment whose name looks like a credential holder."""

    line: int
    name: str


def secret_like(name: str) -> bool:
    lowered = name.lower()
    return any(
        marker in lowered for marker in ("password", "passwd", "token", "secret", "api_key", "apikey", "credential")
    )


def _empty_imports() -> list[ImportRecord]:
    return []


def _empty_calls() -> list[CallRecord]:
    return []


def _empty_dags() -> list[DagRecord]:
    return []


def _empty_tasks() -> list[TaskRecord]:
    return []


def _empty_assignments() -> dict[str, object]:
    return {}


def _empty_unresolved_assignments() -> dict[str, tuple[str, ...]]:
    return {}


@dataclass
class SourceModel:
    source: SourceFile
    imports: list[ImportRecord] = field(default_factory=_empty_imports)
    calls: list[CallRecord] = field(default_factory=_empty_calls)
    dags: list[DagRecord] = field(default_factory=_empty_dags)
    tasks: list[TaskRecord] = field(default_factory=_empty_tasks)
    assignments: dict[str, object] = field(default_factory=_empty_assignments)
    unresolved_assignments: dict[str, tuple[str, ...]] = field(default_factory=_empty_unresolved_assignments)
    constants: list[ConstantAssignment] = field(default_factory=_empty_constants)
    secret_assignments: list[SecretAssignment] = field(default_factory=_empty_secrets)
    dynamic_dag_lines: list[int] = field(default_factory=_empty_dynamic_loops)


def _preserve_legacy_pickle_modules() -> None:
    for cache_model in (
        ParseIssueCode,
        ValueState,
        SourceFile,
        ParseIssue,
        StaticValue,
        ImportRecord,
        CallRecord,
        DagRecord,
        TaskRecord,
        ConstantAssignment,
        SecretAssignment,
        SourceModel,
    ):
        cache_model.__module__ = "conformdag.analysis"


_preserve_legacy_pickle_modules()
