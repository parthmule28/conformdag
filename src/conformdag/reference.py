"""Human- and machine-readable CLI reference data."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReferenceEntry:
    key: str
    meaning: str
    behavior: str


OUTCOME_REFERENCE = (
    ReferenceEntry(
        "PASS", "The selected policy was evaluated and no violation was found.", "Non-blocking."
    ),
    ReferenceEntry(
        "FAIL",
        "The selected policy was evaluated and a violation was found.",
        "Blocks for deterministic checks and semantic policies marked blocking.",
    ),
    ReferenceEntry(
        "NEEDS_REVIEW",
        "The available evidence was insufficient or uncertain.",
        "Non-blocking advisory outcome.",
    ),
    ReferenceEntry(
        "NOT_APPLICABLE",
        "The policy does not apply to the selected source or profile.",
        "Non-blocking.",
    ),
    ReferenceEntry(
        "SKIPPED",
        "The policy or phase was intentionally not evaluated.",
        "The report may be incomplete.",
    ),
    ReferenceEntry(
        "ERROR",
        "The evaluation could not complete reliably.",
        "The report is incomplete; exit status 3.",
    ),
)

EXIT_CODE_REFERENCE = (
    ReferenceEntry("0", "Complete run with no unsuppressed blocking failures.", "Success."),
    ReferenceEntry(
        "1",
        "Complete run with an unsuppressed blocking policy failure.",
        "Conformance failure.",
    ),
    ReferenceEntry(
        "2", "Invalid command, configuration, or policy input.", "Usage/configuration error."
    ),
    ReferenceEntry(
        "3",
        "Required evaluation phase failed or the report is incomplete.",
        "Execution/incompleteness error.",
    ),
)

RUNTIME_REFERENCE = (
    ReferenceEntry(
        "manifest",
        "Validated host-to-container execution contract.",
        "Contains repository, paths, policy IDs, profile/image, and limits.",
    ),
    ReferenceEntry(
        "supported profile",
        "Pinned Airflow 2.11.2 legacy or 3.3.0 maintained runtime.",
        "Network is rejected and containment controls are mandatory.",
    ),
    ReferenceEntry(
        "custom image",
        "Explicit user-supplied runtime image.",
        "Digest and outside-benchmark status are recorded.",
    ),
    ReferenceEntry(
        "runtime failure",
        "Docker, import, limit, containment, or output failure.",
        "Never interpreted as policy success.",
    ),
)

REPORT_REFERENCE = (
    ReferenceEntry(
        "terminal", "Human triage summary.", "Printed to the terminal; diagnostics remain separate."
    ),
    ReferenceEntry(
        "json", "Canonical machine-readable report.", "Suitable for agents and automation."
    ),
    ReferenceEntry(
        "sarif",
        "SARIF 2.1.0 code-scanning report.",
        "Maps canonical findings to code-scanning consumers.",
    ),
    ReferenceEntry(
        "html", "Self-contained offline report.", "Requires an explicit output path and no network."
    ),
)
