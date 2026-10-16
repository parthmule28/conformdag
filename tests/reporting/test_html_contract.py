"""Baseline characterization tests for the self-contained HTML projection."""

import hashlib

from conformdag.reporting import render_html

from .fixtures import fixed_report

EXPECTED_HTML_TRUE_SHA256 = "362d8a26d101b2777e48760e51e54d001ae048b0acf563028c46208063e7a411"
EXPECTED_HTML_FALSE_SHA256 = "60ea8b57ba97818116cff42a984342ad19664191c9553fd260df05dcf4090374"


def test_render_html_matches_frozen_full_output_for_both_evidence_modes() -> None:
    report = fixed_report()
    with_evidence = render_html(report, include_evidence=True)
    without_evidence = render_html(report, include_evidence=False)

    assert hashlib.sha256(with_evidence.encode("utf-8")).hexdigest() == EXPECTED_HTML_TRUE_SHA256
    assert hashlib.sha256(without_evidence.encode("utf-8")).hexdigest() == EXPECTED_HTML_FALSE_SHA256
    assert len(with_evidence) == 1745
    assert len(without_evidence) == 1515
    assert with_evidence != without_evidence


def test_render_html_escapes_and_redacts_text_and_toggles_evidence() -> None:
    report = fixed_report()
    with_evidence = render_html(report)
    without_evidence = render_html(report, include_evidence=False)

    assert "tie &lt;b&gt;&amp; explanation" in with_evidence
    assert "medium &lt;m&gt;&amp; explanation" in with_evidence
    assert "api_key=[REDACTED] &lt;unsafe&gt;" in with_evidence
    assert "api_key=[REDACTED] &lt;unsafe&gt;" not in without_evidence
    for secret in (
        "fixture-explanation",
        "fixture-remediation",
        "fixture-evidence",
        "fixture-bearer",
        "fixture-token-remediation",
        "fixture-secret-evidence",
    ):
        assert secret not in with_evidence
        assert secret not in without_evidence
    assert '<th scope="col">Policy</th>' in with_evidence


def test_render_html_does_not_mutate_report() -> None:
    report = fixed_report()
    before = report.model_dump(mode="json")

    render_html(report)

    assert report.model_dump(mode="json") == before
