# AGENTS.md — ConformDAG

Apache Airflow policy governance: deterministic scanner + fix engine + agentic PR pipeline + self-hosted dashboard. Python 3.12, managed via **mise** (Python + uv + node pinned in `mise.toml`).

## Commands

```bash
mise run setup          # uv sync --all-groups --all-extras (REQUIRED — core deps + [platform] extra + dev deps)
mise run check          # the full local gate: format-check → lint → typecheck → test → validate:packs
mise run test:coverage  # pytest + 90% coverage gate (CI runs this)
mise run schema:update  # regenerate JSON schemas after model changes; mise run schema --check verifies
mise run ui-build       # frontend SPA build (npm ci + vite build → outputs to src/conformdag/platform/static/)
mise run test:runtime   # Dockerized Airflow tests (requires Docker; separate from the default suite)
```

Single test: `mise exec -- uv run pytest tests/test_platform.py::test_name -x --tb=short`

## Non-obvious gotchas

- **`uv run` implicitly syncs** the locked env without extras — if the `[platform]` extra (fastapi, sqlalchemy, etc.) is missing, platform tests fail with `ModuleNotFoundError`. Always use `mise run setup` (which includes `--all-extras`) after cloning or changing pyproject.toml.
- **The [platform] extra is required for tests.** `tests/test_platform.py` imports fastapi/sqlalchemy at module level. CI runs `mise run setup` with `--all-extras`.
- **Hatchling respects `.gitignore`**: `src/conformdag/platform/static/` (the built SPA) is gitignored, so the wheel will silently exclude it unless `artifacts = ["src/conformdag/platform/static/**"]` is present in pyproject.toml's `[tool.hatch.build.targets.wheel]`. Never remove this line.
- **`mise run check` = format-check → lint → typecheck → test → validate:packs.** Run this before every commit. CI mirrors it.
- **Pyright strict** (`typeCheckingMode = "strict"`) — 0 errors is the gate. Test files are included. Untyped imports (starlette TestClient) are handled via typed helpers (`_as_httpx`, `cast`) in test files.
- **Coverage gate is 90%** — enforced by `mise run test:coverage`. Adding untested code will fail the build.
- **Schema regeneration**: after changing any pydantic model in `models.py`, run `mise run schema:update` and commit the JSON files in `schemas/`. CI checks they are in sync.
- **ruamel.yaml** needs `# pyright: ignore[reportUnknownMemberType]` on `.load()` and `.dump()` calls (the entire codebase follows this convention).
- **Alembic migrations** — the platform schema is created exclusively through `src/conformdag/platform/migrations/`. `create_session_factory()` runs `command.upgrade(alembic_config, "head")` at startup. Do NOT use `Base.metadata.create_all()`. The migration `env.py` reads the DSN from the Alembic config's `sqlalchemy.url` option (set programmatically), falling back to `CONFORMDAG_PLATFORM_DSN`.
- **Frontend**: the dashboard SPA lives in `frontend/` (React + Vite + TypeScript + Tailwind + TanStack Query). `npm run build` outputs to `../src/conformdag/platform/static/`. TS strict mode, no SSR. Node version is pinned in mise.toml.
- **The SPA is gitignored** but must be present in the wheel for the platform image to serve it. Run `mise run ui-build` before `mise run build` when the dashboard changes.

## Architecture (the stuff that isn't obvious from filenames)

