"""Agent harness tests: triage, verifier, PR flow, and policy review."""

import json
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from conformdag.agent import (
    AgentSettings,
    PrClient,
    Verifier,
    VerifierRequest,
    aggregate_reports,
    draft_proposal,
    load_reports,
    proposal_json,
    run_agent_pipeline,
    triage_report,
)
from conformdag.agent.verifier import VerdictError
from conformdag.models import RunIssue, RunMetadata, ScanReport
from conformdag.scan import scan_repository


def _verdict_content(verdict: str) -> str:
    return json.dumps(
        {
            "verdict": verdict,
            "reason_code": "no-semantic-change",
            "confidence": "high",
            "reasons": ["mechanical kwarg additions only"],
            "concerns": [],
        }
    )


def _chat_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _verifier_transport(verdict: str) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: _chat_response(_verdict_content(verdict)))


def _invalid_verifier_transport(calls: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _chat_response(json.dumps({"oops": True}))

    return httpx.MockTransport(handler)


def _capturing_verifier_transport(captured: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        captured.append(str(body["messages"][-1]["content"]))
        return _chat_response(_verdict_content("approve"))

    return httpx.MockTransport(handler)


def _pr_transport(calls: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = json.loads(request.content.decode("utf-8"))
        assert "Merging is a human action" in body["body"]
        return httpx.Response(201, json={"html_url": "https://github.com/acme/repo/pull/1"})

    return httpx.MockTransport(handler)


def _pr_transport_never_called() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("PR client must not be called when the verifier rejects")

    return httpx.MockTransport(handler)


def test_triage_splits_fixable_from_manual(build_repository: Callable[[Path], Path], tmp_path: Path) -> None:
    root = build_repository(tmp_path)
    report = scan_repository(root, root / "policies/pack.yaml")

    triage = triage_report(report)

    assert {item.policy_id for item in triage.fixable} == {
        "AIR-DET-001",
        "AIR-DET-002",
        "AIR-DET-003",
        "AIR-DET-004",
    }
    assert triage.manual == []
    assert all(":airflow" not in item.file_path for item in triage.fixable)


def test_verifier_approves_and_caches(build_repository: Callable[[Path], Path], tmp_path: Path) -> None:
    root = build_repository(tmp_path)
    before = scan_repository(root, root / "policies/pack.yaml")
    outcome = run_agent_pipeline(root, root / "policies/pack.yaml")
    after = scan_repository(root, root / "policies/pack.yaml")
    cache_path = tmp_path / "verdict-cache.json"
    verifier = Verifier(
        "https://verifier.test/api",
        "key",
        VerifierRequest(model="verifier-model"),
        cache_path=cache_path,
        transport=_verifier_transport("approve"),
    )

    verdict = verifier.verify(outcome.diff, before, after)
    verifier.close()

    assert verdict.verdict == "approve"
    assert cache_path.is_file()
    assert "approve" in cache_path.read_text(encoding="utf-8")

    def second_call_handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("cached verdict must not call the provider again")

    cached_verifier = Verifier(
        "https://verifier.test/api",
        "key",
        VerifierRequest(model="verifier-model"),
        cache_path=cache_path,
        transport=httpx.MockTransport(second_call_handler),
    )
    cached_verdict = cached_verifier.verify(outcome.diff, before, after)
    cached_verifier.close()
    assert cached_verdict.verdict == "approve"


def test_verifier_reject_blocks_pr(build_repository: Callable[[Path], Path], tmp_path: Path) -> None:
    root = build_repository(tmp_path)
    verifier = Verifier(
        "https://verifier.test/api",
        "key",
        VerifierRequest(model="m"),
        transport=_verifier_transport("reject"),
    )
    pull_requests = PrClient(token="t", repo="acme/repo", transport=_pr_transport_never_called())

    outcome = run_agent_pipeline(root, root / "policies/pack.yaml", verifier=verifier, pull_requests=pull_requests)
    verifier.close()

    assert outcome.blocked
    assert outcome.verdict is not None and outcome.verdict.verdict == "reject"
    assert outcome.pull_request_url is None


def test_verifier_invalid_schema_raises_after_attempts(
    build_repository: Callable[[Path], Path], tmp_path: Path
) -> None:
    root = build_repository(tmp_path)
    before = scan_repository(root, root / "policies/pack.yaml")
    calls: list[httpx.Request] = []
    verifier = Verifier(
        "https://verifier.test/api",
        "key",
        VerifierRequest(model="m", max_attempts=2),
        transport=_invalid_verifier_transport(calls),
    )

    with pytest.raises(VerdictError, match="schema-valid"):
        verifier.verify("unified diff", before, before)
    verifier.close()
    assert len(calls) == 2


def test_verifier_redacts_credentials(build_repository: Callable[[Path], Path], tmp_path: Path) -> None:
    root = build_repository(tmp_path)
    before = scan_repository(root, root / "policies/pack.yaml")
    after = scan_repository(root, root / "policies/pack.yaml")
    captured: list[str] = []
    verifier = Verifier(
        "https://verifier.test/api",
        "key",
        VerifierRequest(model="m"),
        transport=_capturing_verifier_transport(captured),
    )

    verifier.verify("PASSWORD = 'hunter2'", before, after)
    verifier.close()

    assert captured and "hunter2" not in captured[0]
    assert "[REDACTED]" in captured[0]


def test_pipeline_opens_pr_after_approval(build_repository: Callable[[Path], Path], tmp_path: Path) -> None:
    root = _git_repo(build_repository(tmp_path))
    pr_calls: list[httpx.Request] = []
    pull_requests = PrClient(token="t", repo="acme/repo", transport=_pr_transport(pr_calls))
    verifier = Verifier(
        "https://verifier.test/api",
        "key",
        VerifierRequest(model="m"),
        transport=_verifier_transport("approve"),
    )

    outcome = run_agent_pipeline(root, root / "policies/pack.yaml", verifier=verifier, pull_requests=pull_requests)
    verifier.close()

    assert outcome.changed
    assert outcome.verdict is not None and outcome.verdict.verdict == "approve"
    assert outcome.pull_request_url == "https://github.com/acme/repo/pull/1"
    assert len(pr_calls) == 1
    body = json.loads(pr_calls[0].content.decode("utf-8"))
    assert "AIR-DET-" in body["body"]
    pushed = _git_output(root, ["branch", "-r"])
    assert "origin/conformdag/fix" in pushed


def test_pipeline_without_pr_client_applies_locally(build_repository: Callable[[Path], Path], tmp_path: Path) -> None:
    root = build_repository(tmp_path)

    outcome = run_agent_pipeline(root, root / "policies/pack.yaml")

    assert outcome.changed
    assert outcome.pull_request_url is None
    assert 'owner="analytics"' in (root / "dags/violations.py").read_text(encoding="utf-8")


def test_pr_body_carries_evidence(build_repository: Callable[[Path], Path], tmp_path: Path) -> None:
    root = build_repository(tmp_path)
    outcome = run_agent_pipeline(root, root / "policies/pack.yaml")

    body = outcome.pr_body("acme/repo")

    assert "## Findings fixed" in body
    assert "AIR-DET-00" in body
    assert "Deterministic re-scan: clean" in body
    assert "Merging is a human action" in body


def test_policy_review_aggregates_reports(tmp_path: Path) -> None:
    first = tmp_path / "one.json"
    second = tmp_path / "two.json"
    for index, path in enumerate((first, second)):
        path.write_text(
            ScanReport(
                complete=True,
                result_fingerprint=f"{index:064x}",
                run=_run_metadata(),
            ).model_dump_json(),
            encoding="utf-8",
        )

    aggregate = aggregate_reports(load_reports([first, second]))
    proposal = draft_proposal(aggregate, "org-pack")

    assert aggregate.report_count == 2
    assert aggregate.stale_suppression_codes == 0
    assert "Policy pack review proposal (org-pack)" in proposal
    assert "Aggregated over 2 scan(s)" in proposal


def test_agent_settings_fail_fast_lists_all_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "CONFORMDAG_AGENT_BASE_URL",
        "CONFORMDAG_AGENT_MODEL",
        "CONFORMDAG_MODEL_API_KEY",
        "CONFORMDAG_GITHUB_TOKEN",
        "CONFORMDAG_GITHUB_REPO",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValueError, match="CONFORMDAG_AGENT_BASE_URL.*CONFORMDAG_GITHUB_REPO"):
        AgentSettings.from_environment()


def test_cli_policy_review_renders_proposal(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text(
        ScanReport(complete=True, result_fingerprint="e" * 64, run=_run_metadata()).model_dump_json(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(_cli_app(), ["agent", "policy-review", str(report_path), "--pack-id", "acme-pack"])

    assert result.exit_code == 0
    assert "Policy pack review proposal (acme-pack)" in result.stdout


def _cli_app():
    from conformdag.cli import app

    return app


def _run_metadata() -> RunMetadata:
    return RunMetadata(
        tool_version="test",
        policy_pack_id="pack",
        policy_pack_version="1.0.0",
        timestamp=datetime.now(UTC),
    )


def _git_repo(root: Path) -> Path:
    remote = root.parent / f"{root.name}-remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True, capture_output=True)
    steps: list[list[str]] = [
        ["init", "-q"],
        ["config", "user.email", "agent@example.com"],
        ["config", "user.name", "ConformDAG Agent"],
        ["add", "-A"],
        ["commit", "-m", "baseline", "--allow-empty"],
        ["remote", "add", "origin", str(remote)],
        ["push", "-q", "-u", "origin", "HEAD:refs/heads/main"],
    ]
    for arguments in steps:
        subprocess.run(["git", *arguments], cwd=root, capture_output=True, check=True)
    return root


def _git_output(root: Path, arguments: list[str]) -> str:
    completed = subprocess.run(["git", *arguments], cwd=root, capture_output=True, text=True, check=True)
    return completed.stdout.strip()


def _finding_with_status(status: str, suppressed: bool, policy_id: str = "AIR-DET-001"):
    from conformdag.models import (
        EnforcementType,
        Finding,
        FindingEvidence,
        FindingLocation,
        FindingStatus,
        Severity,
    )

    return Finding(
        policy_id=policy_id,
        policy_version="1.0.0",
        status=FindingStatus(status),
        severity=Severity.HIGH,
        enforcement=EnforcementType.DETERMINISTIC,
        location=FindingLocation(file=Path("dags/x.py"), start_line=1, end_line=1),
        evidence=FindingEvidence(text="evidence"),
        explanation="explanation",
        fingerprint="f" * 64,
        suppressed=suppressed,
    )


def test_policy_review_aggregates_failures_and_suppressions(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    report = ScanReport(
        complete=True,
        result_fingerprint="f" * 64,
        run=RunMetadata(
            tool_version="t",
            policy_pack_id="p",
            policy_pack_version="1",
            timestamp=datetime.now(UTC),
        ),
        issues=[RunIssue(code="SUPPRESSION_EXPIRED", message="expired", phase="suppression")],
    )
    report = report.model_copy(
        update={
            "findings": [
                _finding_with_status("FAIL", False, "AIR-DET-001"),
                _finding_with_status("FAIL", True, "AIR-DET-002"),
                _finding_with_status("PASS", False, "AIR-DET-003"),
            ]
        }
    )
    path = tmp_path / "report.json"
    path.write_text(report.model_dump_json(), encoding="utf-8")

    aggregate = aggregate_reports(load_reports([path]))

    assert aggregate.fail_counts == {"AIR-DET-001": 1}
    assert aggregate.suppression_counts == {"AIR-DET-002": 1}
    assert aggregate.stale_suppression_codes == 1
    assert aggregate.suppression_rate("AIR-DET-002") == 0.0

    proposal = draft_proposal(aggregate, "acme")
    assert "`AIR-DET-002`: 1 suppression(s) (0% of unsuppressed failures)" in proposal
    assert "`AIR-DET-001`: 1 failing finding(s)" in proposal
    assert json.loads(proposal_json(aggregate))["fail_counts"]["AIR-DET-001"] == 1


def test_verifier_cache_survives_corrupt_file(build_repository: Callable[[Path], Path], tmp_path: Path) -> None:
    root = build_repository(tmp_path)
    before = scan_repository(root, root / "policies/pack.yaml")
    outcome = run_agent_pipeline(root, root / "policies/pack.yaml")
    after = scan_repository(root, root / "policies/pack.yaml")
    cache_path = tmp_path / "corrupt-cache.json"
    cache_path.write_text("{not json", encoding="utf-8")
    verifier = Verifier(
        "https://verifier.test/api",
        "key",
        VerifierRequest(model="m"),
        cache_path=cache_path,
        transport=_verifier_transport("approve"),
    )

    verdict = verifier.verify(outcome.diff, before, after)
    verifier.close()

    assert verdict.verdict == "approve"
    assert "approve" in cache_path.read_text(encoding="utf-8")


def test_agent_settings_without_verifier_needs_github_only(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "CONFORMDAG_AGENT_BASE_URL",
        "CONFORMDAG_AGENT_MODEL",
        "CONFORMDAG_MODEL_API_KEY",
        "CONFORMDAG_GITHUB_TOKEN",
        "CONFORMDAG_GITHUB_REPO",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CONFORMDAG_GITHUB_TOKEN", "t")
    monkeypatch.setenv("CONFORMDAG_GITHUB_REPO", "acme/repo")

    settings = AgentSettings.from_environment(require_verifier=False, require_github=True)

    assert settings.github_repo == "acme/repo"
    assert settings.base_branch == "main"


def test_cli_policy_review_writes_json_output(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    report_path = tmp_path / "report.json"
    report_path.write_text(
        ScanReport(
            complete=True,
            result_fingerprint="9" * 64,
            run=RunMetadata(
                tool_version="t",
                policy_pack_id="p",
                policy_pack_version="1",
                timestamp=datetime.now(UTC),
            ),
        ).model_dump_json(),
        encoding="utf-8",
    )
    output_path = tmp_path / "proposal.json"

    result = CliRunner().invoke(
        _cli_app(),
        [
            "agent",
            "policy-review",
            str(report_path),
            "--format",
            "json",
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["report_count"] == 1
