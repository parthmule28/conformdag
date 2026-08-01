# Architecture

ConformDAG is a modular Python CLI. Its default path reads files but never imports or
executes repository Python. Optional execution and network boundaries must be selected
explicitly.

## Scan flow

1. Configuration is resolved from CLI options, `conformdag.yaml`, environment-only
   secrets, and package defaults, in that order.
2. The policy pack and its linked standards-document hashes are validated.
3. Included Python files are discovered without following external symlinks and parsed
   into typed source models with the standard-library AST.
4. Registry-backed deterministic evaluators produce normalized findings.
5. If requested, Docker runtime observations and/or semantic findings are added.
6. Suppressions are validated and applied, then the report is sorted and fingerprinted.
7. JSON is the canonical report. Terminal, SARIF, and HTML are projections of it.

The code favors typed data models and small, mostly pure transformation functions. It
is not a strictly functional architecture: provider, filesystem, Docker, and CLI
adapters isolate side effects at explicit boundaries.

## Policy model

A policy contract contains a stable ID, version, lifecycle state, owner, provenance,
scope, invariant, remediation, enforcement type, exception rules, and typed
configuration. Deterministic evaluator classes implement a common protocol and are
registered by policy ID. Semantic policy-specific instructions are centralized beside
the semantic evaluator. This keeps policy contracts readable while making unsupported
or duplicate implementations detectable by validation and tests.

Policy authors define the organizational contract; ConformDAG enforces its schema and
execution rules. The beta CLI does not implement multi-user authorization. Role fields
are audit metadata that prepare for a later collaborative service.

## Runtime boundary

Runtime mode validates a manifest on the host, pulls the selected ConformDAG profile,
resolves it to an immutable registry digest, and invokes Docker without a shell. The
container receives a read-only repository mount, no network, a read-only root
filesystem, a non-root user, no Linux capabilities, `no-new-privileges`, and bounded
CPU, memory, process, temporary-storage, and wall-clock resources. It imports DAGs only
inside the container and returns versioned observations.

This is defense in depth, not a complete sandbox. The Docker daemon remains a trusted
host dependency. Custom images must be supplied by digest and are outside the supported
profile compatibility guarantee.

## Semantic boundary

Semantic mode is disabled by default and requires an explicit endpoint, exact model ID,
and API key supplied through an environment variable. Before a request leaves the host,
ConformDAG selects bounded source context, redacts credential-like values, and places all
repository content inside an untrusted-evidence delimiter. Tools are not exposed to the
model. Responses must match the strict `SemanticResponse` schema.

The cache stores only validated normalized responses keyed by policy contract,
enforcement, prompt, response schema, context, model, and evaluation configuration.
Reports retain hashes, model identity, token usage, retries, latency, cache state, and
pricing provenance, but not API keys or raw provider payloads.

## Failure model

Exit `0` means a complete run without blocking failures; `1` means a complete policy
failure; `2` means invalid input or configuration; and `3` means an incomplete phase or
operational failure. Runtime import errors and provider failures are structured report
issues rather than unhandled tracebacks.
