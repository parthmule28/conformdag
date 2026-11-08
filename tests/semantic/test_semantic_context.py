"""C22 owner tests for semantic context selection and canonical redaction."""

from __future__ import annotations

import hashlib
import importlib

import pytest

import conformdag.semantic as facade


def test_context_owner_module_owns_the_public_context_objects() -> None:
    owner = importlib.import_module("conformdag.semantic.context")

    assert owner.SemanticContext is facade.SemanticContext
    assert owner.DEFAULT_SECRET_PATTERNS is facade.DEFAULT_SECRET_PATTERNS
    assert owner.redact_text is facade.redact_text
    assert owner.build_context is facade.build_context


def test_context_selection_is_sorted_budgeted_and_hashed() -> None:
    owner = importlib.import_module("conformdag.semantic.context")

    context = owner.build_context(
        "policy",
        {"b.py": "token='second'", "a.py": "password='first'", "c.py": "x" * 100},
        max_input_tokens=30,
    )

    assert context.included_files == ("a.py", "b.py")
    assert context.omitted_files == ("c.py",)
    assert context.text.index("[SOURCE a.py]") < context.text.index("[SOURCE b.py]")
    assert context.context_hash == hashlib.sha256(context.text.encode("utf-8")).hexdigest()


def test_runtime_observations_are_optional_and_budgeted() -> None:
    owner = importlib.import_module("conformdag.semantic.context")

    without_runtime = owner.build_context("policy", {"dag.py": "safe"})
    with_runtime = owner.build_context("policy", {"dag.py": "safe"}, runtime_observations=("observed",))
    oversized = owner.build_context(
        "policy", {"dag.py": "safe"}, runtime_observations=("x" * 1000,), max_input_tokens=5
    )

    assert "[RUNTIME]" not in without_runtime.text
    assert "[RUNTIME]\nobserved" in with_runtime.text
    assert "<runtime-observations>" in oversized.omitted_files
    assert "[RUNTIME]" not in oversized.text


def test_canonical_redaction_precedes_additive_custom_patterns() -> None:
    owner = importlib.import_module("conformdag.semantic.context")
    source = "vault_marker=c15-test-custom; credential=c15-test-generic"

    redacted = owner.redact_text(source, [r"vault_marker=[A-Za-z0-9_-]+"])

    assert redacted == "[REDACTED]; credential=[REDACTED]"
    assert "c15-test-custom" not in redacted
    assert "c15-test-generic" not in redacted


def test_custom_pattern_cannot_disable_canonical_masking() -> None:
    owner = importlib.import_module("conformdag.semantic.context")
    secret = "c15-test-bypass"
    context = owner.build_context("safe", {"dag.py": f"password={secret}"}, secret_patterns=[r"password="])

    assert secret not in context.text
    assert "[REDACTED]" in context.text


@pytest.mark.parametrize("secret", ["policy-secret", "source-secret", "runtime-secret"])
def test_no_raw_secret_reaches_context(secret: str) -> None:
    owner = importlib.import_module("conformdag.semantic.context")

    context = owner.build_context(
        f"credential={secret}-policy",
        {"dag.py": f"credential={secret}-source"},
        runtime_observations=(f"credential={secret}-runtime",),
    )

    assert f"{secret}-policy" not in context.text
    assert f"{secret}-source" not in context.text
    assert f"{secret}-runtime" not in context.text