- **Single scan engine**: `src/conformdag/scan.py` → `scan_repository()` is the only evaluation path. CLI, platform API, GitHub Action, and agent all invoke this. Never create a second evaluation pipeline.
- **Evaluator registry**: `src/conformdag/evaluator.py` — `CHECK_EVALUATORS` dict keyed by check kind (e.g. `"effective-owner"`), not policy ID. Each evaluator class has a `policy_id` attribute for the legacy alias table.
- **Codemod registry**: `src/conformdag/fixing/codemods.py` — `FIXERS` dict keyed by check kind. Fixability matrix: `AUTOFIX_KINDS` (mechanical), `PROPOSED_ONLY_KINDS` (never auto-applied), `MANUAL_KINDS` (not fixable).
- **Fix engine flow**: scan → triage (pure rules, no LLM) → codemod → apply to temp copy → re-scan → verify → only verified patches are presented. `--apply` is the only write path.
- **Policy packs are YAML with provenance**: every policy references a standards document + section + content_hash. Provenance is validated by `policy.py`. The hash is SHA-256 of the document text.
- **Platform** = FastAPI (`app.py`) + subprocess worker (`worker.py`) + Postgres (SQLAlchemy + Alembic). Scans run in isolated subprocesses (`runner.py`) claimed via `SELECT ... FOR UPDATE SKIP LOCKED` on the `scans` table.
- **Route ordering in FastAPI matters**: the `/api/{rest:path}` fallback and the `StaticFiles` mount at `/` must be registered AFTER all specific API routes, or they will intercept them.
- **The agent** (`agent/`) never merges: deterministic triage → codemod → re-scan → LLM verdict (approve/reject/escalate) → branch + PR via GitHub App. No merge/approve capability by construction.
- **Frontend ↔ backend contract**: the SPA is a hand-written typed client (`frontend/src/api.ts`) matching the stable `/api/v1` contract. `updatePolicy` wraps `upsertPolicy` (they exist as separate functions in api.ts).

## Conventions that differ from defaults

- **Ruff**: line-length 120, `E501` ignored (formatter handles it), `S105/S603/S607` ignored (security exceptions). Test files allow `S101` (assert) and `S106` (hardcoded test tokens).
- **No `# type: ignore`** — the codebase uses targeted `# pyright: ignore[ruleName]` comments only for ruamel.yaml untyped calls. All other type errors are fixed properly.
- **Dataclass default factories**: use named functions (`_empty_patches() -> list[FilePatch]`) instead of bare `field(default_factory=list)` — pyright strict infers `list[Unknown]` from the latter.
- **`cast()` over type ignore**: use `typing.cast` for narrowing at untyped boundaries (mirrors policy.py's pattern).
- **No bare `except Exception`**: catch specific exceptions (`ValueError`, `OSError`, `RuntimeError`) — the runner uses `PERSISTENT_FAILURES` for this pattern.
- **OpenSpec**: normative specs live in `openspec/changes/<name>/specs/<capability>/spec.md`. Each change has `proposal.md`, `design.md`, `tasks.md`. Tasks are checked off as implementation lands. ADRs live in `docs/adr/`.
- **Conventional commits**: `feat:`, `fix:`, `docs:`, `chore:`, `perf:`, `style:`, `fix(release):` etc.

## Testing

- `pytest -m "not runtime"` is the default suite (runtime tests need Docker + the Airflow runtime image).
- Platform tests use SQLite (via `create_session_factory("sqlite:///...")`). Postgres is only exercised in compose/manual boot.
- The round-trip benchmark gate (`tests/test_roundtrip.py`) runs the fix engine over 80 benchmark cases — it takes ~20s and is part of the standard suite.
- `fixture name="build_repository"` in `conftest.py` builds a temp repo with a violating DAG — use it for fix-engine and agent tests.
- Fixture-injected params need explicit type annotations for pyright strict: `build_repository: Callable[[Path], Path]`.

## Git & release

- `main` is protected: PRs required, no force-push. Use feature branches, merge via PR.
- Release tags are `v*` (the train triggers on `v*` tag push). The `pypi` environment deployment policy must have the tag as `type: tag` — a policy added before the tag exists is recorded as branch type and blocks publishing.
- Image tags use the full ref name (`v1.0.0-beta.1`, not `1.0.0`) — `github.ref_name` on a tag push includes the `v`.
- New GHCR package names start private — flip to Public in package settings after first publish.
- Release checklist lives in `docs/release.md` with per-release evidence sections.
