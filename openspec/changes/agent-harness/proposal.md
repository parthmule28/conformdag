## Why

ConformDAG's differentiator is not another linter — it is an agentic enforcer that turns
deterministic findings into human-mergeable pull requests and keeps the policies themselves
healthy. ADR 0003 makes the agent a tool user of ConformDAG: it reads the canonical report
JSON, triages findings, applies deterministic codemods, proves the fix by deterministic
re-scan, then an LLM-verifier reviews the diff and re-scan report for semantic sanity before
the agent pushes a branch and opens a PR via a GitHub App. The agent never merges — humans
merge. Deterministic codemods make fix generation safe; deterministic re-scan makes
compliance provable; the LLM only gates semantic sanity. This reverses the
`org-governance-1-0` "automatic pull request creation" non-goal under a hard never-merge
constraint.

## What Changes

- Add the `agent-harness` capability: an agent that consumes the canonical report JSON,
  triages findings, applies codemods from the fix-engine registry, verifies by deterministic
  re-scan, obtains an LLM-verifier verdict, and opens evidence-rich PRs via a GitHub App.
- Amend the `org-governance-1-0` 1.0.0 non-goals requirement per ADR 0003: remove
  "automatic pull request creation" from the exclusion list (agents open PRs and never
  merge) and narrow the auth non-goal so single-admin platform authentication is in scope.
- Add a policy-review agent mode that drafts policy-pack PRs against the org policy repo
  from governance aggregates (fail rates by policy, suppression rates, stale suppressions,
  never-firing policies).
- Keep the agent optional: install extra `[agent]`, BYOK OpenAI-compatible endpoints, and
  no effect on offline deterministic scan/fix.

## Capabilities

### New Capabilities

- `agent-harness`: Agentic enforcement harness — the agent operates the existing scan/fix
  engine as a tool user (no second pipeline), generates patches only via deterministic
  codemods, verifies by re-scan, gates PRs on a strict LLM-verifier verdict against
  OpenAI-compatible endpoints, opens PRs under a GitHub App identity with an
  interpretability evidence body, never merges/approves/force-pushes, and reviews policies
  themselves from governance aggregates.

### Modified Capabilities

- `org-governance-1-0`: The 1.0.0 non-goals requirement is amended per ADR 0003 —
  automatic pull request creation moves from non-goal to in-scope via `agent-harness` under
  the never-merge constraint, and the auth non-goal is narrowed to dashboard multi-user
  authentication or RBAC (single-admin auth is in scope via the platform-server change).

## Impact

- New optional install extra `[agent]`; all agent code under `src/conformdag/agent/`.
- GitHub App integration: least-privilege manifest, short-lived installation tokens, no PATs.
- Depends on the `fix-engine-and-codemods` change (codemod registry, verify-by-rescan,
  agent-readable findings); benefits from — but does not hard-require — the
  `platform-server` change for policy aggregates (a local summary mode is provided when the
  platform is absent).
- Modifies the `org-governance-1-0` non-goals requirement; downstream changes MUST NOT
  reintroduce auto-PR as a non-goal or weaken the never-merge constraint.
