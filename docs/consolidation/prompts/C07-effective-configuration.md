# C07 — Centralize Effective Scan Configuration

## Role and objective

You are the Build agent for C07. Make configuration precedence explicit and reusable by CLI, platform, worker, and future MCP adapters. Keep secrets outside the effective configuration object and preserve current project defaults.

## Required reads

- `AGENTS.md`, `architecture-rules.md`, `progress.md`, and C06.
- `src/conformdag/config.py`, `src/conformdag/models.py` project config models, `src/conformdag/cli.py`, `src/conformdag/application/scan.py`, and `src/conformdag/semantic.py`.
- `src/conformdag/platform/app.py` settings/repository payloads and `src/conformdag/platform/workspace.py`.
- `tests/test_config.py`, `tests/test_cli.py`, and platform configuration tests.

## Current ownership and resulting owner

Configuration resolution is spread across CLI options, project YAML, platform runner logic, environment reads, and model defaults. After this PR, `src/conformdag/application/configuration.py` owns typed precedence for invocation overrides, platform repository overrides, project config, and defaults. Secret resolution remains in the provider/adapter composition boundary.

## Interfaces

Add:

```python
@dataclass(frozen=True)
class ScanOverrides:
    policy_pack: Path | None = None
    airflow_profile: AirflowProfile | None = None
    runtime_image: str | None = None
    semantic_enabled: bool | None = None
    semantic_base_url: str | None = None
    semantic_model: str | None = None
    semantic_structured_output: bool | None = None


@dataclass(frozen=True)
class EffectiveScanConfiguration:
    project: ProjectConfig
    resolved_policy_pack: Path
    runtime: ProjectRuntimeConfig
    semantic: ProjectSemanticConfig
```

Define `resolve_effective_configuration()` with precedence `explicit invocation → platform repository override → project file → model defaults`.

## Expected files

- Create: `src/conformdag/application/configuration.py` and `tests/application/test_configuration.py`.
- Modify: `src/conformdag/application/scan.py`, `src/conformdag/cli.py`, and platform composition code only to pass typed overrides.
- Do not implement the platform `airflow_profile` behavior beyond passing a validated value; C08 owns that behavior.

## Test-first sequence

1. Add matrix tests for policy pack, profile, runtime image, semantic enablement, endpoint/model, and structured-output precedence.
2. Run the focused application/config tests and verify the resolver is absent.
3. Implement the resolver without storing API keys or reading environment secrets in domain dataclasses.
4. Migrate CLI/application construction to use the resolver and preserve current defaults/errors.
5. Run config/application/CLI/platform tests, `mise run check`, and coverage.

## Allowed changes

- Typed override/effective-config objects, resolution helpers, adapter composition changes, and tests.
- Explicit validation errors for conflicting or invalid overrides.

## Non-goals and prohibitions

- Do not make environment reads occur in core models or checks.
- Do not duplicate precedence rules in CLI, runner, or routes.
- Do not persist API keys, tokens, or DSN values in effective configuration.

## Verification matrix

- Precedence matrix and secret-boundary tests.
- Existing config, CLI, application, and platform suites.
- `mise run check`, coverage, and Pyright.
- Independent review must inspect every caller that previously resolved a project/profile/semantic value.

## Completion checklist and handoff

- [ ] One resolver defines precedence.
- [ ] Secrets remain adapter-only and environment-based.
- [ ] Existing project config behavior is unchanged when no overrides are supplied.
- [ ] Commit with `refactor: centralize scan configuration`; open the PR without merging.
