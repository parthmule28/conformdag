# C22 — Decompose the Semantic Package

## Role and objective

You are the Build agent for C22. Split semantic context, prompts, provider transport, cache, and policy evaluator into a package that uses the central security redaction primitive and keeps semantic mode opt-in.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C15/C21.
- Full `src/conformdag/semantic.py`, `src/conformdag/semantic_evaluator.py`, `src/conformdag/scan.py`, and semantic imports.
- `src/conformdag/security/redaction.py`, `src/conformdag/models.py`, `src/conformdag/benchmark_semantic.py`, and `tests/test_semantic.py`/`test_semantic_evaluator.py`.

## Current ownership and resulting owner

`semantic.py` owns redaction, context, prompt templates, provider HTTP, cache keys/storage, and cached provider behavior; `semantic_evaluator.py` owns policy-facing evaluation. After this PR, `semantic/context.py`, `prompts.py`, `provider.py`, `cache.py`, and `evaluator.py` own those concerns, with `semantic/__init__.py` as a compatibility facade.

## Interfaces

Preserve `SemanticProviderError`, `SemanticContext`, `OpenAICompatibleProvider`, `SemanticCache`, `CachedSemanticProvider`, `build_context()`, `semantic_cache_key()`, and semantic evaluator public functions. Provider errors remain typed enough for scan/application handling.

## Expected files

- Create: `src/conformdag/semantic/` package modules and focused `tests/semantic/` modules if useful.
- Remove: old `semantic.py` and `semantic_evaluator.py` only after facade/import parity.
- Modify: scan/application/benchmark/agent imports and semantic tests.
- Do not change prompt content, cache identity, provider schema, or default disabled behavior.

## Test-first sequence

1. Add import-parity tests and preserve redaction/context/cache/provider/evaluator characterization cases.
2. Run semantic and scan tests before movement.
3. Move context/prompts/provider/cache/evaluator by responsibility and replace duplicated redaction imports.
4. Run provider failure/schema/model mismatch/cache privacy/concurrency tests.
5. Run `mise run check`, coverage, semantic benchmark checks, and privacy verification.

## Allowed changes

- Package movement, facade exports, typed provider error refinement where callers distinguish it, and imports/tests.

## Non-goals and prohibitions

- Do not enable semantic mode by default or expose tools to providers.
- Do not persist raw prompts/provider payloads/API keys.
- Do not introduce provider-specific logic into core scan models.

## Verification matrix

- Semantic, evaluator, scan, agent, and benchmark-semantic tests.
- `mise run check`, coverage, and privacy gate.
- Security review of cache contents and untrusted evidence boundaries.

## Completion checklist and handoff

- [ ] Semantic subresponsibilities have one owner each.
- [ ] Old imports remain valid.
- [ ] Central redaction is used everywhere.
- [ ] Commit with `refactor: split semantic package`; open the PR without merging.
