# Beta release checklist

## 1.0.0b1 release checklist

The 1.0.0b1 soak release ships the v1 agentic platform (ADR 0003): fix engine,
self-hosted platform, agent harness, and distribution surfaces. It is released only
from a reviewed `v1.0.0-beta.1` tag on `main`; the release workflow re-runs every gate
and then publishes PyPI, the GHCR runtime image, and the new GHCR platform image.

- [ ] Update the `pypi` environment deployment policy to allow the exact
  `v1.0.0-beta.1` tag before pushing it.
- [x] Remediate the runtime image security gate found on the first 1.0.0b1 train:
  GitPython 3.1.58, aiohttp 3.14.3, cryptography 50.0.0,
  snowflake-connector-python 4.7.1, snowflake-sqlalchemy 1.11.0, sqlparse 0.6.0,
  and tornado 6.5.8 installed above the Airflow constraints; the Ray-bundled
  httpcore5 jar (CVE-2026-54399, HIGH, no fixed build available to Airflow 3.3.0)
  is allowlisted in `.trivyignore` with justification. Local re-scan of
  `conformdag-airflow-smoke:3.3.0` exits 0 under the CRITICAL/HIGH gate.
- [ ] Review the release run's `Validate release candidate` job for all quality,
  benchmark, schema, dependency, secret, and privacy gates.
- [ ] Confirm the `Validate platform image` job: wheel contains the built dashboard
  static assets, `serve`/`worker` smoke, and the Trivy CRITICAL/HIGH gate passed.
- [ ] Confirm the published platform image carries SBOM and provenance attestations
  and is tagged with the release ref and `latest`.
- [ ] Confirm the `Run the composite action against the sample repository` self-test
  passed on the release commit, covering the community pack path and the
  `pack pull` git path.
- [ ] Boot the documented compose deploy once against a real Postgres and record the
  evidence: Alembic baseline applied, repository registered, worker-claimed scan
  succeeded, findings with remediation payloads listed, SARIF export parity with the
  CLI, suppression create/list/patch. (Completed locally on 2026-09-02 during the
  v1 platform merge review; repeat on the release image and record the run.)
- [ ] Review final wheel/sdist contents and checksums, including the dashboard
  static assets, before approving the PyPI deployment.
- [ ] Confirm PyPI trusted publishing completed for `1.0.0b1` and record the wheel
  and sdist SHA-256 values.
- [ ] Record provider smoke or note it as not executed for this release; the offline
  deterministic and round-trip gates are the accuracy-neutral release floor.

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

- [x] `conformdag fix --path . --policy-pack policies/pack.yaml` dry-run writes nothing and
  exits `0` (user guide: Deterministic fixes).
- [x] Round-trip gate: the benchmark's autofix violation population (inject violations,
  run the fix engine, assert a clean re-scan) passes via
  `tests/test_roundtrip.py::test_roundtrip_gate_fixes_every_autofix_violation_case` over
  the 240-case synthetic corpus; a regression fails the build.

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

- [x] Run the updated real Docker smoke job for the maintained 3.3.0 profile after this
  release-scope change. The tag workflow's `Validate Airflow 3.3.0 image` job
  (pre-publication image build, smoke, and Trivy scan) succeeded in release run
  [#5](https://github.com/parthmule28/conformdag/actions/runs/30715005648) on 2026-08-01.
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
- [x] Merge the reviewed release-preparation pull request, then create and push
  `v0.1.0-beta.1` from that exact `main` commit. The reviewed remediation PRs #5-#9 were
  merged first, and the tag points at `f030065`, the exact resulting `main` commit.
- [x] Confirm the tag workflow's attestations, image SBOMs, and high/critical image scan
  results before approving the final PyPI deployment. All attestation and image jobs in
  release run [#5](https://github.com/parthmule28/conformdag/actions/runs/30715005648)
  succeeded, the published GHCR index carries an `attestation-manifest` entry, and the
  pre-publication Trivy gate passed with the documented allowlist. PyPI trusted publishing
  completed at 2026-08-01T20:38Z (wheel `0.1.0b1` SHA-256 `4967f7b7...746f821`, sdist
  SHA-256 `4ff90635...c2556b8ee08`). The Trivy gate ignores only findings
  with no upstream fixed version; fixed high/critical findings remain blocking except for
  the three documented Jackson CVEs in Ray's shaded `ray_dist.jar`, which are temporarily
  allowlisted because the required Airflow Google provider has no published Ray build with
  the patched Jackson dependency.
- [x] After publication, confirm the GHCR 3.3.0 runtime package is public and can be
  pulled anonymously; the supported `scan --runtime` profile depends on anonymous digest
  resolution. Confirmed 2026-08-29 by fetching an anonymous pull token and the
  `v0.1.0-beta.1` manifest from `ghcr.io/parthmule28/conformdag/airflow-3.3.0` with no
  credentials (HTTP 200); the OCI index digest is
  `sha256:b78c44154bc0112c2be67746ba70eef66a0f3c9b34b8ad43b398837f74f72481` for
  `linux/amd64`.

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
