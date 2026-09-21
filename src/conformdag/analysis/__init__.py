"""Public compatibility facade for source discovery and structural analysis."""

from conformdag.analysis.airflow import analyze_source, datetime_parts, iter_module_scope_calls
from conformdag.analysis.cache import ParseCache
from conformdag.analysis.discovery import (
    DEFAULT_EXCLUDES,
    NON_FATAL_DISCOVERY_ISSUES,
    discover_python_files,
    matches_exclude,
)
from conformdag.analysis.models import (
    CallRecord,
    ConstantAssignment,
    DagRecord,
    ImportRecord,
    ParseIssue,
    ParseIssueCode,
    SecretAssignment,
    SourceFile,
    SourceModel,
    StaticValue,
    TaskRecord,
    ValueState,
    secret_like,
)

__all__ = [
    "DEFAULT_EXCLUDES",
    "ParseIssueCode",
    "ValueState",
    "NON_FATAL_DISCOVERY_ISSUES",
    "SourceFile",
    "ParseIssue",
    "StaticValue",
    "ImportRecord",
    "CallRecord",
    "DagRecord",
    "TaskRecord",
    "ConstantAssignment",
    "SecretAssignment",
    "secret_like",
    "SourceModel",
    "matches_exclude",
    "discover_python_files",
    "datetime_parts",
    "analyze_source",
    "ParseCache",
    "iter_module_scope_calls",
]
