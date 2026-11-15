## Canonical Issue and authority

Refs #REPLACE_WITH_CANONICAL_ISSUE_NUMBER

- [ ] Authorized Stage B implementation PR (link explicit user authorization comment below)
- [ ] Exceptional governance / ADR / documentation PR (state why it is necessary)

**Stage B authorization (or exception):** LINK_OR_NOT_APPLICABLE
**Exact accepted main baseline SHA:** SHA
**Current PR head SHA:** SHA (update after every push; review and CI must match)
**User merge authorization:** NOT GRANTED; separate explicit permission is required for this exact reviewed head.

## Intended outcome and bounded diff

<!-- What changed, why, and what intentionally did NOT change? -->

| Changed file / owner | Accepted Issue criterion | Reason / contract preserved |
| --- | --- | --- |
| | | |

## Sequential TDD and implementation evidence (Stage B only)

<!-- Link tests added before changes, RED -> GREEN evidence, changed patch seams and handback. Use N/A with reason for a documentation-only exception. -->

## Validation and exact-head CI

- [ ] Focused affected tests and any relevant runtime/Docker smoke (or N/A with reason)
- [ ] Local mise run check, strict Pyright 0 errors and >=90% coverage (or explain unavailable evidence)
- [ ] Real PostgreSQL 17 suite twice, database/backend cleanup when relevant (or N/A with reason)
- [ ] Schema/pack/inventory/build, security and credential/privacy boundaries checked
- [ ] Git diff and whitespace checked; no unrelated files or generated artifacts
- [ ] Seven mandatory exact-head GitHub checks independently verified at the current PR head

Required hosted checks: **Fast checks**; **Offline benchmark gate**; **Release validation**; **macOS host CLI and source analysis**; **Airflow runtime profile (3.3.0)**; **PostgreSQL integration**; **Browser journeys (Playwright)**.

**Head CI run / exact SHA:** LINK_AND_SHA_OR_PENDING
**Known limitations, deferred issues and regression risks:** DETAILS

## Handover and merge prohibition

- [ ] Implementation writer has stopped; one implementation PR for this milestone remains unmerged
- [ ] ChatGPT independent exact-head review and all seven checks are pending or linked above
- [ ] User has separately authorized merge of this exact reviewed head (do NOT precheck)
- [ ] After a user-authorized merge, ChatGPT will verify seven jobs on the exact main merge SHA, record formal acceptance in the canonical Issue, and only then close that Issue

**Do not use Closes/Fixes/Resolves #N for milestone Issues.** Use Refs #N so GitHub does not auto-close them before Stage C acceptance. No default Stage A or Stage C docs-only PR. OpenCode never merges its own PR.
