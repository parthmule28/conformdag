# Contributing to ConformDAG

Contributions are welcome through GitHub pull requests.

## Development setup

Use mise for the project toolchain and tasks:

    mise install
    mise run setup
    mise run check

Run the focused checks relevant to a change before opening a pull request:

    mise run lint
    mise run format-check
    mise run typecheck
    mise run test

Runtime and Docker changes should also be tested with the appropriate
mise run test:runtime task when Docker is available.

## Change process

1. Open an issue or explain the problem in the pull request.
2. Keep changes focused and update tests and documentation together.
3. Use Conventional Commits, for example feat: add policy reference output.
4. Do not commit credentials, private organizational DAGs, provider responses,
   generated cache files, or local runtime manifests.
5. Commit OpenSpec planning artifacts (`openspec/`) with the change they
   describe. Do not commit `.cursor/`.

Pull requests require one approving review, resolved discussions, and passing
required checks before merge. The main branch is the protected integration
branch.

## Policy and schema changes

Policy behavior, response schemas, report schemas, cache keys, and benchmark
labels are compatibility-sensitive. Explain versioning and migration impact in
the pull request. Deterministic behavior changes require a policy version
change; semantic contract or prompt changes require semantic versioning and
cache/benchmark invalidation review.
