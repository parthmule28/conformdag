# Beta release checklist

The public beta is released only from a reviewed `v0.1.0-beta.1` tag on `main`. The
release workflow first re-runs quality, benchmark, schema, dependency, secret, privacy,
and image-vulnerability gates. Only then does it publish the two GHCR runtime images;
PyPI trusted publishing runs last. Python checksums are kept outside the distribution
directory so they cannot be uploaded to PyPI as packages.

## Repository and identity

- [x] GitHub repository and PyPI project name are `parthmule28/conformdag` and
  `conformdag`.
- [x] PyPI pending trusted publisher is scoped to `.github/workflows/release.yml` and the
  `pypi` environment.
- [x] The `pypi` environment limits deployment to the exact beta tag and contains no
  publishing secret.
- [x] `main` is protected by pull requests, review/conversation resolution, current-branch
  checks, deletion protection, and force-push protection.
- [x] Preliminary trademark/confusability screening was recorded on 2026-08-01. No exact
  or materially similar `ConformDAG` result was found in GitHub, PyPI, general web, WIPO,
  USPTO, EUIPO, or IP India searches available at the time. This is not legal advice or
  a guarantee against unregistered rights.

## Required pull-request checks

- [x] Fast checks.
- [x] Offline benchmark gate.
- [x] Release validation.
- [x] macOS host CLI and source analysis.
- [x] Airflow runtime profile 2.11.2.
- [x] Airflow runtime profile 3.3.0.

The opt-in `Semantic provider smoke` job is intentionally not a protected-branch
requirement because it uses an external paid provider. To enable it, set the repository
variable `CONFORMDAG_RUN_SEMANTIC_SMOKE=true`, variables
`CONFORMDAG_SEMANTIC_BASE_URL` and `CONFORMDAG_SEMANTIC_MODEL`, and the Actions secret
`CONFORMDAG_MODEL_API_KEY`. It performs a real provider-backed example scan, not an
accuracy baseline. Leave it disabled when those credentials and costs are not approved.

## Release evidence still required

- [ ] Run the updated real Docker smoke jobs for both profiles in the audit pull request.
- [x] Run a secret-injected OpenRouter scan with the configured exact model and retain
  only ignored normalized reports. On 2026-08-01, prompt v3 evaluated all four semantic
  policies over the one-DAG public sample with `deepseek/deepseek-v4-flash`; OpenRouter
  reported the exact requested/served model, 3,176 total tokens (2,523 prompt and 653
  completion), no transport retries, four prompt hashes, one context hash, and 90,846 ms
  aggregate client latency. A repeated identical run returned four of four cache hits.
- [x] Record semantic limitations: the beta benchmark has no redistributable labelled
  semantic corpus, so LLM-only, hybrid, deterministic-plus-generic-reviewer, and
  generic-reviewer accuracy baselines remain `not_executed`. Do not describe those
  baselines as measured accuracy.
- [ ] Review the final wheel/sdist contents, generated schemas, checksums, attestations,
  image SBOMs, and high/critical image scan results.
- [ ] After publication, confirm both GHCR runtime packages are public and can be pulled
  anonymously; supported `scan --runtime` profiles depend on anonymous digest resolution.
- [ ] Create and push `v0.1.0-beta.1` only after every item above is accepted.

The workflow has no PyPI token or long-lived GHCR password. GitHub OIDC is used for PyPI
trusted publishing and the scoped `GITHUB_TOKEN` is used for GHCR.

The provider integration audit also confirmed the failure boundary: earlier prompt
versions produced schema-invalid output (including a non-string `evidence` value and
malformed JSON). ConformDAG rejected those responses, emitted a fatal structured
`SEMANTIC_PROVIDER_ERROR`, and did not reinterpret them as findings. Prompt v3 makes the
field contract explicit, but provider schema conformance is still not an accuracy claim.

Trademark search references:

- [WIPO Global Brand Database](https://www.wipo.int/en/web/global-brand-database)
- [USPTO trademark search](https://www.uspto.gov/trademarks/search)
- [EUIPO search](https://www.euipo.europa.eu/en/search)
- [IP India existing-trademark search](https://ipindia.gov.in/trade-marks-before-you-apply-search-existing-trademarks)
