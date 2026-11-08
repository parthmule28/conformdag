"""C22 facade, dependency-direction and import-order contracts."""

from __future__ import annotations

import ast
import importlib
import os
import subprocess
import sys
from pathlib import Path

import conformdag.semantic as facade
import conformdag.semantic_evaluator as legacy_shim

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = REPO_ROOT / "src" / "conformdag"
SEMANTIC_DIR = PACKAGE_DIR / "semantic"
OWNER_MODULES = ("context", "prompts", "provider", "cache", "evaluator")

SEMANTIC_WILDCARD = [
    "annotations",
    "fcntl",
    "hashlib",
    "json",
    "logging",
    "os",
    "re",
    "tempfile",
    "Iterable",
    "Iterator",
    "Mapping",
    "Sequence",
    "ThreadPoolExecutor",
    "contextmanager",
    "suppress",
    "deepcopy",
    "dataclass",
    "Path",
    "monotonic",
    "sleep",
    "Any",
    "cast",
    "httpx",
    "SemanticRequest",
    "SemanticResponse",
    "CREDENTIAL_PATTERNS",
    "redact_credentials",
    "LOGGER",
    "SemanticProviderError",
    "strict_semantic_response_schema",
    "DEFAULT_SECRET_PATTERNS",
    "SemanticContext",
    "PromptTemplate",
    "DEFAULT_PROMPT_TEMPLATE",
    "GENERIC_REVIEWER_PROMPT",
    "redact_text",
    "build_context",
    "OpenAICompatibleProvider",
    "semantic_cache_key",
    "SemanticCache",
    "CachedSemanticProvider",
]

EVALUATOR_WILDCARD = [
    "annotations",
    "hashlib",
    "json",
    "re",
    "Sequence",
    "dataclass",
    "Path",
    "Protocol",
    "EnforcementType",
    "Finding",
    "FindingEvidence",
    "FindingLocation",
    "FindingStatus",
    "Policy",
    "SemanticAuditEvidence",
    "SemanticRequest",
    "SemanticResponse",
    "policy_contract_hash",
    "policy_enforcement_hash",
    "redact_credentials",
    "redact_evidence",
    "DEFAULT_PROMPT_TEMPLATE",
    "SemanticContext",
    "SemanticProviderError",
    "redact_text",
    "POLICY_INSTRUCTIONS",
    "SemanticProvider",
    "SemanticEvaluationResult",
    "select_semantic_policies",
    "build_semantic_request",
    "semantic_finding",
    "run_semantic_evaluation",
    "evaluate_semantic_policies",
]


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            modules.append(node.module)
    return modules


def test_semantic_facade_contains_only_explicit_exports() -> None:
    tree = ast.parse((SEMANTIC_DIR / "__init__.py").read_text(encoding="utf-8"))

    implementations = [
        node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    assignments = [node for node in tree.body if isinstance(node, (ast.Assign, ast.AnnAssign))]

    assert implementations == []
    assert len(assignments) == 1
    assignment = assignments[0]
    assert isinstance(assignment, ast.Assign)
    assert len(assignment.targets) == 1
    assert isinstance(assignment.targets[0], ast.Name)
    assert assignment.targets[0].id == "__all__"


def test_facades_preserve_the_frozen_wildcard_bindings() -> None:
    assert facade.__all__ == SEMANTIC_WILDCARD
    assert legacy_shim.__all__ == EVALUATOR_WILDCARD


def test_owner_modules_have_no_facade_or_shim_back_edges() -> None:
    for module in OWNER_MODULES:
        imported = _imported_modules(SEMANTIC_DIR / f"{module}.py")
        assert "conformdag.semantic" not in imported
        assert "conformdag.semantic_evaluator" not in imported

    shim_imports = _imported_modules(PACKAGE_DIR / "semantic_evaluator.py")
    assert "conformdag.semantic" not in shim_imports
    assert "conformdag.semantic.evaluator" in shim_imports


def test_semantic_core_does_not_import_transport_or_platform_adapters() -> None:
    forbidden = (
        "conformdag.application",
        "conformdag.platform",
        "conformdag.cli",
        "conformdag.agent",
        "fastapi",
        "sqlalchemy",
        "typer",
    )
    for module in OWNER_MODULES:
        imported = _imported_modules(SEMANTIC_DIR / f"{module}.py")
        assert not [name for name in imported if name.startswith(forbidden)]
        if module != "provider":
            assert "httpx" not in imported


def test_both_legacy_paths_and_owners_import_in_any_order() -> None:
    scripts = [
        (
            "conformdag.semantic.cache",
            "conformdag.semantic.evaluator",
            "conformdag.semantic",
            "conformdag.semantic_evaluator",
        ),
        (
            "conformdag.semantic_evaluator",
            "conformdag.semantic.provider",
            "conformdag.semantic.context",
            "conformdag.semantic.prompts",
            "conformdag.semantic.cache",
            "conformdag.semantic",
        ),
        ("conformdag.semantic", "conformdag.semantic.evaluator", "conformdag.semantic_evaluator"),
    ]
    body = """
import importlib
for name in {order!r}:
    importlib.import_module(name)
import conformdag.semantic as facade
import conformdag.semantic_evaluator as shim
import conformdag.semantic.context as context
import conformdag.semantic.evaluator as evaluator
import conformdag.semantic.provider as provider
assert facade.SemanticContext is context.SemanticContext
assert shim.semantic_finding is evaluator.semantic_finding
assert facade.SemanticProviderError is provider.SemanticProviderError
assert shim.SemanticEvaluationResult is evaluator.SemanticEvaluationResult
print("import-order-ok")
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    for order in scripts:
        completed = subprocess.run(
            [sys.executable, "-c", body.format(order=order)],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert "import-order-ok" in completed.stdout


def test_scan_semantic_provider_remains_independent() -> None:
    import conformdag.scan as scan

    evaluator = importlib.import_module("conformdag.semantic.evaluator")

    assert scan.SemanticProvider is not evaluator.SemanticProvider
    assert scan.SemanticProvider.__module__ == "conformdag.scan"
