"""C22 legacy contract characterization for the pre-move semantic modules.

These tests are intentionally written against the public import paths that
existed before the semantic package decomposition. They must keep passing
unchanged after the move.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import pickle
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest

import conformdag.semantic as legacy_semantic
import conformdag.semantic_evaluator as legacy_evaluator
from conformdag.models import (
    Confidence,
    EnforcementConfig,
    EnforcementType,
    Policy,
    SemanticAuditEvidence,
    SemanticRequest,
    SemanticResponse,
    Severity,
)
from conformdag.policy import load_policy_pack

FIXTURES = Path(__file__).parent / "fixtures"

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


def _star_import(module_name: str) -> list[str]:
    namespace: dict[str, Any] = {}
    exec(f"from {module_name} import *", namespace)  # noqa: S102 - explicit contract check
    return [name for name in namespace if not name.startswith("__")]


def _request(evidence: str = "safe evidence") -> SemanticRequest:
    return SemanticRequest(
        policy_id="AIR-SEM-001",
        prompt_version="3",
        context_hash="context-hash",
        system_prompt="Return only the requested JSON decision.",
        evidence=evidence,
    )


def _semantic_policies() -> list[Policy]:
    pack = load_policy_pack(Path("policies/pack.yaml"), Path.cwd())
    return [policy for policy in pack.policies if policy.id.startswith("AIR-SEM-")]


def test_legacy_semantic_wildcard_bindings_and_order_are_frozen() -> None:
    assert _star_import("conformdag.semantic") == SEMANTIC_WILDCARD


def test_legacy_semantic_evaluator_wildcard_bindings_and_order_are_frozen() -> None:
    assert _star_import("conformdag.semantic_evaluator") == EVALUATOR_WILDCARD


def test_legacy_semantic_public_callable_signatures_are_stable() -> None:
    assert list(inspect.signature(legacy_semantic.build_context).parameters) == [
        "policy_text",
        "source_slices",
        "runtime_observations",
        "max_input_tokens",
        "secret_patterns",
    ]
    build_defaults = inspect.signature(legacy_semantic.build_context).parameters
    assert build_defaults["max_input_tokens"].default == 32_000
    assert build_defaults["secret_patterns"].default is legacy_semantic.DEFAULT_SECRET_PATTERNS
    assert build_defaults["secret_patterns"].default is legacy_semantic.CREDENTIAL_PATTERNS

    provider_defaults = inspect.signature(legacy_semantic.OpenAICompatibleProvider).parameters
    assert provider_defaults["timeout_seconds"].default == 60.0
    assert provider_defaults["max_retries"].default == 2
    assert provider_defaults["native_structured_output"].default is False
    assert provider_defaults["client"].default is None

    assert list(inspect.signature(legacy_semantic.semantic_cache_key).parameters) == [
        "request",
        "model",
        "configuration",
    ]
    assert list(inspect.signature(legacy_semantic.CachedSemanticProvider).parameters) == [
        "provider",
        "cache",
        "model",
        "configuration",
    ]
    assert list(inspect.signature(legacy_evaluator.semantic_finding).parameters) == [
        "policy",
        "response",
        "context",
        "source_path",
    ]
    assert list(inspect.signature(legacy_evaluator.run_semantic_evaluation).parameters) == [
        "policies",
        "context",
        "provider",
        "source_path",
        "max_concurrency",
        "temperature",
        "max_output_tokens",
    ]
    run_defaults = inspect.signature(legacy_evaluator.run_semantic_evaluation).parameters
    assert run_defaults["max_concurrency"].default == 4
    assert run_defaults["temperature"].default == 0.0
    assert run_defaults["max_output_tokens"].default == 4000
    assert list(inspect.signature(legacy_evaluator.evaluate_semantic_policies).parameters) == [
        "policies",
        "context",
        "provider",
        "source_path",
        "max_concurrency",
    ]


@pytest.mark.parametrize(
    ("fixture_name", "expected_type", "expected_owner"),
    [
        ("semantic_context.pkl", "SemanticContext", legacy_semantic.SemanticContext),
        ("prompt_template.pkl", "PromptTemplate", legacy_semantic.PromptTemplate),
        ("semantic_provider_error.pkl", "SemanticProviderError", legacy_semantic.SemanticProviderError),
        (
            "semantic_evaluation_result.pkl",
            "SemanticEvaluationResult",
            legacy_evaluator.SemanticEvaluationResult,
        ),
    ],
)
def test_legacy_pickle_globals_still_resolve(
    fixture_name: str,
    expected_type: str,
    expected_owner: type[Any],
) -> None:
    loaded = pickle.loads((FIXTURES / fixture_name).read_bytes())  # noqa: S301 - trusted local fixture

    assert type(loaded).__name__ == expected_type
    assert type(loaded) is expected_owner


def test_legacy_facade_identity_is_shared() -> None:
    assert legacy_evaluator.SemanticContext is legacy_semantic.SemanticContext
    assert legacy_evaluator.DEFAULT_PROMPT_TEMPLATE is legacy_semantic.DEFAULT_PROMPT_TEMPLATE
    assert legacy_evaluator.SemanticProviderError is legacy_semantic.SemanticProviderError
    assert legacy_evaluator.redact_text is legacy_semantic.redact_text


def test_legacy_prompt_bytes_versions_and_hashes_are_frozen() -> None:
    assert legacy_semantic.DEFAULT_PROMPT_TEMPLATE.version == "3"
    assert legacy_semantic.DEFAULT_PROMPT_TEMPLATE.prompt_hash == (
        "cf231a53699dd12d8ec0dd603cade486f250a81f04e6e3c339b36bc8ea56cd39"
    )
    assert (
        legacy_semantic.DEFAULT_PROMPT_TEMPLATE.prompt_hash
        == hashlib.sha256(legacy_semantic.DEFAULT_PROMPT_TEMPLATE.system_prompt.encode("utf-8")).hexdigest()
    )
    assert legacy_semantic.DEFAULT_PROMPT_TEMPLATE.system_prompt.startswith(
        "You are the semantic evaluator inside ConformDAG"
    )
    assert legacy_semantic.DEFAULT_PROMPT_TEMPLATE.system_prompt.endswith("Policy:\n{{ policy }}")
    assert legacy_semantic.GENERIC_REVIEWER_PROMPT.version == "1"
    assert legacy_semantic.GENERIC_REVIEWER_PROMPT.prompt_hash == (
        "855beca426219accdece1084d69bcf41293d2bb41ce546efc3d4fbbf1ad93c51"
    )
    rendered = legacy_semantic.DEFAULT_PROMPT_TEMPLATE.render("POLICY-BODY")
    assert "POLICY-BODY" in rendered
    assert "{{ policy }}" not in rendered


def test_legacy_context_selection_redaction_and_hash_are_frozen() -> None:
    context = legacy_semantic.build_context(
        "policy text",
        {"b.py": "token='second'", "a.py": "password='first'", "c.py": "x" * 100},
        runtime_observations=("credential=runtime-secret",),
        max_input_tokens=30,
    )

    assert context.text == (
        "[POLICY]\npolicy text\n\n[SOURCE a.py]\npassword='[REDACTED]'\n\n[SOURCE b.py]\ntoken='[REDACTED]'"
    )
    assert context.context_hash == "9fdb2650da3272ff4b292227962131dd8cfe06bc9bdcdf601f34aa2f6023ca1c"
    assert context.included_files == ("a.py", "b.py")
    assert context.omitted_files == ("c.py", "<runtime-observations>")
    assert "runtime-secret" not in context.text

    additive = legacy_semantic.build_context(
        "policy",
        {"dag.py": "vault_marker=c15-test-custom-value\ncredential=c15-test-generic-value"},
        secret_patterns=(r"vault_marker=[A-Za-z0-9_-]+",),
    )
    assert additive.text == "[POLICY]\npolicy\n\n[SOURCE dag.py]\n[REDACTED]\ncredential=[REDACTED]"


def test_legacy_cache_key_and_strict_schema_are_frozen() -> None:
    request = _request()
    strict = legacy_semantic.strict_semantic_response_schema()

    assert legacy_semantic.semantic_cache_key(request, "test-model", {"temperature": 0.0}) == (
        "ee1190cb91cda37404d69d63a6ef7345729cfc3625ee6d6c54a4fecb86605237"
    )
    assert (
        hashlib.sha256(json.dumps(strict, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        == "e6d0da08f2e54624a3279db1940e66902f17c614d910d5fb78a7d2b1672553f6"
    )
    assert set(strict["properties"]) == {
        "status",
        "evidence",
        "explanation",
        "remediation",
        "confidence",
        "audit_evidence",
    }
    assert strict["additionalProperties"] is False
    assert set(strict["required"]) == set(strict["properties"])


def test_legacy_provider_retries_transient_failures_and_rejects_model_mismatch() -> None:
    calls = 0

    def transient_handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, request=request)
        response = SemanticResponse(
            status="PASS",
            evidence="bounded",
            explanation="safe",
            confidence=Confidence.HIGH,
        )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": response.model_dump_json()}}]},
            request=request,
        )

    provider = legacy_semantic.OpenAICompatibleProvider(
        "https://model.example/v1",
        "test-model",
        "secret-key",
        max_retries=1,
        client=httpx.Client(transport=httpx.MockTransport(transient_handler)),
    )
    assert provider.evaluate(_request()).status == "PASS"
    assert calls == 2

    mismatch = legacy_semantic.OpenAICompatibleProvider(
        "https://model.example/v1",
        "test-model",
        "secret-key",
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "model": "other-model",
                        "choices": [
                            {
                                "message": {
                                    "content": SemanticResponse(
                                        status="PASS",
                                        evidence="bounded",
                                        explanation="safe",
                                        confidence=Confidence.HIGH,
                                    ).model_dump_json()
                                }
                            }
                        ],
                    },
                    request=request,
                )
            )
        ),
    )
    with pytest.raises(legacy_semantic.SemanticProviderError, match="served model"):
        mismatch.evaluate(_request())


def test_legacy_evaluator_fingerprint_and_ordering_are_frozen() -> None:
    policy = Policy.model_construct(
        id="C19-SEM-001",
        version="3.2.1",
        severity=Severity.MEDIUM,
        safe_path="Review the semantic fixture.",
        enforcement=EnforcementConfig(type=EnforcementType.SEMANTIC, blocking=True),
    )
    response = SemanticResponse(
        status="FAIL",
        evidence="same provider evidence",
        explanation="same provider explanation",
        remediation="same remediation",
        confidence=Confidence.HIGH,
        audit_evidence=[
            SemanticAuditEvidence(
                criterion="retry-safety",
                source_type="source",
                location="dags/sample.py",
                excerpt="bounded source citation",
                unresolved=False,
            )
        ],
    )
    context = legacy_semantic.SemanticContext(
        "[SOURCE dags/sample.py]\noperation()",
        "context-hash-one",
        ("dags/sample.py",),
        (),
    )

    finding = legacy_evaluator.semantic_finding(policy, response, context, Path("dags/sample.py"))

    assert finding.fingerprint == "a647f8e06112394f51a3c2f37f7bd567771ee61ac7a406ba74e2d7b8c43cb38b"


class _Provider:
    def evaluate_many(
        self,
        requests: Sequence[SemanticRequest],
        max_concurrency: int = 4,
    ) -> list[SemanticResponse]:
        return [
            SemanticResponse(
                status="PASS",
                evidence=f"evidence-{request.policy_id}",
                explanation="supported",
                confidence=Confidence.HIGH,
            )
            for request in requests
        ]


def test_legacy_evaluator_ordering_and_monkeypatch_targets_are_stable() -> None:
    context = legacy_semantic.SemanticContext("[SOURCE dag.py]\nlogging.info('safe')", "hash", ("dag.py",), ())

    findings = legacy_evaluator.evaluate_semantic_policies(_semantic_policies(), context, _Provider())

    assert [finding.policy_id for finding in findings] == [
        "AIR-SEM-001",
        "AIR-SEM-002",
        "AIR-SEM-003",
        "AIR-SEM-004",
    ]

    import conformdag.scan as scan

    assert scan.run_semantic_evaluation is legacy_evaluator.run_semantic_evaluation
    assert scan.select_semantic_policies is legacy_evaluator.select_semantic_policies
