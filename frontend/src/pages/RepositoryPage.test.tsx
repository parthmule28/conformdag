/**
 * Repository page journeys: summary, scan lifecycle actions, baseline
 * management, paginated history, and repository trends. Client functions are
 * mocked; TanStack Query runs for real so invalidation and error behavior is
 * covered through the page.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import {
  ApiError,
  cancelScan,
  getRepositoryTrends,
  listRepositories,
  scanHistory,
  setBaseline,
  triggerScan,
  type Page,
  type Repository,
  type ScanSummary,
  type ScanTransitionResponse,
  type TrendPoint,
} from "../api";
import RepositoryPage from "./RepositoryPage";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    cancelScan: vi.fn(),
    getRepositoryTrends: vi.fn(),
    listRepositories: vi.fn(),
    scanHistory: vi.fn(),
    setBaseline: vi.fn(),
    triggerScan: vi.fn(),
  };
});

const cancelScanMock = vi.mocked(cancelScan);
const getRepositoryTrendsMock = vi.mocked(getRepositoryTrends);
const listRepositoriesMock = vi.mocked(listRepositories);
const scanHistoryMock = vi.mocked(scanHistory);
const setBaselineMock = vi.mocked(setBaseline);
const triggerScanMock = vi.mocked(triggerScan);

const REPOSITORY: Repository = {
  id: "repo-1",
  name: "etl-core",
  path: "/srv/repos/etl-core",
  policy_pack: "packs/core.yaml",
  airflow_profile: "3.3.0",
  baseline_scan_id: "scan-1",
};

const TREND_POINTS: TrendPoint[] = [
  {
    date: "2026-09-16",
    completed_scan_count: 2,
    fail_finding_count: 2,
    error_finding_count: 1,
    suppressed_finding_count: 0,
    new_finding_count: 1,
  },
];

const HISTORY: Page<ScanSummary> = {
  total: 12,
  items: [
    {
      scan_id: "scan-1",
      status: "succeeded",
      created_at: "2026-09-15T08:00:00Z",
      finished_at: "2026-09-15T08:02:00Z",
      result_fingerprint: "fp-1",
      complete: true,
      gate_passed: true,
    },
    {
      scan_id: "scan-2",
      status: "succeeded",
      created_at: "2026-09-16T09:00:00Z",
      finished_at: "2026-09-16T09:01:00Z",
      result_fingerprint: "fp-2",
      complete: true,
      gate_passed: false,
    },
    {
      scan_id: "scan-3",
      status: "running",
      created_at: "2026-09-17T09:00:00Z",
      finished_at: null,
      result_fingerprint: null,
      complete: null,
      gate_passed: null,
    },
    {
      scan_id: "scan-4",
      status: "failed",
      created_at: "2026-09-14T07:00:00Z",
      finished_at: "2026-09-14T07:05:00Z",
      result_fingerprint: null,
      complete: false,
      gate_passed: null,
    },
  ],
};

function makeClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function happyMocks(): void {
  listRepositoriesMock.mockResolvedValue([REPOSITORY]);
  scanHistoryMock.mockResolvedValue(HISTORY);
  getRepositoryTrendsMock.mockResolvedValue({ repository_id: "repo-1", points: TREND_POINTS });
}

function renderRepositoryPage(): void {
  render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter initialEntries={["/repos/repo-1"]}>
        <Routes>
          <Route path="/repos/:repositoryId" element={<RepositoryPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function rowForScan(scanId: string): HTMLElement {
  // The summary region may link the same scan id (current baseline); rows are
  // the link instances that live inside a table row.
  const links = screen.getAllByRole("link", { name: scanId });
  for (const link of links) {
    const row = link.closest("tr");
    if (row !== null) {
      return row;
    }
  }
  throw new Error(`scan ${scanId} has no table row`);
}

function summaryRegion(): HTMLElement {
  return screen.getByRole("region", { name: "Repository configuration" });
}

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("RepositoryPage", () => {
  it("shows a loading state while repository data is in flight", () => {
    listRepositoriesMock.mockReturnValue(new Promise(() => undefined));
    scanHistoryMock.mockReturnValue(new Promise(() => undefined));
    getRepositoryTrendsMock.mockReturnValue(new Promise(() => undefined));
    renderRepositoryPage();
    expect(screen.getByRole("status")).toHaveTextContent("Loading repository");
  });

  it("renders the summary, paginated history, exports, and trends", async () => {
    happyMocks();
    renderRepositoryPage();

    expect(await screen.findByText("etl-core")).toBeInTheDocument();
    expect(screen.getByText("/srv/repos/etl-core")).toBeInTheDocument();
    expect(screen.getByText("packs/core.yaml")).toBeInTheDocument();
    expect(screen.getByText("3.3.0")).toBeInTheDocument();
    expect(within(summaryRegion()).getByRole("link", { name: "scan-1" })).toHaveAttribute(
      "href",
      "/scans/scan-1",
    );

    for (const scanId of ["scan-1", "scan-2", "scan-3", "scan-4"]) {
      const row = rowForScan(scanId);
      expect(within(row).getByRole("link", { name: scanId })).toHaveAttribute("href", `/scans/${scanId}`);
    }
    expect(within(rowForScan("scan-1")).getByRole("link", { name: "JSON" })).toHaveAttribute(
      "href",
      "/api/v1/scans/scan-1/export/json",
    );
    expect(within(rowForScan("scan-1")).getByRole("link", { name: "SARIF" })).toHaveAttribute(
      "href",
      "/api/v1/scans/scan-1/export/sarif",
    );
    expect(within(rowForScan("scan-1")).getByRole("link", { name: "HTML" })).toHaveAttribute(
      "href",
      "/api/v1/scans/scan-1/export/html",
    );
    expect(within(rowForScan("scan-2")).getByRole("link", { name: "JSON" })).toBeInTheDocument();
    expect(within(rowForScan("scan-3")).queryByRole("link", { name: "JSON" })).not.toBeInTheDocument();
    expect(within(rowForScan("scan-4")).queryByRole("link", { name: "JSON" })).not.toBeInTheDocument();

    expect(within(rowForScan("scan-1")).getByText("2026-09-15 08:00 UTC")).toBeInTheDocument();
    expect(within(rowForScan("scan-3")).getByText("Not evaluated")).toBeInTheDocument();

    expect(screen.getByText("2026-09-16")).toBeInTheDocument();
    expect(screen.queryByText("2026-09-15")).not.toBeInTheDocument();
  });

  it("pages through scan history using the server total", async () => {
    happyMocks();
    renderRepositoryPage();

    expect(await screen.findByText("Showing 1\u201310 of 12")).toBeInTheDocument();
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(scanHistoryMock).toHaveBeenCalledWith("repo-1", { limit: 10, offset: 10 }));
    expect(await screen.findByText("Showing 11\u201312 of 12")).toBeInTheDocument();
  });

  it("offers baseline actions only for eligible scans and disables the current baseline", async () => {
    happyMocks();
    renderRepositoryPage();

    await screen.findByText("Showing 1\u201310 of 12");
    expect(
      within(rowForScan("scan-1")).getByRole("button", { name: "Current baseline" }),
    ).toBeDisabled();

    const setBaselineButton = within(rowForScan("scan-2")).getByRole("button", {
      name: "Set as baseline",
    });
    expect(setBaselineButton).toBeEnabled();
    expect(within(rowForScan("scan-3")).queryByRole("button", { name: /baseline/i })).not.toBeInTheDocument();
    expect(within(rowForScan("scan-4")).queryByRole("button", { name: /baseline/i })).not.toBeInTheDocument();

    setBaselineMock.mockResolvedValue({ repository_id: "repo-1", baseline_scan_id: "scan-2" });
    fireEvent.click(setBaselineButton);

    await waitFor(() => expect(setBaselineMock).toHaveBeenCalledWith("repo-1", "scan-2"));
    await waitFor(() => expect(scanHistoryMock).toHaveBeenCalledTimes(2));
  });

  it("cancels an active scan and surfaces a terminal-state conflict inline", async () => {
    happyMocks();
    renderRepositoryPage();

    await screen.findByText("Showing 1\u201310 of 12");
    cancelScanMock.mockRejectedValueOnce(
      new ApiError(409, "req-2", "scan already succeeded", "/scans/scan-3/cancel failed with 409"),
    );

    fireEvent.click(within(rowForScan("scan-3")).getByRole("button", { name: "Cancel" }));

    await waitFor(() => expect(cancelScanMock).toHaveBeenCalledWith("scan-3"));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("scan already succeeded");
    expect(alert).toHaveTextContent(/rejected/i);
  });

  it("triggers a scan with a pending state and refreshes history", async () => {
    happyMocks();
    renderRepositoryPage();

    await screen.findByText("Showing 1\u201310 of 12");
    let resolveTrigger!: (value: ScanTransitionResponse) => void;
    triggerScanMock.mockReturnValue(
      new Promise<ScanTransitionResponse>((resolve) => {
        resolveTrigger = resolve;
      }),
    );

    const triggerButton = screen.getByRole("button", { name: "Trigger scan" });
    fireEvent.click(triggerButton);
    await waitFor(() => expect(triggerButton).toBeDisabled());
    expect(triggerScanMock).toHaveBeenCalledWith("repo-1");

    act(() => {
      resolveTrigger({ scan_id: "scan-99", status: "queued" });
    });
    await waitFor(() => expect(scanHistoryMock).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/Scan queued/)).toBeInTheDocument();
  });

  it("maps authentication failures to an actionable message", async () => {
    listRepositoriesMock.mockRejectedValue(
      new ApiError(401, "req-3", "missing or invalid admin token", "/repos failed with 401"),
    );
    renderRepositoryPage();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/admin token/i);
  });

  it("shows an actionable error with retry when history fails", async () => {
    happyMocks();
    scanHistoryMock.mockRejectedValue(
      new ApiError(503, "req-4", "platform unavailable", "history failed with 503"),
    );
    renderRepositoryPage();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/temporarily unavailable/i);

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(scanHistoryMock).toHaveBeenCalledTimes(2));
  });

  it("shows calm empty states when the repository has no scans or trend points", async () => {
    listRepositoriesMock.mockResolvedValue([REPOSITORY]);
    scanHistoryMock.mockResolvedValue({ items: [], total: 0 });
    getRepositoryTrendsMock.mockResolvedValue({ repository_id: "repo-1", points: [] });
    renderRepositoryPage();

    expect(await screen.findByText(/No scans have run yet/)).toBeInTheDocument();
    expect(screen.getByText("No trend data yet")).toBeInTheDocument();
    expect(screen.getByText("No items")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Trigger scan" })).toBeEnabled();
  });

  it("shows a not-found state for unregistered repositories", async () => {
    listRepositoriesMock.mockResolvedValue([]);
    scanHistoryMock.mockRejectedValue(
      new ApiError(404, "req-5", "repository not registered", "failed with 404"),
    );
    getRepositoryTrendsMock.mockRejectedValue(
      new ApiError(404, "req-5", "repository not registered", "failed with 404"),
    );
    renderRepositoryPage();

    expect(await screen.findByText("Repository not found")).toBeInTheDocument();
  });
});
