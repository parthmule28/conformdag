# Beta release checklist

The public beta is released only from the reviewed `v0.1.0-beta.1` tag. The
release workflow publishes the Python package through PyPI trusted publishing
and publishes both immutable Airflow runtime profiles to GHCR. It also emits
distribution checksums, build provenance, image SBOMs, and high/critical
vulnerability results.

Before creating the tag:

1. Confirm the GitHub repository, PyPI project name, and trademark/confusability
   review for `ConformDAG` are complete.
2. Confirm the `pypi` GitHub environment is configured for the repository and
   that PyPI trusted publishing is scoped to this repository and workflow.
3. Confirm `main` is protected and requires the Fast checks, Offline benchmark
   gate, Release validation, and both Airflow runtime checks.
4. Run the clean-environment acceptance suite on Linux and macOS and retain the
   reports as release evidence.
5. Verify the deterministic per-policy and aggregate benchmark gates, then
   document semantic baseline measurements and known limitations.

The workflow deliberately has no PyPI token or GHCR password. GitHub's OIDC
identity is used for PyPI, and the scoped `GITHUB_TOKEN` is used for GHCR.
