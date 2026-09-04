## Why

ADR 0002 (via capability `org-governance-1-0`) makes the GitHub Action a 1.0.0 MUST — "runs a
scan, can upload SARIF, fails the job on blocking findings" — and git-native policy
distribution the golden path, yet nothing specs either surface. ADR 0003 decision 7 pins the
distribution design: git-native `conformdag pack pull <git-url>` first, git as the auth
boundary (private repos and deploy keys work with ambient credentials), no ConformDAG account,
SSO deferred post-1.0, and a pull interface that lets a platform-backed source slot in later.
This change turns those decisions into a reviewable capability before implementation begins.

## What Changes

- Ship a composite GitHub Action living in this repository (`action.yml` at the repo root),
  versioned by git release tags aligned with CLI releases.
- The action invokes the CLI via `uvx --from conformdag==<pinned version>`; the version
  defaults to the action's own release tag, with an input to override the CLI version.
- Action inputs: `path` (default `.`), `policy-pack` (filesystem path, `community`, or a git
  URL the action resolves by running `conformdag pack pull` first), `upload-sarif` (default
  `true`), `fail-on-blocking` (default `true`), `semantic` (default `false`). On public repos
  with the community pack the action works with zero credentials (try-now path).
- The scan writes SARIF to a stable path (`.conformdag/report.sarif`); SARIF upload is
  composed from `github/codeql-action/upload-sarif`; blocking findings fail the job via the
  CLI's exit code 1 semantics.
- Add `conformdag pack pull <source>`: clone/pull with ambient git credentials into a local
  cache (default `.conformdag/packs/<name>`), validate with the existing provenance/schema
  validation, record the resolved commit ref, and update only on explicit re-pull. The source
  grammar reserves a scheme prefix (e.g. `platform://`) for a later platform-backed registry.
- No engine, report schema, or pack schema changes; no `org-governance-1-0` modifications —
  the existing requirements already authorize this change.

## Capabilities

### New Capabilities

- `distribution-and-ci`: Composite in-repo GitHub Action (uvx-invoked pinned CLI, stable SARIF
  path plus codeql upload step, fail-on-blocking, zero-credential try-now) and git-native
  `conformdag pack pull` — ambient-credential fetch, existing provenance validation, recorded
  resolved refs, explicit re-pull, and a forward-compatible source grammar — with CI scans
  producing the same canonical report JSON contract as local scans.

### Modified Capabilities

None — `org-governance-1-0`'s "GitHub Action in 1.0.0" and "Git-native org policy
distribution" requirements already authorize this change; it is a pure ADDED capability.

## Impact

- New `action.yml` at the repository root (composite action) plus workflow files, including a
  self-test workflow running the action against `examples/sample-repository` on push and PR.
- New pack-pull module in `src/conformdag` and a `conformdag pack pull` CLI subcommand.
- Docs: action usage section (README/user guide), private-repo credentials guide, and a
  release-checklist entry for tag-aligned action versioning.
- No scan engine, canonical report JSON, or policy pack schema changes.
