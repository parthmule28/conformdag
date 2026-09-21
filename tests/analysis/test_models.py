"""Tests for analysis model ownership and the public facade."""

from types import ModuleType

import conformdag.analysis as facade
from conformdag.analysis import airflow, cache, discovery, models

OWNERS: dict[str, ModuleType] = {
    "DEFAULT_EXCLUDES": discovery,
    "ParseIssueCode": models,
    "ValueState": models,
    "NON_FATAL_DISCOVERY_ISSUES": discovery,
    "SourceFile": models,
    "ParseIssue": models,
    "StaticValue": models,
    "ImportRecord": models,
    "CallRecord": models,
    "DagRecord": models,
    "TaskRecord": models,
    "ConstantAssignment": models,
    "SecretAssignment": models,
    "secret_like": models,
    "SourceModel": models,
    "matches_exclude": discovery,
    "discover_python_files": discovery,
    "datetime_parts": airflow,
    "analyze_source": airflow,
    "ParseCache": cache,
    "iter_module_scope_calls": airflow,
}


def test_facade_exports_direct_owner_objects() -> None:
    assert tuple(facade.__all__) == tuple(OWNERS)
    for name, owner in OWNERS.items():
        assert getattr(facade, name) is getattr(owner, name)
