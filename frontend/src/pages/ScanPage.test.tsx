/**
 * Scan detail journeys: header summary, recorded gate results, run issues,
 * runtime observations, server-backed finding investigation, exports, and
 * artifact-unavailable states. Client functions are mocked; TanStack Query
 * runs for real so polling, invalidation, and error mapping are exercised.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import {
  ApiError,
  cancelScan,
  findings,
  getScanReport,
  getScanStatus,
  type Finding,
  type GateResult,
  type Page,
  type ReportFinding,
  type ScanReport,
  type ScanStatus,
} from "../api";
import { ACTIVE_POLL_INTERVAL_MS } from "../hooks/usePlatformQueries";
import ScanPage from "./ScanPage";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    cancelScan: vi.fn(),
    findings: vi.fn(),
    getScanReport: vi.fn(),
    getScanStatus: vi.fn(),
  };
});

const cancelScanMock = vi.mocked(cancelScan);
const findingsMock = vi.mocked(findings);
const getScanReportMock = vi.mocked(getScanReport);
const getScanStatusMock = vi.mocked(getScanStatus);

const SCAN_COMPLETED: ScanStatus = {
  scan_id: "scan-1",
  repository_id: "repo-1",
  status: "succeeded",
  created_at: "2026-09-17T08:00:00Z",
  finished_at: "2026-09-17T08:02:00Z",
  complete: true,
  result_fingerprint: "fp-abc",
  error: null,
  gate_passed: true,
};

const SCAN_INCOMPLETE: ScanStatus = {
  scan_id: "scan-2",
  repository_id: "repo-1",
  status: "failed",
  created_at: "2026-09-17T09:00:00Z",
  finished_at: "2026-09-17T09:01:00Z",
  complete: false,
  result_fingerprint: "fp-def",
  error: "scan incomplete: parse-error: dags/broken.py could not be parsed",
  gate_passed: null,
};

const SCAN_RUNNING: ScanStatus = {
  scan_id: "scan-3",
  repository_id: "repo-1",
  status: "running",
  created_at: "2026-09-17T10:00:00Z",
  finished_at: null,
  complete: null,
  result_fingerprint: null,
  error: null,
  gate_passed: null,
};

const SCAN_CANCELLED: ScanStatus = {
  scan_id: "scan-3",
  repository_id: "repo-1",
  status: "cancelled",
  created_at: "2026-09-17T10:00:00Z",
  finished_at: "2026-09-17T10:01:00Z",
  complete: null,
  result_fingerprint: null,
  error: null,
  gate_passed: null,
};

const GATE_RESULT: GateResult = {
  gate_id: "release-critical",
  passed: false,
  rules: [
    {
      rule_type: "max-severity",
      passed: false,
      detail: "1 failing finding at high",
      matching_findings: 1,
    },
    {
      rule_type: "no-new-findings",
      passed: true,
      detail: "0 new findings",
      matching_findings: 0,
    },
  ],
};

const REPORT_FINDING_FAIL: ReportFinding = {
  policy_id: "OWN-001",
  policy_version: "2",
  status: "FAIL",
  severity: "high",
  enforcement: "deterministic",
  location: { file: "dags/orders.py", start_line: 12, end_line: 20 },
  evidence: {
    text: 'dag = DAG("orders")',
    start_line: 12,
    end_line: 12,
    code_hash: "hash-1",
  },
  explanation: "DAG lacks an effective owner",
  remediation: "Declare owner on every DAG call",
  confidence: "deterministic",
  fix: { fix_kind: "codemod", action: "add-owner" },
  audit_evidence: [],
  fingerprint: "fp-own-1",
  blocking: true,
  suppressed: false,
  suppression: null,
};

const REPORT_FINDING_SUPPRESSED_ERROR: ReportFinding = {
  policy_id: "PARSE-002",
  policy_version: "1",
  status: "ERROR",
  severity: "high",
  enforcement: "deterministic",
  location: { file: "dags/legacy.py", start_line: 3, end_line: 9 },
  evidence: null,
  explanation: "DAG could not be parsed",
  remediation: "Fix the syntax error",
  confidence: "deterministic",
  fix: null,
  audit_evidence: [],
  fingerprint: "fp-err-1",
  blocking: false,
  suppressed: true,
  suppression: { reason: "known parser limitation", owner: "data-platform" },
};

const REPORT_COMPLETED: ScanReport = {
  report_version: "2",
  complete: true,
  result_fingerprint: "fp-abc",
  files_scanned: ["dags/orders.py", "dags/legacy.py"],
  policies_evaluated: ["OWN-001", "PARSE-002"],
  policies_skipped: [],
  findings: [REPORT_FINDING_FAIL, REPORT_FINDING_SUPPRESSED_ERROR],
  runtime_observations: [{ dag_id: "orders", workers: 2 }],
  issues: [
    {
      code: "parse-error",
      message: "unexpected indent",
      path: "dags/broken.py",
      phase: "parse",
      fatal: false,
    },
  ],
  gate_result: GATE_RESULT,
  run: { timestamp: "2026-09-17T08:00:00Z" },
};

const REPORT_INCOMPLETE: ScanReport = {
  report_version: "2",
  complete: false,
  result_fingerprint: "fp-def",
  files_scanned: ["dags/orders.py"],
  policies_evaluated: [],
  policies_skipped: ["OWN-001"],
  findings: [],
  runtime_observations: [],
  issues: [
    {
      code: "EVALUATION_ERROR",
      message: "policy OWN-001 raised",
      path: "dags/orders.py",
      phase: "evaluate",
      fatal: true,
    },
  ],
  gate_result: null,
  run: {},
};

const FINDING_FAIL: Finding = {
  policy_id: "OWN-001",
  policy_version: "2",
  status: "FAIL",
  severity: "high",
  file_path: "dags/orders.py",
  start_line: 12,
  end_line: 20,
  fingerprint: "fp-own-1",
  explanation: "DAG lacks an effective owner",
  remediation: "Declare owner on every DAG call",
  fix: { fix_kind: "codemod", action: "add-owner" },
  suppressed: false,
  baseline_status: "new",
};

const FINDING_SUPPRESSED_ERROR: Finding = {
  policy_id: "PARSE-002",
  policy_version: "1",
  status: "ERROR",
  severity: "high",
  file_path: "dags/legacy.py",
  start_line: 3,
  end_line: 9,
  fingerprint: "fp-err-1",
  explanation: "DAG could not be parsed",
  remediation: "Fix the syntax error",
  fix: null,
  suppressed: true,
  baseline_status: "existing",
};

const FINDING_ERROR_UNSUPPRESSED: Finding = {
  policy_id: "SCHED-004",
  policy_version: "1",
  status: "ERROR",
  severity: "high",
  file_path: "dags/schedules.py",
  start_line: 41,
  end_line: 44,
  fingerprint: "fp-err-2",
  explanation: "Schedule expression could not be evaluated",
  remediation: "Correct the cron expression",
  fix: null,
  suppressed: false,
  baseline_status: "new",
};

const FINDING_PASS_LOW: Finding = {
  policy_id: "DOC-003",
  policy_version: "4",
  status: "PASS",
  severity: "low",
  file_path: "dags/orders.py",
  start_line: 30,
  end_line: 30,
  fingerprint: "fp-doc-3",
  explanation: "DAG has a docstring",
  remediation: null,
  fix: null,
  suppressed: false,
  baseline_status: null,
};

const FINDINGS_PAGE: Page<Finding> = {
  total: 12,
  items: [
    FINDING_FAIL,
    FINDING_SUPPRESSED_ERROR,
    FINDING_ERROR_UNSUPPRESSED,
    FINDING_PASS_LOW,
  ],
};

const EMPTY_FINDINGS: Page<Finding> = { items: [], total: 0 };

function makeClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderScanPage(scanId: string): void {
  render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter initialEntries={[`/scans/${scanId}`]}>
        <Routes>
          <Route path="/scans/:scanId" element={<ScanPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function completedScanMocks(): void {
  getScanStatusMock.mockResolvedValue(SCAN_COMPLETED);
  getScanReportMock.mockResolvedValue(REPORT_COMPLETED);
  findingsMock.mockResolvedValue(FINDINGS_PAGE);
}

function gateRegion(): HTMLElement {
  return screen.getByRole("region", { name: "Gate result" });
}

async function findGateRegion(): Promise<HTMLElement> {
  return screen.findByRole("region", { name: "Gate result" });
}

function rowForFinding(policyId: string): HTMLElement {
  const row = screen
    .getByRole("button", { name: `Details for ${policyId}` })
    .closest("tr");
  if (row === null) {
    throw new Error(`finding ${policyId} has no table row`);
  }
  return row;
}

function ruleRowFor(ruleType: string): HTMLElement {
  const row = screen.getByText(ruleType).closest("tr");
  if (row === null) {
    throw new Error(`rule ${ruleType} has no table row`);
  }
  return row;
}

async function openDetail(policyId: string): Promise<HTMLElement> {
  fireEvent.click(screen.getByRole("button", { name: `Details for ${policyId}` }));
  const dialog = await screen.findByRole("dialog");
  await within(dialog).findByText(`Finding ${policyId}`);
  return dialog;
}

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ScanPage", () => {
  it("shows a loading state while scan status is in flight", () => {
    getScanStatusMock.mockReturnValue(new Promise(() => undefined));
    findingsMock.mockReturnValue(new Promise(() => undefined));
    renderScanPage("scan-1");
    expect(screen.getByRole("status")).toHaveTextContent("Loading scan");
  });

  it("renders the completed scan summary, recorded gate result, and exports", async () => {
    completedScanMocks();
    renderScanPage("scan-1");

    const summary = await screen.findByRole("region", { name: "Scan summary" });
    expect(within(summary).getByText("Succeeded")).toBeInTheDocument();
    expect(within(summary).getByText("PASS")).toBeInTheDocument();
    expect(within(summary).getByText("Complete")).toBeInTheDocument();
    expect(within(summary).getByText("2026-09-17 08:00 UTC")).toBeInTheDocument();
    expect(within(summary).getByText("2026-09-17 08:02 UTC")).toBeInTheDocument();
    expect(within(summary).getByText("fp-abc")).toBeInTheDocument();
    expect(
      within(summary).getByRole("link", { name: "repo-1" }),
    ).toHaveAttribute("href", "/repos/repo-1");

    const gate = gateRegion();
    expect(within(gate).getByText("release-critical")).toBeInTheDocument();
    expect(within(gate).getByText("Gate failed")).toBeInTheDocument();
    expect(within(ruleRowFor("max-severity")).getByText("FAIL")).toBeInTheDocument();
    expect(within(ruleRowFor("max-severity")).getByText("1 failing finding at high")).toBeInTheDocument();
    expect(within(ruleRowFor("max-severity")).getByText("1")).toBeInTheDocument();
    expect(within(ruleRowFor("no-new-findings")).getByText("PASS")).toBeInTheDocument();
    expect(within(ruleRowFor("no-new-findings")).getByText("0")).toBeInTheDocument();

    expect(screen.getByRole("link", { name: "JSON" })).toHaveAttribute(
      "href",
      "/api/v1/scans/scan-1/export/json",
    );
    expect(screen.getByRole("link", { name: "SARIF" })).toHaveAttribute(
      "href",
      "/api/v1/scans/scan-1/export/sarif",
    );
    expect(screen.getByRole("link", { name: "HTML" })).toHaveAttribute(
      "href",
      "/api/v1/scans/scan-1/export/html",
    );

    expect(screen.getByText(/scroll horizontally/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Run issues" })).toBeInTheDocument();
    expect(screen.getByText(/"dag_id": "orders"/)).toBeInTheDocument();
  });

  it("lists findings with suppression, baseline, and location, and opens a keyboard-accessible detail", async () => {
    completedScanMocks();
    renderScanPage("scan-1");

    await screen.findByText("OWN-001");

    const failRow = rowForFinding("OWN-001");
    expect(within(failRow).getByText("FAIL")).toBeInTheDocument();
    expect(within(failRow).getByText("high")).toBeInTheDocument();
    expect(within(failRow).getByText("dags/orders.py")).toBeInTheDocument();
    expect(within(failRow).getByText("12\u201320")).toBeInTheDocument();
    expect(within(failRow).getByText("Active")).toBeInTheDocument();
    expect(within(failRow).getByText("New")).toBeInTheDocument();
    expect(within(failRow).getByText("DAG lacks an effective owner")).toBeInTheDocument();

    const suppressedRow = rowForFinding("PARSE-002");
    expect(within(suppressedRow).getByText("SUPPRESSED")).toBeInTheDocument();
    expect(within(suppressedRow).getByText("Existing")).toBeInTheDocument();

    const dialog = await openDetail("PARSE-002");
    expect(dialog).toHaveFocus();
    expect(within(dialog).getByText("Suppressed finding")).toBeInTheDocument();
    expect(within(dialog).getByText(/known parser limitation/)).toBeInTheDocument();
    expect(within(dialog).getByText("DAG could not be parsed")).toBeInTheDocument();

    fireEvent.keyDown(dialog, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    const failDialog = await openDetail("OWN-001");
    expect(within(failDialog).getByText("Declare owner on every DAG call")).toBeInTheDocument();
    expect(within(failDialog).getByText("Retained evidence")).toBeInTheDocument();
    expect(within(failDialog).getByText('dag = DAG("orders")')).toBeInTheDocument();
    expect(within(failDialog).getByText(/add-owner/)).toBeInTheDocument();
    expect(within(failDialog).queryByText("Report artifact unavailable")).not.toBeInTheDocument();
  });

  it("calls out an unsuppressed ERROR finding instead of reading it as a passing gate", async () => {
    completedScanMocks();
    renderScanPage("scan-1");

    await screen.findByText("OWN-001");

    const errorRow = rowForFinding("SCHED-004");
    expect(within(errorRow).getByText("ERROR")).toBeInTheDocument();
    expect(within(errorRow).getByText("Active")).toBeInTheDocument();
    expect(within(errorRow).queryByText("SUPPRESSED")).not.toBeInTheDocument();

    const dialog = await openDetail("SCHED-004");
    expect(within(dialog).getByText("Unsuppressed ERROR")).toBeInTheDocument();
    expect(
      within(dialog).getByText(/cannot be treated as\s+passing its gate/),
    ).toBeInTheDocument();
    expect(within(dialog).queryByText("Suppressed finding")).not.toBeInTheDocument();
    expect(within(dialog).getByText("Schedule expression could not be evaluated")).toBeInTheDocument();
  });

  it("labels an incomplete scan and its missing gate result as Not evaluated instead of deriving a pass", async () => {
    getScanStatusMock.mockResolvedValue(SCAN_INCOMPLETE);
    getScanReportMock.mockResolvedValue(REPORT_INCOMPLETE);
    findingsMock.mockResolvedValue(EMPTY_FINDINGS);
    renderScanPage("scan-2");

    const summary = await screen.findByRole("region", { name: "Scan summary" });
    expect(within(summary).getByText("Failed")).toBeInTheDocument();
    expect(within(summary).getByText("Incomplete")).toBeInTheDocument();
    expect(
      within(summary).getByText(/parse-error: dags\/broken\.py could not be parsed/),
    ).toBeInTheDocument();

    const gate = await findGateRegion();
    expect(within(gate).getByText("Not evaluated")).toBeInTheDocument();
    expect(within(gate).queryByText("Gate passed")).not.toBeInTheDocument();
    expect(within(gate).queryByText("Gate failed")).not.toBeInTheDocument();
    expect(
      within(gate).getByText(/did not finish evaluating every policy/),
    ).toBeInTheDocument();

    expect(screen.getAllByText("EVALUATION_ERROR").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/policy OWN-001 raised/)).toBeInTheDocument();
    expect(screen.getByText("No runtime observations")).toBeInTheDocument();
    expect(screen.getByText("No findings match the current filters.")).toBeInTheDocument();
  });

  it("keeps normalized findings and shows calm unavailable states when the artifact is pruned", async () => {
    getScanStatusMock.mockResolvedValue(SCAN_COMPLETED);
    getScanReportMock.mockRejectedValue(
      new ApiError(404, "req-9", "scan report not available", "/scans/scan-1/report failed with 404"),
    );
    findingsMock.mockResolvedValue(FINDINGS_PAGE);
    renderScanPage("scan-1");

    const gate = await findGateRegion();
    expect(within(gate).getByText("Not evaluated")).toBeInTheDocument();
    expect(within(gate).getByText(/canonical report artifact .* is unavailable/i)).toBeInTheDocument();

    expect(screen.queryByRole("link", { name: "JSON" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Run issues" })).not.toBeInTheDocument();

    expect(await screen.findByText("OWN-001")).toBeInTheDocument();

    const dialog = await openDetail("OWN-001");
    expect(within(dialog).getByText("DAG lacks an effective owner")).toBeInTheDocument();
    expect(within(dialog).getByText("Report artifact unavailable")).toBeInTheDocument();
    expect(within(dialog).getByText("Declare owner on every DAG call")).toBeInTheDocument();
    expect(within(dialog).queryByText("Retained evidence")).not.toBeInTheDocument();
  });

  it("sends exact server filters and pagination, resetting the page when filters change", async () => {
    completedScanMocks();
    renderScanPage("scan-1");

    await screen.findByText("OWN-001");
    expect(findingsMock).toHaveBeenCalledWith("scan-1", { limit: 25, offset: 0 });

    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "FAIL" } });
    await waitFor(() =>
      expect(findingsMock).toHaveBeenCalledWith("scan-1", { status: "FAIL", limit: 25, offset: 0 }),
    );

    fireEvent.change(screen.getByLabelText("Per page"), { target: { value: "10" } });
    await waitFor(() =>
      expect(findingsMock).toHaveBeenCalledWith("scan-1", {
        status: "FAIL",
        limit: 10,
        offset: 0,
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() =>
      expect(findingsMock).toHaveBeenCalledWith("scan-1", {
        status: "FAIL",
        limit: 10,
        offset: 10,
      }),
    );

    fireEvent.change(screen.getByLabelText("Severity"), { target: { value: "high" } });
    await waitFor(() =>
      expect(findingsMock).toHaveBeenCalledWith("scan-1", {
        status: "FAIL",
        severity: "high",
        limit: 10,
        offset: 0,
      }),
    );

    fireEvent.change(screen.getByLabelText("Suppressed"), { target: { value: "false" } });
    await waitFor(() =>
      expect(findingsMock).toHaveBeenCalledWith("scan-1", {
        status: "FAIL",
        severity: "high",
        suppressed: false,
        limit: 10,
        offset: 0,
      }),
    );

    fireEvent.change(screen.getByLabelText("Policy ID"), { target: { value: "OWN-001" } });
    fireEvent.change(screen.getByLabelText("File path"), { target: { value: "dags/orders.py" } });
    fireEvent.change(screen.getByLabelText("Baseline"), { target: { value: "new" } });
    await waitFor(() =>
      expect(findingsMock).toHaveBeenCalledWith("scan-1", {
        status: "FAIL",
        severity: "high",
        policy_id: "OWN-001",
        file_path: "dags/orders.py",
        suppressed: false,
        baseline_status: "new",
        limit: 10,
        offset: 0,
      }),
    );
  });

  it("maps findings failures to an actionable banner with retry", async () => {
    completedScanMocks();
    findingsMock.mockRejectedValue(
      new ApiError(503, "req-4", "platform unavailable", "/scans/scan-1/findings failed with 503"),
    );
    renderScanPage("scan-1");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/temporarily unavailable/i);

    fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(findingsMock).toHaveBeenCalledTimes(2));
  });

  it("does not fetch the report for an active scan, offers cancellation, and refreshes after it", async () => {
    getScanStatusMock
      .mockResolvedValueOnce(SCAN_RUNNING)
      .mockResolvedValue(SCAN_CANCELLED);
    getScanReportMock.mockRejectedValue(
      new ApiError(404, "req-8", "scan report not available", "/scans/scan-3/report failed with 404"),
    );
    findingsMock.mockResolvedValue(EMPTY_FINDINGS);
    cancelScanMock.mockResolvedValue({ scan_id: "scan-3", status: "cancelled" });
    renderScanPage("scan-3");

    const summary = await screen.findByRole("region", { name: "Scan summary" });
    expect(within(summary).getByText("Running")).toBeInTheDocument();
    expect(getScanReportMock).not.toHaveBeenCalled();
    expect(screen.getByText("Findings appear when the scan finishes.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cancel scan" }));
    await waitFor(() => expect(cancelScanMock).toHaveBeenCalledWith("scan-3"));
    await waitFor(() => expect(getScanStatusMock).toHaveBeenCalledTimes(2));
    expect(await within(summary).findByText("Cancelled")).toBeInTheDocument();

    const gate = await findGateRegion();
    expect(within(gate).getByText("Not evaluated")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel scan" })).not.toBeInTheDocument();
  });

  it("surfaces a conflict when cancellation is rejected", async () => {
    getScanStatusMock.mockResolvedValue(SCAN_RUNNING);
    findingsMock.mockResolvedValue(EMPTY_FINDINGS);
    cancelScanMock.mockRejectedValueOnce(
      new ApiError(409, "req-2", "scan already succeeded", "/scans/scan-3/cancel failed with 409"),
    );
    renderScanPage("scan-3");

    await screen.findByRole("button", { name: "Cancel scan" });
    fireEvent.click(screen.getByRole("button", { name: "Cancel scan" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/rejected/i);
    expect(alert).toHaveTextContent("scan already succeeded");
  });

  it("maps authentication failures on scan status to an actionable message", async () => {
    getScanStatusMock.mockRejectedValue(
      new ApiError(401, "req-3", "missing or invalid admin token", "/scans/scan-1 failed with 401"),
    );
    renderScanPage("scan-1");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/admin token/i);
  });

  it("shows a not-found state for unknown scans", async () => {
    getScanStatusMock.mockRejectedValue(
      new ApiError(404, "req-5", "scan not found", "/scans/scan-404 failed with 404"),
    );
    renderScanPage("scan-404");

    expect(await screen.findByText("Scan not found")).toBeInTheDocument();
  });

  it("polls scan status only while the scan is active", async () => {
    vi.useFakeTimers();
    try {
      getScanStatusMock
        .mockResolvedValueOnce(SCAN_RUNNING)
        .mockResolvedValue(SCAN_COMPLETED);
      getScanReportMock.mockResolvedValue(REPORT_COMPLETED);
      findingsMock.mockResolvedValue(EMPTY_FINDINGS);
      renderScanPage("scan-1");

      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(getScanStatusMock).toHaveBeenCalledTimes(1);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(ACTIVE_POLL_INTERVAL_MS);
      });
      expect(getScanStatusMock).toHaveBeenCalledTimes(2);

      // The refetched status is terminal, so polling stops.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(ACTIVE_POLL_INTERVAL_MS * 3);
      });
      expect(getScanStatusMock).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });
});
