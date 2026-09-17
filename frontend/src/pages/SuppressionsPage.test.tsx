/**
 * Suppression inventory journeys: active/expired distinction, contextual
 * links, state/source filters, creation and editing through the existing
 * client routes, expiry-input wire format, and mutation error mapping. Client
 * functions are mocked; TanStack Query runs for real so invalidation and
 * error mapping are exercised.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import {
  ApiError,
  createSuppression,
  listSuppressions,
  updateSuppression,
  type Suppression,
} from "../api";
import SuppressionsPage from "./SuppressionsPage";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    createSuppression: vi.fn(),
    listSuppressions: vi.fn(),
    updateSuppression: vi.fn(),
  };
});

const createSuppressionMock = vi.mocked(createSuppression);
const listSuppressionsMock = vi.mocked(listSuppressions);
const updateSuppressionMock = vi.mocked(updateSuppression);

const ACTIVE: Suppression = {
  id: "sup-1",
  policy_id: "OWN-001",
  fingerprint: "fp-own-1",
  reason: "legacy DAG pending migration",
  owner: "data-platform",
  created_at: "2026-08-01T09:00:00Z",
  expires_at: "2030-01-01T00:00:00Z",
  source: "platform",
};

const EXPIRED: Suppression = {
  id: "sup-2",
  policy_id: "DOC-002",
  fingerprint: "fp-doc-2",
  reason: "documented exception for the reports DAG",
  owner: "reports-team",
  created_at: "2026-05-01T09:00:00Z",
  expires_at: "2020-01-01T00:00:00Z",
  source: "code",
};

const CREATED: Suppression = {
  id: "sup-3",
  policy_id: "OWN-001",
  fingerprint: "fp-new-9",
  reason: "migration in progress",
  owner: "data-platform",
  created_at: "2026-09-17T00:00:00Z",
  expires_at: "2030-06-01T12:00:00Z",
  source: "platform",
};

function makeClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderSuppressions(): void {
  render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter initialEntries={["/suppressions"]}>
        <SuppressionsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function populatedList(): void {
  listSuppressionsMock.mockResolvedValue([ACTIVE, EXPIRED]);
}

function rowForSuppression(id: string): HTMLElement {
  const row = screen
    .getByRole("button", { name: `Edit suppression ${id}` })
    .closest("tr");
  if (row === null) {
    throw new Error(`suppression ${id} has no table row`);
  }
  return row;
}

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("SuppressionsPage", () => {
  it("distinguishes active suppressions from expired ones", async () => {
    populatedList();
    renderSuppressions();

    await screen.findByRole("button", { name: "Edit suppression sup-1" });
    const activeRow = rowForSuppression("sup-1");
    expect(within(activeRow).getByText("SUPPRESSED")).toBeInTheDocument();
    expect(within(activeRow).getByText("2030-01-01 00:00 UTC")).toBeInTheDocument();

    const expiredRow = rowForSuppression("sup-2");
    expect(within(expiredRow).getByText("Expired")).toBeInTheDocument();
    expect(within(expiredRow).queryByText("SUPPRESSED")).not.toBeInTheDocument();
    expect(within(expiredRow).getByText("2020-01-01 00:00 UTC")).toBeInTheDocument();
  });

  it("links policy ids to the policies page and shows fingerprints", async () => {
    populatedList();
    renderSuppressions();

    await screen.findByText("fp-own-1");
    expect(screen.getByRole("link", { name: "OWN-001" })).toHaveAttribute("href", "/policies");
    expect(screen.getByRole("link", { name: "DOC-002" })).toHaveAttribute("href", "/policies");
    expect(screen.getByText("fp-doc-2")).toBeInTheDocument();
  });

  it("filters rows by state and source", async () => {
    populatedList();
    renderSuppressions();

    await screen.findByText("fp-own-1");

    fireEvent.change(screen.getByLabelText("State"), { target: { value: "expired" } });
    expect(screen.queryByText("fp-own-1")).not.toBeInTheDocument();
    expect(screen.getByText("fp-doc-2")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("State"), { target: { value: "active" } });
    expect(screen.getByText("fp-own-1")).toBeInTheDocument();
    expect(screen.queryByText("fp-doc-2")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("State"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Source"), { target: { value: "code" } });
    expect(screen.getByText("fp-doc-2")).toBeInTheDocument();
    expect(screen.queryByText("fp-own-1")).not.toBeInTheDocument();
  });

  it("creates a suppression with an ISO expiry and refreshes the list", async () => {
    listSuppressionsMock.mockResolvedValueOnce([ACTIVE, EXPIRED]);
    listSuppressionsMock.mockResolvedValue([ACTIVE, EXPIRED, CREATED]);
    createSuppressionMock.mockResolvedValue(CREATED);
    renderSuppressions();

    fireEvent.click(await screen.findByRole("button", { name: "New suppression" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Policy ID"), {
      target: { value: "OWN-001" },
    });
    fireEvent.change(within(dialog).getByLabelText("Fingerprint"), {
      target: { value: "fp-new-9" },
    });
    fireEvent.change(within(dialog).getByLabelText("Reason"), {
      target: { value: "migration in progress" },
    });
    fireEvent.change(within(dialog).getByLabelText("Owner"), {
      target: { value: "data-platform" },
    });
    fireEvent.change(within(dialog).getByLabelText("Expires at"), {
      target: { value: "2030-06-01T12:00" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save suppression" }));

    await waitFor(() =>
      expect(createSuppressionMock).toHaveBeenCalledWith({
        policy_id: "OWN-001",
        fingerprint: "fp-new-9",
        reason: "migration in progress",
        owner: "data-platform",
        expires_at: new Date("2030-06-01T12:00").toISOString(),
      }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(await screen.findByText("fp-new-9")).toBeInTheDocument();
    expect(listSuppressionsMock).toHaveBeenCalledTimes(2);
  });

  it("keeps the create form open with a safe error when creation is rejected", async () => {
    populatedList();
    createSuppressionMock.mockRejectedValue(
      new ApiError(422, "req-1", "fingerprint unknown", "/suppressions failed with 422"),
    );
    renderSuppressions();

    fireEvent.click(await screen.findByRole("button", { name: "New suppression" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Policy ID"), {
      target: { value: "OWN-001" },
    });
    fireEvent.change(within(dialog).getByLabelText("Fingerprint"), {
      target: { value: "fp-new-9" },
    });
    fireEvent.change(within(dialog).getByLabelText("Reason"), {
      target: { value: "migration in progress" },
    });
    fireEvent.change(within(dialog).getByLabelText("Owner"), {
      target: { value: "data-platform" },
    });
    fireEvent.change(within(dialog).getByLabelText("Expires at"), {
      target: { value: "2030-06-01T12:00" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save suppression" }));

    const alert = await within(dialog).findByRole("alert");
    expect(alert).toHaveTextContent(/rejected the input/);
    expect(alert).toHaveTextContent("fingerprint unknown");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Reason")).toHaveValue("migration in progress");
  });

  it("edits reason, owner, and expiry through the update route", async () => {
    populatedList();
    updateSuppressionMock.mockResolvedValue(ACTIVE);
    renderSuppressions();

    await screen.findByRole("button", { name: "Edit suppression sup-1" });
    fireEvent.click(screen.getByRole("button", { name: "Edit suppression sup-1" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Reason")).toHaveValue("legacy DAG pending migration");
    expect(within(dialog).getByLabelText("Owner")).toHaveValue("data-platform");
    expect(within(dialog).getByLabelText("Expires at")).toHaveValue("2030-01-01T00:00");

    fireEvent.change(within(dialog).getByLabelText("Reason"), {
      target: { value: "updated reason" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save suppression" }));

    await waitFor(() =>
      expect(updateSuppressionMock).toHaveBeenCalledWith("sup-1", {
        reason: "updated reason",
        owner: "data-platform",
        expires_at: new Date("2030-01-01T00:00").toISOString(),
      }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("explains that an expired suppression does not waive a current finding", async () => {
    populatedList();
    renderSuppressions();

    await screen.findByRole("button", { name: "Edit suppression sup-2" });
    fireEvent.click(screen.getByRole("button", { name: "Edit suppression sup-2" }));
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(/does not waive a current finding/),
    ).toBeInTheDocument();
  });

  it("maps list failures to an actionable banner with retry", async () => {
    listSuppressionsMock.mockRejectedValue(
      new ApiError(503, "req-5", null, "/suppressions failed with 503"),
    );
    renderSuppressions();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/temporarily unavailable/i);

    listSuppressionsMock.mockResolvedValue([ACTIVE, EXPIRED]);
    fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("fp-own-1")).toBeInTheDocument();
  });
});
