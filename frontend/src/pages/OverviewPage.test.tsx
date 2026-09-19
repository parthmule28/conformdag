/**
 * Overview page journeys: metric strip, trend chart, and recent scans fed by
 * the platform query layer. Client functions are mocked; TanStack Query runs
 * for real so loading, error, empty, polling, and retry behavior is covered.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { ApiError, getOverview, type OverviewResponse } from "../api";
import { ACTIVE_POLL_INTERVAL_MS } from "../hooks/usePlatformQueries";
import OverviewPage from "./OverviewPage";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return { ...actual, getOverview: vi.fn() };
});

const getOverviewMock = vi.mocked(getOverview);

function makeClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderOverview(): void {
  render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter initialEntries={["/"]}>
        <OverviewPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function neverResolvingOverview(): Promise<OverviewResponse> {
  return new Promise<OverviewResponse>(() => undefined);
}

function emptyOverview(): OverviewResponse {
  return {
    repository_count: 0,
    completed_scan_count: 0,
    active_scan_count: 0,
    current_failure_count: 0,
    current_error_count: 0,
    current_new_finding_count: 0,
    trends: [],
    recent_scans: [],
  };
}

const POPULATED_OVERVIEW: OverviewResponse = {
  repository_count: 6,
  completed_scan_count: 21,
  active_scan_count: 0,
  current_failure_count: 4,
  current_error_count: 1,
  current_new_finding_count: 3,
  trends: [
    {
      date: "2026-09-16",
      completed_scan_count: 2,
      fail_finding_count: 2,
      error_finding_count: 1,
      suppressed_finding_count: 1,
      new_finding_count: 3,
    },
    {
      date: "2026-09-17",
      completed_scan_count: 1,
      fail_finding_count: 0,
      error_finding_count: 0,
      suppressed_finding_count: 0,
      new_finding_count: 0,
    },
  ],
  recent_scans: [
    {
      scan_id: "scan-9",
      repository_id: "repo-1",
      repository_name: "etl-core",
      status: "running",
      created_at: "2026-09-17T09:00:00Z",
      finished_at: null,
      complete: null,
      gate_passed: null,
    },
    {
      scan_id: "scan-8",
      repository_id: "repo-2",
      repository_name: "reports-etl",
      status: "succeeded",
      created_at: "2026-09-17T08:00:00Z",
      finished_at: "2026-09-17T08:03:00Z",
      complete: true,
      gate_passed: false,
    },
  ],
};

function rowForScan(scanId: string): HTMLElement {
  const link = screen.getByRole("link", { name: scanId });
  const row = link.closest("tr");
  if (row === null) {
    throw new Error(`scan ${scanId} has no table row`);
  }
  return row;
}

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("OverviewPage", () => {
  it("shows a loading state while the overview is in flight", () => {
    getOverviewMock.mockReturnValue(neverResolvingOverview());
    renderOverview();
    expect(screen.getByRole("status")).toHaveTextContent("Loading overview");
  });

  it("shows an actionable error with a retry for service failures", async () => {
    getOverviewMock.mockRejectedValue(
      new ApiError(503, "req-1", "platform unavailable", "/overview failed with 503"),
    );
    renderOverview();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/temporarily unavailable/i);

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(getOverviewMock).toHaveBeenCalledTimes(2));
  });

  it("renders a calm empty state when the platform has no data yet", async () => {
    getOverviewMock.mockResolvedValue(emptyOverview());
    renderOverview();

    expect(await screen.findByText("No trend data yet")).toBeInTheDocument();
    expect(screen.getByText(/No scans have run yet/)).toBeInTheDocument();
    expect(screen.queryByText("2026-09-16")).not.toBeInTheDocument();

    const repositories = await screen.findByText("Repositories");
    expect(repositories.nextElementSibling).toHaveTextContent("0");
  });

  it("renders metrics, trend labels, and recent scans without fabricated history", async () => {
    getOverviewMock.mockResolvedValue(POPULATED_OVERVIEW);
    renderOverview();

    const repositories = await screen.findByText("Repositories");
    expect(repositories.nextElementSibling).toHaveTextContent("6");
    expect(screen.getByText("Completed scans").nextElementSibling).toHaveTextContent("21");
    expect(screen.getByText("Active scans").nextElementSibling).toHaveTextContent("0");
    expect(screen.getByText("Current failures").nextElementSibling).toHaveTextContent("4");
    expect(screen.getByText("Current errors").nextElementSibling).toHaveTextContent("1");
    expect(screen.getByText("New findings").nextElementSibling).toHaveTextContent("3");

    expect(screen.getByText("2026-09-16")).toBeInTheDocument();
    expect(screen.getByText("2026-09-17")).toBeInTheDocument();
    expect(screen.queryByText("2026-09-15")).not.toBeInTheDocument();

    expect(screen.getByRole("link", { name: "etl-core" })).toHaveAttribute("href", "/repos/repo-1");
    expect(screen.getByRole("link", { name: "reports-etl" })).toHaveAttribute("href", "/repos/repo-2");
    expect(screen.getByRole("link", { name: "scan-9" })).toHaveAttribute("href", "/scans/scan-9");
    expect(screen.getByRole("link", { name: "scan-8" })).toHaveAttribute("href", "/scans/scan-8");

    const runningRow = rowForScan("scan-9");
    expect(within(runningRow).getByText("INCOMPLETE")).toBeInTheDocument();
    expect(within(runningRow).getByText("Not evaluated")).toBeInTheDocument();
    expect(within(runningRow).getByText("\u2014")).toBeInTheDocument();

    const finishedRow = rowForScan("scan-8");
    expect(within(finishedRow).getByText("PASS")).toBeInTheDocument();
    expect(within(finishedRow).getByText("FAIL")).toBeInTheDocument();
    expect(within(finishedRow).getByText("2026-09-17 08:00 UTC")).toBeInTheDocument();
    expect(within(finishedRow).getByText("2026-09-17 08:03 UTC")).toBeInTheDocument();
  });

  it("polls at a bounded interval only while scans are active", async () => {
    vi.useFakeTimers();
    try {
      getOverviewMock
        .mockResolvedValueOnce({ ...POPULATED_OVERVIEW, active_scan_count: 1 })
        .mockResolvedValue(emptyOverview());
      renderOverview();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(getOverviewMock).toHaveBeenCalledTimes(1);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(ACTIVE_POLL_INTERVAL_MS);
      });
      expect(getOverviewMock).toHaveBeenCalledTimes(2);

      // The refetched overview reports no active scans, so polling stops.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(ACTIVE_POLL_INTERVAL_MS * 4);
      });
      expect(getOverviewMock).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });
});
