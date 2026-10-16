"""Baseline characterization tests for the canonical SARIF projection."""

import json
from typing import cast

from conformdag.reporting import render_sarif

from .fixtures import fixed_report

EXPECTED_SARIF_JSON = """
{"$schema":"https://json.schemastore.org/sarif-2.1.0.json","runs":[{"automationDetails":{"id":"seed-result-fingerprint"},"results":[{"level":"error","locations":[{"physicalLocation":{"artifactLocation":{"uri":"dags/b.py"},"region":{"startLine":12}}}],"message":{"text":"password=[REDACTED] <unsafe>"},"properties":{"fingerprint":"fp-b-suppressed","status":"FAIL","suppressed":true},"ruleId":"B-POLICY","suppressions":[{"justification":"external suppression","kind":"external"}]},{"level":"error","locations":[{"physicalLocation":{"artifactLocation":{"uri":"dags/a.py"},"region":{"startLine":7}}}],"message":{"text":"Bearer [REDACTED]"},"properties":{"fingerprint":"fp-a-error","status":"ERROR","suppressed":false},"ruleId":"A-POLICY"},{"level":"note","locations":[{"physicalLocation":{"artifactLocation":{"uri":"dags/b.py"},"region":{"startLine":12}}}],"message":{"text":"tie <b>& explanation"},"properties":{"fingerprint":"fp-b-tie","status":"FAIL","suppressed":false},"ruleId":"B-POLICY"},{"level":"warning","locations":[{"physicalLocation":{"artifactLocation":{"uri":"dags/m.py"},"region":{"startLine":20}}}],"message":{"text":"medium <m>& explanation"},"properties":{"fingerprint":"fp-m-fail","status":"FAIL","suppressed":false},"ruleId":"M-POLICY"}],"tool":{"driver":{"name":"ConformDAG","rules":[{"help":{"text":"credential=[REDACTED]"},"id":"B-POLICY","shortDescription":{"text":"B-POLICY"}},{"help":{"text":"no action"},"id":"Z-PASS","shortDescription":{"text":"Z-PASS"}},{"help":{"text":"token=[REDACTED]"},"id":"A-POLICY","shortDescription":{"text":"A-POLICY"}},{"help":{"text":"review medium finding"},"id":"M-POLICY","shortDescription":{"text":"M-POLICY"}}],"version":"fixture-tool-1.0"}}}],"version":"2.1.0"}
"""


def test_render_sarif_matches_frozen_canonical_dict_and_wire_bytes() -> None:
    report = fixed_report()
    expected = json.loads(EXPECTED_SARIF_JSON)

    rendered = render_sarif(report)

    assert rendered == expected
    assert (
        json.dumps(rendered, indent=2, sort_keys=True) + "\n" == json.dumps(expected, indent=2, sort_keys=True) + "\n"
    )


def test_render_sarif_keeps_pass_rules_without_pass_results_and_preserves_rule_order() -> None:
    rendered = render_sarif(fixed_report())
    runs = cast(list[dict[str, object]], rendered["runs"])
    run = runs[0]
    tool = cast(dict[str, object], run["tool"])
    driver = cast(dict[str, object], tool["driver"])
    rules = cast(list[dict[str, object]], driver["rules"])
    assert [rule["id"] for rule in rules] == [
        "B-POLICY",
        "Z-PASS",
        "A-POLICY",
        "M-POLICY",
    ]
    results = cast(list[dict[str, object]], run["results"])
    assert all(result["ruleId"] != "Z-PASS" for result in results)


def test_render_sarif_redacts_sensitive_free_text_without_mutating_report() -> None:
    report = fixed_report()
    before = report.model_dump(mode="json")

    rendered = render_sarif(report)
    serialized = json.dumps(rendered)

    assert report.model_dump(mode="json") == before
    for secret in (
        "fixture-explanation",
        "fixture-remediation",
        "fixture-evidence",
        "fixture-bearer",
        "fixture-token-remediation",
        "fixture-secret-evidence",
    ):
        assert secret not in serialized
