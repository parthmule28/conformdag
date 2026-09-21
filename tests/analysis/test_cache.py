"""Tests for direct parse-cache ownership and pickle compatibility."""

from __future__ import annotations

import pickle
import pickletools
from os import stat_result
from pathlib import Path

import pytest

from conformdag.analysis.airflow import analyze_source
from conformdag.analysis.cache import ParseCache
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
)


def _source_file(source: str) -> SourceFile:
    return SourceFile(
        path=Path("dags/x.py"),
        relative_path="dags/x.py",
        content=source,
        content_hash="e" * 64,
    )


def _model(source: str = "value = 1\n") -> SourceModel:
    model, issue = analyze_source(_source_file(source))
    assert issue is None
    assert model is not None
    return model


def test_empty_entry_is_a_miss(tmp_path: Path) -> None:
    cache = ParseCache(tmp_path / "cache")
    cache.directory.mkdir()
    (cache.directory / "abc.pkl").write_bytes(b"")

    assert cache.get("abc") is None


def test_corrupt_entry_is_a_miss(tmp_path: Path) -> None:
    cache = ParseCache(tmp_path / "cache")
    cache.directory.mkdir()
    (cache.directory / "abc.pkl").write_bytes(b"not a pickle")

    assert cache.get("abc") is None


def test_new_entries_keep_historical_pickle_module_path(tmp_path: Path) -> None:
    cache = ParseCache(tmp_path / "cache")
    cache.put("abc", _model())

    payload = (cache.directory / "abc.pkl").read_bytes()
    strings = [argument for opcode, argument, _ in pickletools.genops(payload) if isinstance(argument, str)]

    assert "conformdag.analysis" in strings
    assert "conformdag.analysis.models" not in strings


def test_legacy_analysis_pickle_entry_is_readable(tmp_path: Path) -> None:
    cache = ParseCache(tmp_path / "cache")
    model = _model("value = 2\n")
    cache.directory.mkdir()
    cache_models = (
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
    )
    original_modules = {model_type: model_type.__module__ for model_type in cache_models}
    try:
        for model_type in cache_models:
            model_type.__module__ = "conformdag.analysis"
        payload = pickle.dumps(model)
    finally:
        for model_type, module_name in original_modules.items():
            model_type.__module__ = module_name
    (cache.directory / "legacy.pkl").write_bytes(payload)

    cached = cache.get("legacy")

    assert isinstance(cached, SourceModel)
    assert cached.source.content == "value = 2\n"


def test_atomic_replace_failure_preserves_last_good_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = ParseCache(tmp_path / "cache")
    first = _model("value = 1\n")
    second = _model("value = 2\n")
    cache.put("abc", first)

    original_replace = Path.replace
    replacements: list[Path] = []

    def fail_replace(self: Path, target: Path) -> Path:
        replacements.append(self)
        raise OSError("simulated atomic replace failure")

    monkeypatch.setattr(Path, "replace", fail_replace)
    cache.put("abc", second)
    monkeypatch.setattr(Path, "replace", original_replace)

    cached = cache.get("abc")
    assert replacements
    assert cached is not None
    assert cached.source.content == "value = 1\n"
    assert not list(cache.directory.glob(".*.tmp"))


def test_prune_ignores_entries_removed_by_a_racing_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = ParseCache(tmp_path / "cache")
    model = _model()
    for index in range(499):
        cache.put(f"entry-{index}", model)

    original_stat = Path.stat

    def missing_stat(path: Path, *, follow_symlinks: bool = True) -> stat_result:
        if path.suffix == ".pkl":
            raise FileNotFoundError("entry disappeared during prune")
        return original_stat(path, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", missing_stat)
    cache.put("abc", model)

    assert cache.get("abc") is not None
