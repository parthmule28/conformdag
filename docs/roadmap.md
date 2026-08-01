# Roadmap

## Beta foundation

- [x] Bootstrap the Python/mise project and public schemas.
- [x] Implement six deterministic Airflow policies and canonical report formats.
- [x] Add constrained Airflow 2.11.2 and 3.3.0 runtime profiles.
- [x] Wire opt-in BYOK semantic evaluation for four semantic policies.
- [x] Build a 240-case deterministic benchmark and CI release gates.
- [x] Configure protected-main review, PyPI trusted publishing, and staged release jobs.
- [x] Record provider-backed integration measurements and semantic accuracy limitations.
- [ ] Publish `0.1.0b1` after all release evidence is reviewed.

## Planned follow-up

- Interactive policy authoring and validation from standards documents.
- Git-based synchronization of signed/versioned policy bundles.
- A centralized dashboard for collaboration, audit history, exceptions, and monitoring.
- dbt support after the Airflow quality and demand gates pass.
- Additional exporters and repository integrations.

The local CLI remains fully usable without the future online service. Multi-user roles
and permissions belong to that service, not to the beta CLI.
