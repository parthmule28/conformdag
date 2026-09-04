## 1. Composite action definition

- [x] 1.1 Create `action.yml` at the repository root as a composite action (metadata,
      descriptions, inputs, `runs: using: composite`)
- [x] 1.2 Define inputs: `path` (default `.`), `policy-pack` (default `community`),
      `upload-sarif` (default `true`), `fail-on-blocking` (default `true`), `semantic`
      (default `false`)
- [x] 1.3 Document each input in the action metadata (accepted forms, defaults, fork-PR
      caveats)

## 2. CLI invocation via uvx

- [x] 2.1 Invoke the CLI via `uvx --from conformdag==<pinned-version> conformdag scan` with
      the version defaulting to the action's own release tag version
- [x] 2.2 Add a CLI-version override input so users can pin forward or backward
- [x] 2.3 Wire uv/uvx caching (setup-uv or actions/cache) so cold start is paid once per
      runner cache lifetime

## 3. Policy pack resolution in the action

- [x] 3.1 When `policy-pack` is a git URL, run `conformdag pack pull <url>` first and scan
      the cached pack path
- [x] 3.2 When `policy-pack` is `community` or a filesystem path, pass it through unchanged
      (zero-credential path; no pull step)

## 4. SARIF write path and upload composition

- [x] 4.1 Scan step writes SARIF to the stable path `.conformdag/report.sarif`
- [x] 4.2 Compose `github/codeql-action/upload-sarif` (pinned) as a step that runs when
      `upload-sarif` is true
- [x] 4.3 Document the fork-PR fallback (`upload-sarif: false`) for runs where the SARIF
      upload token is unavailable; scan and fail-on-blocking still run

## 5. fail-on-blocking wiring

- [x] 5.1 Propagate the CLI exit code so exit code 1 (complete run with blocking failures)
      fails the job when `fail-on-blocking` is true
- [x] 5.2 When `fail-on-blocking` is false, succeed the step while findings remain in the
      report/SARIF artifacts

## 6. Self-test workflow

- [x] 6.1 Add a workflow that runs this repository's action against
      `examples/sample-repository` on push and pull request
- [x] 6.2 Assert the zero-credential path: community pack, SARIF written and uploaded, no
      secrets configured
- [x] 6.3 Include a blocking-finding case that asserts the job concludes unsuccessfully

## 7. `conformdag pack pull` module

- [x] 7.1 New module in `src/conformdag` that clones or pulls the pack repo via git using
      ambient credentials (SSH keys, credential helpers)
- [x] 7.2 Local cache directory with default `.conformdag/packs/<name>`; an existing cache
      is reused without contacting the remote
- [x] 7.3 Validate the pulled pack with the existing provenance/schema validation
      (`src/conformdag/policy.py`); validation failure aborts with a clear error
- [x] 7.4 Record the resolved commit ref alongside the cached pack
- [x] 7.5 Explicit re-pull semantics: updates happen only when pull runs again (no automatic
      sync); scans use the cached pack and recorded ref as-is
- [x] 7.6 Add the `conformdag pack pull <source>` CLI subcommand

## 8. Source grammar

- [x] 8.1 Parse `<source>` as a filesystem path or git URL, deriving the cache name `<name>`
- [x] 8.2 Reserve scheme prefixes in the grammar (e.g. `platform://`) for a later
      platform-backed source
- [x] 8.3 Reject reserved schemes today as unimplemented with a clear message; git URLs keep
      working unchanged

## 9. Tests

- [x] 9.1 Pytest: pull via a `file://` git URL clones, validates, and records the resolved
      ref
- [x] 9.2 Validation failure path: a pack failing provenance/schema validation aborts the
      pull with a clear error
- [x] 9.3 Ref recording: a second run without an explicit re-pull keeps the recorded ref and
      cached pack unchanged
- [x] 9.4 Reserved-scheme rejection: `platform://` sources error clearly while git URL
      sources still succeed

## 10. Docs

- [x] 10.1 Action usage section in README/user guide: inputs matrix, pinned-tag usage, SARIF
      upload notes, fork-PR fallback
- [x] 10.2 Private-repo credentials guide: deploy keys, SSH, credential helpers — git is the
      auth boundary, no ConformDAG account

## 11. Release chores

- [x] 11.1 Note tag-aligned action versioning in the release checklist (the action release
      tag equals the CLI release version it pins by default)
