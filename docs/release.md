# Beta release checklist

The public beta is released only from a reviewed `v0.1.0-beta.1` tag on `main`. The
release workflow first re-runs quality, benchmark, schema, dependency, secret, privacy,
and image-vulnerability gates. Only then does it publish the GHCR runtime image;
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
  checks, deletion protection, and force-push protection. Required approvals are
  temporarily zero while the repository has one maintainer because GitHub does not count
  self-approval; restore one required approval when a second trusted maintainer is added.
- [x] Preliminary trademark/confusability screening was recorded on 2026-08-01. No exact
  or materially similar `ConformDAG` result was found in GitHub, PyPI, general web, WIPO,
  USPTO, EUIPO, or IP India searches available at the time. This is not legal advice or
  a guarantee against unregistered rights.

## Required pull-request checks

- [x] Fast checks.
- [x] Offline benchmark gate.
- [x] Release validation.
- [x] macOS host CLI and source analysis.
- [x] Airflow runtime profile 3.3.0.

The opt-in `Semantic provider smoke` job is intentionally not a protected-branch
requirement because it uses an external paid provider. To enable it, set the repository
variable `CONFORMDAG_RUN_SEMANTIC_SMOKE=true`, variables
`CONFORMDAG_SEMANTIC_BASE_URL` and `CONFORMDAG_SEMANTIC_MODEL`, and the Actions secret
`CONFORMDAG_MODEL_API_KEY`. It performs a real provider-backed example scan, not an
accuracy baseline. Leave it disabled when those credentials and costs are not approved.

## Release evidence

- [ ] Run the updated real Docker smoke job for the maintained 3.3.0 profile after this
  release-scope change.
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
- [x] Review the final local wheel/sdist contents, generated schemas, and checksums before
  creating the tag. The isolated wheel reported `0.1.0b1` and completed the public example
  scan. Local SHA-256 values were `a79335ef...ab9c381` for the wheel and
  `2d1b2fc...df06613` for the source distribution; the tag workflow independently
  regenerates and publishes its full checksums.
- [ ] Merge the reviewed release-preparation pull request, then create and push
  `v0.1.0-beta.1` from that exact `main` commit.
- [ ] Confirm the tag workflow's attestations, image SBOMs, and high/critical image scan
  results before approving the final PyPI deployment.
- [ ] After publication, confirm the GHCR 3.3.0 runtime package is public and can be
  pulled anonymously; the supported `scan --runtime` profile depends on anonymous digest
  resolution.

Airflow 2.11.2 was removed from the beta before publication. It was initially built and
tested as a legacy compatibility candidate, but its upstream end-of-life status means
the project cannot responsibly promise the security fixes and maintenance cadence that a
published supported profile requires. Its historical benchmark/source references remain
provenance only; they do not indicate an active supported runtime.

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
