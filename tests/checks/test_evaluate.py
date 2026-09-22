"""Direct characterization tests for deterministic routing orchestration."""

from conformdag.checks.evaluate import evaluate_deterministic


def test_deterministic_orchestration_handles_an_empty_policy_set() -> None:
    findings, evaluated, skipped = evaluate_deterministic([], [])

    assert findings == []
    assert evaluated == []
    assert skipped == []
