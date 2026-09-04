## 1. Install extra and configuration

- [x] 1.1 Add the `[agent]` optional extra (OpenAI-compatible client, GitHub App client); offline `scan`/`fix` MUST work without it
- [x] 1.2 Add the agent config surface: OpenAI-compatible endpoint base URL, model, and API key via environment variable (no keys in files)
- [x] 1.3 Fail fast with actionable errors when the extra or credentials are missing

## 2. Report consumption and triage

- [x] 2.1 Implement the report-consumption layer over the canonical report JSON (agent-readable findings, remediation payloads, code anchors, fix hints)
- [x] 2.2 Triage findings into mechanical-autofix, proposed-diff-only, and human/agent-only per the fix-engine fixability matrix
- [x] 2.3 Shape the consumption layer as a tool surface so a later MCP adapter can expose the same operations

## 3. LLM-verifier integration

- [x] 3.1 Define the strict verdict schema (approve/reject with reasons); malformed or unknown responses are rejected
- [x] 3.2 Build the verification input from diff plus before/after reports with untrusted-evidence delimitation and redaction
- [x] 3.3 Reuse semantic-boundary infrastructure: strict response validation, bounded concurrency, normalized caching
- [x] 3.4 Enforce end-to-end that a reject verdict blocks PR creation

## 4. GitHub App integration

- [x] 4.1 Author the least-privilege GitHub App manifest (contents: write for branch push, pull requests: write; no merge/approve/workflow scopes)
- [x] 4.2 Implement the installation token flow (short-lived tokens, no PATs)
- [x] 4.3 Document App installation and per-org configuration

## 5. Branch and PR authoring

- [x] 5.1 Push a dedicated branch per PR candidate; never commit to the default branch
- [x] 5.2 Render the evidence PR body: findings fixed with file/line, policy contracts, report fingerprints before/after, deterministic verification result, LLM-verifier verdict, rollback note
- [x] 5.3 Enforce never-merge / never-approve / never-force-push at the client capability level (no such methods exist on the agent's GitHub client)

## 6. End-to-end pipeline command

- [x] 6.1 Add `conformdag agent run` (or equivalent): scan → triage → codemod → verify-by-rescan → LLM-verifier → branch + PR
- [x] 6.2 Support a dry-run mode that stops before any git write
- [x] 6.3 Bound fix iterations; exit non-zero on unclean re-scan or reject verdict

## 7. Policy-review mode

- [x] 7.1 Consume platform aggregates (fail rates by policy, suppression rates, stale suppressions, never-firing policies) when the platform is available
- [x] 7.2 Compute a local aggregate summary from workspace scans when the platform is absent
- [x] 7.3 Draft policy-pack PRs against the org policy repo for human review, with the same evidence-body and never-merge constraints

## 8. Safety tests

- [x] 8.1 Verifier rejection blocks PR creation (fixture: semantically nonsensical codemod output that re-scans clean)
- [x] 8.2 Never-merge enforcement: no merge/approve/force-push capability exists in the agent client; App permissions deny them
- [x] 8.3 Deterministic FAIL cannot be cleared by agent or LLM output (re-scan is the only path)
- [x] 8.4 Offline scan/fix works without the `[agent]` extra installed

## 9. Documentation

- [x] 9.1 Agent setup guide: install extra, endpoint/model/key configuration, first run
- [x] 9.2 GitHub App guide: manifest, permissions, token model, org installation
- [x] 9.3 Threat model: untrusted evidence, prompt injection, least privilege, never-merge constraint

## 10. Benchmark and evidence recording

- [x] 10.1 Extend the round-trip benchmark to the full agent pipeline (inject → fix → re-scan → verify → PR body)
- [x] 10.2 Record LLM-verifier verdicts and evidence bodies as benchmark artifacts for release gating
