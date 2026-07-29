"""Tests for the opt-in semantic provider boundary."""

import json
from pathlib import Path

import httpx

from conformdag.models import Confidence, SemanticRequest, SemanticResponse
from conformdag.semantic import (
    DEFAULT_PROMPT_TEMPLATE,
    OpenAICompatibleProvider,
    SemanticCache,
    build_context,
    redact_text,
    semantic_cache_key,
)


def _request(evidence: str = "safe evidence") -> SemanticRequest:
    return SemanticRequest(
        policy_id="AIR-SEM-001",
        prompt_version="1",
        context_hash="context-hash",
        system_prompt="Return only the requested JSON decision.",
        evidence=evidence,
    )


def test_context_is_redacted_bounded_and_deterministically_selected() -> None:
    context = build_context(
        "policy",
        {"b.py": "password='second'", "a.py": "token='first'", "c.py": "x" * 100},
        max_input_tokens=30,
    )

    assert "first" not in context.text
    assert "second" not in context.text
    assert context.included_files == ("a.py", "b.py")
    assert context.omitted_files == ("c.py",)
    assert len(context.context_hash) == 64


def test_provider_validates_structured_output_and_sends_untrusted_boundary() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        response = SemanticResponse(
            status="NEEDS_REVIEW",
            evidence="not enough evidence",
            explanation="abstain",
            confidence=Confidence.MEDIUM,
        )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": response.model_dump_json()}}]},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        "https://model.example/v1", "test-model", "secret-key", client=client
    )

    result = provider.evaluate(_request("password='do-not-send'"))

    assert result.status == "NEEDS_REVIEW"
    body = captured["body"]
    assert isinstance(body, dict)
    assert "tools" not in body
    assert "<untrusted-evidence>" in body["messages"][1]["content"]
    batch = provider.evaluate_many([_request("first"), _request("second")], max_concurrency=2)
    assert [item.status for item in batch] == ["NEEDS_REVIEW", "NEEDS_REVIEW"]


def test_cache_stores_only_normalized_response(tmp_path: Path) -> None:
    request = _request()
    key = semantic_cache_key(request, "test-model", {"temperature": 0.0})
    cache = SemanticCache(tmp_path / "semantic-cache.json")
    response = SemanticResponse(
        status="PASS",
        evidence="bounded evidence",
        explanation="safe",
        confidence=Confidence.HIGH,
    )

    cache.put(key, response)

    assert cache.get(key) == response
    stored = (tmp_path / "semantic-cache.json").read_text(encoding="utf-8")
    assert "system_prompt" not in stored
    assert "safe evidence" not in stored


def test_custom_secret_pattern_is_applied() -> None:
    assert redact_text("credential=abc", [r"credential=\w+"]) == "[REDACTED]"


def test_prompt_template_is_versioned_and_hashed() -> None:
    rendered = DEFAULT_PROMPT_TEMPLATE.render("AIR-SEM-001 invariant")

    assert DEFAULT_PROMPT_TEMPLATE.version == "1"
    assert len(DEFAULT_PROMPT_TEMPLATE.prompt_hash) == 64
    assert "AIR-SEM-001 invariant" in rendered
    assert "untrusted-evidence" in rendered
