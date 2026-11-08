"""C22 owner tests for versioned semantic prompts."""

from __future__ import annotations

import hashlib
import importlib

import conformdag.semantic as facade


def test_prompt_owner_module_owns_the_public_prompt_objects() -> None:
    owner = importlib.import_module("conformdag.semantic.prompts")

    assert owner.PromptTemplate is facade.PromptTemplate
    assert owner.DEFAULT_PROMPT_TEMPLATE is facade.DEFAULT_PROMPT_TEMPLATE
    assert owner.GENERIC_REVIEWER_PROMPT is facade.GENERIC_REVIEWER_PROMPT


def test_default_prompt_bytes_version_and_hash_are_unchanged() -> None:
    owner = importlib.import_module("conformdag.semantic.prompts")
    prompt = owner.DEFAULT_PROMPT_TEMPLATE

    assert prompt.version == "3"
    assert prompt.prompt_hash == "cf231a53699dd12d8ec0dd603cade486f250a81f04e6e3c339b36bc8ea56cd39"
    assert prompt.prompt_hash == hashlib.sha256(prompt.system_prompt.encode("utf-8")).hexdigest()
    assert prompt.system_prompt.startswith("You are the semantic evaluator inside ConformDAG")
    assert prompt.system_prompt.endswith("Policy:\n{{ policy }}")


def test_generic_reviewer_prompt_bytes_version_and_hash_are_unchanged() -> None:
    owner = importlib.import_module("conformdag.semantic.prompts")
    prompt = owner.GENERIC_REVIEWER_PROMPT

    assert prompt.version == "1"
    assert prompt.prompt_hash == "855beca426219accdece1084d69bcf41293d2bb41ce546efc3d4fbbf1ad93c51"
    assert prompt.system_prompt.startswith("You are the pinned generic ConformDAG reviewer baseline")
    assert prompt.system_prompt.endswith("Policy:\n{{ policy }}")


def test_prompt_rendering_is_unchanged() -> None:
    owner = importlib.import_module("conformdag.semantic.prompts")

    rendered = owner.DEFAULT_PROMPT_TEMPLATE.render("POLICY-BODY")

    assert "POLICY-BODY" in rendered
    assert "{{ policy }}" not in rendered
    assert rendered.count("POLICY-BODY") == 1
    assert owner.PromptTemplate("v", "prefix {{ policy }} suffix").render("body") == "prefix body suffix"
