# DAG Authoring Standards

## Ownership and metadata

Every DAG declares an approved owner and required metadata so operational responsibility is
discoverable without executing the DAG.

## Execution safety

Tasks use bounded timeouts and retries, avoid module-scope I/O, and use approved operators and
imports for the selected Airflow runtime profile.

## Semantic review

Idempotence, orchestration boundaries, sensitive logging, and approved abstractions are reviewed
with redacted evidence and may abstain when the source is ambiguous.
