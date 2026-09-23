# Consolidation Progress Ledger

This ledger records evidence for C01–C64. It starts at `planned` because this branch contains the backlog artifacts, not product consolidation implementations. A Build agent updates only its assigned row and appends commands, results, compatibility notes, and review evidence.

## Status legend

`planned` · `ready` · `in-progress` · `blocked` · `review` · `accepted` · `split`

## Program checkpoints

| Checkpoint | Status | Evidence |
| --- | --- | --- |
| Backlog contract (pre-C01) | accepted | bootstrap commit `920f2b1`; C01 remains in review |
| C01–C10 application boundary | planned | No product slice accepted |
| C11–C20 domain/reporting/policy boundary | planned | No product slice accepted |
| C21–C32 model/platform/adapter boundary | planned | No product slice accepted |
| C33–C44 testing/architecture/infrastructure audit | planned | No product slice accepted |
| C45–C54 error/config/docs/threat audit | planned | No product slice accepted |
| C55–C64 adversarial/final verification | planned | No product slice accepted |

## Slice ledger

| ID | Status | Owner/PR | Focused evidence | Review notes |
| --- | --- | --- | --- | --- |
| [C01](prompts/C01-baseline-contract.md) | accepted | [PR #25](https://github.com/parthmule28/conformdag/pull/25) | `origin/main @ c20b9a19`; `mise run check`: 501 passed, 2 skipped, 19 deselected; `mise run test:coverage`: 90.64%; 522 collected; inventory passed; local-link/index validation; PR CI: Fast checks, macOS, browser, benchmark, release, and Airflow runtime passed; semantic smoke skipped as opt-in | ADR 0004 accepted; independent review passed; documentation-only change; no product code or generated schema changes |
| [C02](prompts/C02-domain-vocabulary.md) | accepted | `docs/c02-domain-vocabulary` ([PR #26](https://github.com/parthmule28/conformdag/pull/26)) | `mise run check`: 513 passed, 19 deselected; `mise run test:coverage`: 90.86%; 532 collected; `mise run schema --check`; frontend: 153 passed; `mise run ui-build`; `mise run build`; `git diff --check` | Additive canonical fields, explicit conflict rejection, partial-update coverage, OpenAPI deprecation metadata, and legacy-only creation coverage implemented; legacy `check_kind` means `configuration.kind`, not a deterministic check, and remains a compatibility projection until C14/C30; no report/schema behavior changes |
| [C03](prompts/C03-check-catalogue.md) | accepted | `docs/c03-authoritative-check-catalogue` ([PR #27](https://github.com/parthmule28/conformdag/pull/27)) | Merge commit `2b8f0d8d95fc6159885db5052ad709846b5ccad8`; `mise run check`: 527 passed, 19 deselected; `mise run test:coverage`: 90.98%; 546 collected; `mise run schema --check`; `mise run build`; focused registry/evaluator/fixing/CLI/policy/round-trip suite: 148 passed; `git diff --check` | One authoritative `CheckSpec` catalogue with 15 entries and exactly 12 executable evaluator-backed entries; evaluator compatibility imports are cycle-safe and internal routing uses a local registry helper; `fix_kind` vocabulary and explicit `FIXERS` preserved; semantic-only entries remain non-executable until they are separately implemented in a future scoped slice; no scan, policy ID, finding, report, fix, or scaffold behavior changes; final review passed and PR merged |
| [C04](prompts/C04-analysis-package.md) | accepted | `docs/c04-analysis-package` ([PR #28](https://github.com/parthmule28/conformdag/pull/28)) | Merge commit `3a651fe8b516b18fb8de2994e76c262635ce7482`; focused analysis/evaluator/scan suite: 72 passed; `mise run check`: 539 passed, 2 skipped, 19 deselected; `mise run test:coverage`: 539 passed, 2 skipped, 19 deselected; 90.68% coverage; `mise run schema --check`; `git diff --check`; consolidation local links and package-boundary checks passed; independent review: no Critical/Important findings | `conformdag.analysis` now owns a five-file package facade with 21 identity-preserving exports; historical parse-cache pickle globals are retained for new and legacy entries; discovery/symlink, AST, cache atomicity/pruning, scan, and schema behavior are preserved; no CLI/platform/evaluator/fixing dependency entered analysis; PR #28 merged by human-authorized action; four Minor review notes deferred |
| [C05](prompts/C05-deterministic-checks.md) | accepted | [PR #29](https://github.com/parthmule28/conformdag/pull/29) | Merge commit `fbc4342fbf695dfe22a77b670e9cacf1548a1db2`; PR #29 head `6ddbb37fdc2172f84f528850076192472c4cb9d1`, based on `3a651fe8b516b18fb8de2994e76c262635ce7482`; focused modular-check/facade/fixing suite: 154 passed; `mise run check`: 575 passed, 2 skipped, 19 deselected; `mise run test:coverage`: 90.84% total coverage; `mise run schema --check`; `git diff --check`; Ruff, Pyright, policy-pack validation, dependency inventory, and the 80-case round-trip population passed | `checks.common`, `checks.airflow.{metadata,scheduling,safety}`, and `checks.evaluate` now own deterministic checks; `conformdag.evaluator` is a compatibility facade; C03's catalogue and C04 boundaries remain authoritative; C06 application orchestration was not pulled forward; independent review of `3a651fe8b..df0e6d0` found no Critical/Important issues; minor review documentation cleanups applied; PR #29 merged by human-authorized action |
| [C06](prompts/C06-application-scan.md) | accepted | [PR #30](https://github.com/parthmule28/conformdag/pull/30) | Merge commit `dfa8dca25311090b5b8fde6c6460df8f710a1371`; implementation head `06a16e474da27be1781f625ba9b623f6e4806138`, based on `fbc4342fbf695dfe22a77b670e9cacf1548a1db2`; focused suite: 178 passed; `mise run check`: 607 passed, 2 skipped, 19 deselected; coverage: 91.03%; `mise run schema --check`; full-range `git diff --check`; cross-worktree parity for deterministic, semantic, runtime, repository-suppression, passing/failing gate, and baseline cases matched (only `run.timestamp` excluded; exit codes matched); final PR CI run `35810415322` passed all required checks, semantic smoke skipped as opt-in | Independent whole-branch review and final human review found no Critical, Important, or Minor issues; all three recorded rulings accepted; `platform/runner.py` unchanged; application boundary, CLI output/exits, and schema compatibility preserved; C07 configuration precedence and C10 platform delegation remain future slices; parity is cross-worktree evidence, not a claimed pre-migration capture |
| [C07](prompts/C07-effective-configuration.md) | accepted | [PR #33](https://github.com/parthmule28/conformdag/pull/33) | Merge commit `edaaf878c378bd81f61da03ac3d0ec406e26c02d`; reviewed implementation head `c053921ccaa7387836f18b6b3880b5690560c56d`; final PR head `c7f7467e4cccf86b17e0320ca8a44173961dcb99`; PR base `main@c330cd928fb1013b02ad96fb2ada2a45e6228c57`; focused suite: 338 passed, 2 skipped; `mise run check`: 655 passed, 2 skipped, 19 deselected; coverage: 91.16%; schema and whitespace checks passed; final-head CI run `35846142056`: all required checks passed, opt-in semantic smoke skipped | Independent final review found no Critical, Important, or Minor issues. C06/C07 report JSON and exits match byte-for-byte for deterministic, fake-semantic, fake-runtime-profile, repository-suppression, baseline, gate-pass, and gate-fail cases. Sole intentional behavior correction: `--runtime-image` clears a lower-precedence project Airflow profile before core evaluation; PR #33 merged |
| [C08](prompts/C08-airflow-profile.md) | accepted | [PR #35](https://github.com/parthmule28/conformdag/pull/35) | Merge commit `faa731edd702b04b1daf1368c08744a6bb771a17`; reviewed implementation head `53b2c31512c4be4673b37f1af0a80c2a2959645b`; final PR head `d64cd6c13bf27cd6a8f9dcd7a90bed62b15ab054`; PR base `main@f49c145fba1cb6b9969431a2ce0c8982487532bb`; focused application/config suite: 41 passed; API/workspace profile suite: 5 passed; runner suite: 22 passed; finding-payload runner regression: 1 passed; `mise run check`: 665 passed, 2 skipped, 19 deselected; coverage: 91.19%; `mise run schema --check` and `git diff --check` passed; final-head CI run [35893869826](https://github.com/parthmule28/conformdag/actions/runs/35893869826): all required checks passed | Independent review and final human review found no Critical, Important, or Minor issues. Platform profile is validated/coerced and reaches core evaluation; project fallback, runtime-disabled/image-preserved behavior, invalid historical-row failure and cancellation fencing are covered; no DB migration or worker-specific logic; PR #35 merged via user-authorized action |
| [C09](prompts/C09-typed-scan-state.md) | planned | — | — | — |
| [C10](prompts/C10-platform-runner.md) | planned | — | — | — |
| [C11](prompts/C11-outcome-classification.md) | planned | — | — | — |
| [C12](prompts/C12-platform-services.md) | planned | — | — | — |
| [C13](prompts/C13-fastapi-routes.md) | planned | — | — | — |
| [C14](prompts/C14-platform-contracts.md) | planned | — | — | — |
| [C15](prompts/C15-security-redaction.md) | planned | — | — | — |
| [C16](prompts/C16-policy-package.md) | planned | — | — | — |
| [C17](prompts/C17-policy-editing.md) | planned | — | — | — |
| [C18](prompts/C18-reporting-package.md) | planned | — | — | — |
| [C19](prompts/C19-fingerprint-contract.md) | planned | — | — | — |
| [C20](prompts/C20-baseline-suppression.md) | planned | — | — | — |
| [C21](prompts/C21-models-package.md) | planned | — | — | — |
| [C22](prompts/C22-semantic-package.md) | planned | — | — | — |
| [C23](prompts/C23-runtime-package.md) | planned | — | — | — |
| [C24](prompts/C24-platform-persistence.md) | planned | — | — | — |
| [C25](prompts/C25-transaction-ownership.md) | planned | — | — | — |
| [C26](prompts/C26-postgres-integration.md) | planned | — | — | — |
| [C27](prompts/C27-worker-runner.md) | planned | — | — | — |
| [C28](prompts/C28-cli-package.md) | planned | — | — | — |
| [C29](prompts/C29-cli-output.md) | planned | — | — | — |
| [C30](prompts/C30-compatibility.md) | planned | — | — | — |
| [C31](prompts/C31-openapi-types.md) | planned | — | — | — |
| [C32](prompts/C32-frontend-api.md) | planned | — | — | — |
| [C33](prompts/C33-test-suite-split.md) | planned | — | — | — |
| [C34](prompts/C34-layered-tests.md) | planned | — | — | — |
| [C35](prompts/C35-production-coverage.md) | planned | — | — | — |
| [C36](prompts/C36-property-mutation.md) | planned | — | — | — |
| [C37](prompts/C37-dependency-audit.md) | planned | — | — | — |
| [C38](prompts/C38-packaging-audit.md) | planned | — | — | — |
| [C39](prompts/C39-container-audit.md) | planned | — | — | — |
| [C40](prompts/C40-ci-consolidation.md) | planned | — | — | — |
| [C41](prompts/C41-architecture-tests.md) | planned | — | — | — |
| [C42](prompts/C42-import-side-effects.md) | planned | — | — | — |
| [C43](prompts/C43-filesystem-boundary.md) | planned | — | — | — |
| [C44](prompts/C44-observability.md) | planned | — | — | — |
| [C45](prompts/C45-error-taxonomy.md) | planned | — | — | — |
| [C46](prompts/C46-config-inventory.md) | planned | — | — | — |
| [C47](prompts/C47-demo-code.md) | planned | — | — | — |
| [C48](prompts/C48-benchmark-package.md) | planned | — | — | — |
| [C49](prompts/C49-dead-code-audit.md) | planned | — | — | — |
| [C50](prompts/C50-complexity-pass.md) | planned | — | — | — |
| [C51](prompts/C51-todo-audit.md) | planned | — | — | — |
| [C52](prompts/C52-docs-overhaul.md) | planned | — | — | — |
| [C53](prompts/C53-agents-rewrite.md) | planned | — | — | — |
| [C54](prompts/C54-threat-model.md) | planned | — | — | — |
| [C55](prompts/C55-adversarial-suite.md) | planned | — | — | — |
| [C56](prompts/C56-postgres-stress.md) | planned | — | — | — |
| [C57](prompts/C57-performance.md) | planned | — | — | — |
| [C58](prompts/C58-security-review.md) | planned | — | — | — |
| [C59](prompts/C59-architecture-review.md) | planned | — | — | — |
| [C60](prompts/C60-audit-replay.md) | planned | — | — | — |
| [C61](prompts/C61-onboarding.md) | planned | — | — | — |
| [C62](prompts/C62-release-rehearsal.md) | planned | — | — | — |
| [C63](prompts/C63-enforcement.md) | planned | — | — | — |
| [C64](prompts/C64-final-report.md) | planned | — | — | — |

## Update rule

An accepted row must link to its PR, focused test output, relevant full-gate output, independent-review evidence when required, and any compatibility or schema notes. A `split` row must name every child slice and explain why the original boundary was unsafe.
