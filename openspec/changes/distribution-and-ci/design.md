## Context

See `proposal.md` for why. `org-governance-1-0` (ADR 0002) already REQUIRES a GitHub Action in
1.0.0 that "runs a scan, can upload SARIF, and fails the job on blocking findings", and
git-native policy distribution ("central policy repo consumed by DAG repos; no OCI/HTTP bundle
pull; no remote cloning as a platform MUST"). ADR 0003 decision 7 decides the mechanism:
git-native `conformdag pack pull <git-url>` first — git is the auth boundary, so private repos
and deploy keys work with ambient credentials; no ConformDAG account; SSO via the OAuth device
flow is deferred post-1.0; and the pull interface must let a platform-backed source slot in
later. Today the repo has one scan engine, a canonical report JSON contract, SARIF rendering
(`src/conformdag/reporting.py` `render_sarif`), exit code 1 meaning a complete run with
blocking failures, a bundled `community` pack, and provenance/schema pack validation
(`src/conformdag/policy.py`). Nothing exists yet for the action or pack pull; this change is
their contract.

## Goals / Non-Goals

**Goals:**

- Ship the documented GitHub Action as a composite action in this repository, satisfying the
  `org-governance-1-0` action requirement with a zero-credential try-now path.
- Specify `conformdag pack pull` as the git-native distribution golden path: ambient
  credentials, existing provenance validation, recorded resolved refs, explicit updates.
- Keep CI scans on the single scan engine with the same canonical report JSON contract as
  local scans.
- Keep the pull command surface forward-compatible with a platform-backed source.

**Non-Goals:**

- SSO or the OAuth device flow (deferred post-1.0 per ADR 0003).
- A platform-backed registry or any ConformDAG-operated service (only the source grammar is
  reserved).
- Signed OCI/HTTP policy bundle pull (forbidden by `org-governance-1-0`).
- GitHub Marketplace listing chores (optional follow-up; the marketplace can list this
  repository's `action.yml` as-is).
- Scanning via the Docker image inside the action.

## Decisions

1. **The GitHub Action is a composite action living in this repository.** `action.yml` sits at
   the repo root and is versioned by git release tags aligned with CLI releases. Alternative:
   a Docker action. Rejected — couples the action to image builds and is slower. Alternative:
   a separate action repository. Rejected — splits the release train; the marketplace can list
   this repository's `action.yml` anyway.

2. **The action invokes the CLI via `uvx --from conformdag==<pinned version>`.** The pinned
   version defaults to the action's own release tag version; an input lets users override the
   CLI version (forward or backward). Alternative: `pip install` in a setup step. Rejected —
   uvx resolves an isolated, pinned, cacheable environment without a separate step.

3. **Five action inputs cover the CI surface.** `path` (default `.`), `policy-pack`
   (filesystem path, `community`, or a git URL the action resolves by running `conformdag
   pack pull` first), `upload-sarif` (default `true`), `fail-on-blocking` (default `true`),
   `semantic` (default `false`). On public repos with the community pack the action works with
   zero credentials (try-now path). Alternative: a config-file input. Rejected — five explicit
   inputs keep the action transparent and cover the CI mainstream.

4. **SARIF upload composes `github/codeql-action/upload-sarif`.** The scan writes SARIF to a
   stable path (`.conformdag/report.sarif`) and the action composes the upload as a step.
   Blocking findings fail the job via the CLI's exit code 1 semantics (a complete run with
   blocking failures). Alternative: upload SARIF from inside the CLI. Rejected — the CodeQL
   action already handles the upload API and token scoping; the CLI stays offline-only.

5. **`conformdag pack pull <source>` is git-native with ambient credentials.** It clones or
   pulls the pack repo using ambient git credentials (SSH keys, credential helpers) into a
   local cache directory (default `.conformdag/packs/<name>`), validates the pack with the
   EXISTING provenance/schema validation, records the resolved commit ref alongside the pack,
   and requires an explicit re-pull to update (no automatic sync). It SHALL NOT require a
   ConformDAG account, any network service beyond git, or an API key. The source argument
   grammar reserves a scheme prefix (e.g. `platform://`) so a platform-backed registry can
   slot in later without breaking the command surface. Alternative: automatic sync to the
   remote's latest on every scan. Rejected — silent policy drift changes CI outcomes;
   explicit re-pull plus the recorded ref keeps runs reproducible and inspectable.

6. **No `org-governance-1-0` modifications.** The existing "GitHub Action in 1.0.0" and
   "Git-native org policy distribution" requirements already authorize this change; it is a
   pure ADDED capability. Alternative: amend the requirement text to name `pack pull`
   explicitly. Rejected — requirement churn with no behavioral gain.

## Risks / Trade-offs

- [uvx cold-start latency in CI] → The action wires the uv cache so the CLI resolves from
  cache after the first run; latency is paid once per runner cache lifetime.
- [Action version / CLI version drift] → Tag-aligned release pinning makes the default
  coherent; the override input pins forward or backward when they must differ.
- [SARIF upload token unavailable on fork PRs] → Document the `upload-sarif: false` fallback;
  the scan and `fail-on-blocking` still run and the SARIF file remains an artifact.
- [Pack cache staleness] → Updates require an explicit re-pull; the recorded resolved ref
  makes the cached state inspectable at any time.

## Migration Plan

Net-new surfaces only: `action.yml` at the repo root, workflow files, and a new pack-pull
module plus subcommand. No engine, report, or pack schema changes, so there is no runtime
migration for existing users; adopters point workflows at a release tag. Rollback is removal
of the action, workflows, and subcommand; cached packs under `.conformdag/packs` are inert
directories.

## Open Questions

None — resolved at planning (2026-09-02).
