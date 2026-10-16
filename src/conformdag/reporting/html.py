"""Canonical self-contained HTML projection for scan reports."""

from __future__ import annotations

from jinja2 import Environment, select_autoescape

from conformdag.models import ScanReport
from conformdag.security.redaction import redact_credentials


def render_html(report: ScanReport, include_evidence: bool = True) -> str:
    """Render a self-contained offline HTML report with accessible table markup."""
    template = Environment(
        autoescape=select_autoescape(default=True),
        trim_blocks=True,
        lstrip_blocks=True,
    ).from_string(
        """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ConformDAG report</title><style>
body{font-family:system-ui,sans-serif;margin:2rem;color:#202124}
table{border-collapse:collapse;width:100%}
th,td{border:1px solid #bbb;padding:.5rem;text-align:left;vertical-align:top}
th{background:#eee}.evidence{font-family:monospace;margin-top:.4rem;white-space:pre-wrap}
.PASS{color:#176b2c}.FAIL{color:#a20d0d}.NEEDS_REVIEW{color:#7a4b00}
</style></head><body>
<h1>ConformDAG report</h1>
<p>Complete: {{ report.complete }}; Result fingerprint:
<code>{{ report.result_fingerprint }}</code></p>
<table><caption>Policy findings</caption><thead><tr>
<th scope="col">Policy</th><th scope="col">Status</th><th scope="col">Severity</th>
<th scope="col">Location</th><th scope="col">Explanation</th>
</tr></thead><tbody>
{% for finding in report.findings %}<tr>
<td>{{ finding.policy_id }}</td>
<td class="{{ finding.status.value }}">{{ finding.status.value }}</td>
<td>{{ finding.severity.value }}</td><td>{{ finding.location.file or "" }}</td>
<td>{{ redact_credentials(finding.explanation or "") }}{% if include_evidence and finding.evidence %}
<div class="evidence">{{ redact_credentials(finding.evidence.text) }}</div>{% endif %}</td>
</tr>{% endfor %}
</tbody></table></body></html>
"""
    )
    return template.render(report=report, include_evidence=include_evidence, redact_credentials=redact_credentials)
