/**
 * Policy and gate management journeys: pack summaries and selection, policy
 * filtering, lossless policy editing with draft safety, gate rule editing with
 * typed controls, server-side pack validation, and mutation error mapping.
 * Client functions are mocked; TanStack Query runs for real so invalidation,
 * draft preservation, and error mapping are exercised.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import {
  ApiError,
  deleteGate,
  listPackGates,
  listPackPolicies,
  listPacks,
  updatePolicy,
  upsertGate,
  validatePack,
  type Gate,
  type PackSummary,
  type PolicyInfo,
} from "../api";
import PoliciesPage from "./PoliciesPage";

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    deleteGate: vi.fn(),
    listPackGates: vi.fn(),
    listPackPolicies: vi.fn(),
    listPacks: vi.fn(),
    updatePolicy: vi.fn(),
    upsertGate: vi.fn(),
    validatePack: vi.fn(),
  };
});

const deleteGateMock = vi.mocked(deleteGate);
const listPackGatesMock = vi.mocked(listPackGates);
const listPackPoliciesMock = vi.mocked(listPackPolicies);
const listPacksMock = vi.mocked(listPacks);
const updatePolicyMock = vi.mocked(updatePolicy);
const upsertGateMock = vi.mocked(upsertGate);
const validatePackMock = vi.mocked(validatePack);

const PACKS: PackSummary[] = [
  {
    name: "core",
    path: "packs/core.yaml",
    id: "core-pack",
    version: "3",
    policy_count: 2,
    error: null,
  },
  {
    name: "broken",
    path: "packs/broken.yaml",
    id: null,
    version: null,
    policy_count: 0,
    error: "duplicate policy id DUP-001",
  },
];

const POLICY_OWN: PolicyInfo = {
  id: "OWN-001",
  title: "Every DAG declares an effective owner",
  version: "2",
  status: "ACTIVE",
  severity: "high",
  tags: ["owner", "core"],
  check_kind: "required-owner",
  check_config: { kind: "required-owner", allowed: ["team-a"] },
  deterministic_checks: ["effective-owner"],
  configuration: { kind: "required-owner", allowed: ["team-a"] },
  source_document: "standards/ownership.md",
  source_section: "Owner of record",
  source_version: "2026-09",
  invariant: "Every DAG declares an effective owner from the approved roster.",
  safe_path: null,
  ownership: {
    owner: "data-platform",
    approvers: ["alice"],
    approved_at: "2026-01-15T00:00:00Z",
    review_before: "2027-01-15T00:00:00Z",
    expires_at: null,
  },
  scope: { files: ["dags/**"], operators: [] },
  exceptions: { require_reason: true, require_expiry: true },
  enforcement: {
    type: "deterministic",
    deterministic_checks: ["effective-owner"],
    model_check: false,
    allow_abstention: false,
    blocking: true,
  },
};

const POLICY_DOC: PolicyInfo = {
  id: "DOC-002",
  title: "Every DAG carries a docstring",
  version: "1",
  status: "DRAFT",
  severity: "low",
  tags: ["docs"],
  check_kind: "required-tags",
  check_config: { kind: "required-tags", required: ["docstring"] },
  deterministic_checks: [],
  configuration: { kind: "required-tags", required: ["docstring"] },
  source_document: "standards/documentation.md",
  source_section: "Docstrings",
  source_version: null,
  invariant: "Every DAG module documents its DAGs with a docstring.",
  safe_path: "dags/legacy.py",
  ownership: {
    owner: "docs-team",
    approvers: [],
    approved_at: null,
    review_before: null,
    expires_at: null,
  },
  scope: { files: ["dags/**"], operators: ["PythonOperator"] },
  exceptions: { require_reason: true, require_expiry: false },
  enforcement: {
    type: "semantic",
    deterministic_checks: [],
    model_check: true,
    allow_abstention: true,
    blocking: false,
  },
};

const POLICIES: PolicyInfo[] = [POLICY_OWN, POLICY_DOC];

const GATES: Gate[] = [
  {
    id: "release",
    rules: [{ type: "max-severity", severity: "high" }, { type: "no-new-findings" }],
  },
  { id: "nightly", rules: [{ type: "max-findings", count: 10 }] },
];

function makeClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderPolicies(): void {
  render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter initialEntries={["/policies"]}>
        <PoliciesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function loadedPacks(): void {
  listPacksMock.mockResolvedValue(PACKS);
  listPackPoliciesMock.mockResolvedValue(POLICIES);
  listPackGatesMock.mockResolvedValue(GATES);
}

async function renderAndSelectCore(): Promise<void> {
  loadedPacks();
  renderPolicies();
  fireEvent.click(await screen.findByRole("button", { name: /core/ }));
  await screen.findByText("OWN-001");
}

function rowForPolicy(policyId: string): HTMLElement {
  const row = screen.getByText(policyId).closest("tr");
  if (row === null) {
    throw new Error(`policy ${policyId} has no table row`);
  }
  return row;
}

function rowForGate(gateId: string): HTMLElement {
  const row = screen.getByText(gateId).closest("tr");
  if (row === null) {
    throw new Error(`gate ${gateId} has no table row`);
  }
  return row;
}

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("PoliciesPage", () => {
  it("lists packs with version, policy count, and validation state", async () => {
    loadedPacks();
    renderPolicies();

    const coreButton = await screen.findByRole("button", { name: /core/ });
    expect(coreButton).toHaveTextContent("Version 3");
    expect(coreButton).toHaveTextContent("2 policies");
    expect(within(coreButton).getByText("PASS")).toBeInTheDocument();

    const brokenButton = screen.getByRole("button", { name: /broken/ });
    expect(within(brokenButton).getByText("ERROR")).toBeInTheDocument();
    expect(brokenButton).toHaveTextContent("duplicate policy id DUP-001");
  });

  it("maps pack load failures to an actionable banner with retry", async () => {
    listPacksMock.mockRejectedValue(
      new ApiError(503, "req-7", null, "/packs failed with 503"),
    );
    renderPolicies();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/temporarily unavailable/i);

    listPacksMock.mockResolvedValue(PACKS);
    fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("button", { name: /core/ })).toBeInTheDocument();
  });

  it("links a selected pack to its policies and gates", async () => {
    await renderAndSelectCore();

    expect(screen.getByRole("heading", { name: "Policies in core" })).toBeInTheDocument();
    expect(screen.getByText("standards/ownership.md")).toBeInTheDocument();
    const ownRow = rowForPolicy("OWN-001");
    expect(within(ownRow).getByText("effective-owner")).toBeInTheDocument();

    const releaseRow = rowForGate("release");
    const nightlyRow = rowForGate("nightly");
    expect(
      releaseRow.compareDocumentPosition(nightlyRow) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(releaseRow).toHaveTextContent("max severity high");
    expect(releaseRow).toHaveTextContent("no new findings");
    expect(nightlyRow).toHaveTextContent("at most 10 findings");
  });

  it("filters policies by domain tag, deterministic check, severity, and lifecycle status", async () => {
    await renderAndSelectCore();

    fireEvent.change(screen.getByLabelText("Domain tag"), { target: { value: "docs" } });
    expect(screen.queryByText("OWN-001")).not.toBeInTheDocument();
    expect(screen.getByText("DOC-002")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Domain tag"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Deterministic check"), {
      target: { value: "effective-owner" },
    });
    expect(screen.getByText("OWN-001")).toBeInTheDocument();
    expect(screen.queryByText("DOC-002")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Deterministic check"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Severity"), { target: { value: "low" } });
    expect(screen.queryByText("OWN-001")).not.toBeInTheDocument();
    expect(screen.getByText("DOC-002")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Severity"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Lifecycle status"), { target: { value: "DRAFT" } });
    expect(screen.getByText("DOC-002")).toBeInTheDocument();
    expect(screen.queryByText("OWN-001")).not.toBeInTheDocument();
  });

  it("edits a policy, preserving contract metadata and tag order", async () => {
    await renderAndSelectCore();

    const ownRow = rowForPolicy("OWN-001");
    expect(
      within(ownRow)
        .getAllByText(/^(owner|core)$/)
        .map((chip) => chip.textContent),
    ).toEqual(["owner", "core"]);

    fireEvent.click(within(ownRow).getByRole("button", { name: "Edit policy OWN-001" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Title")).toHaveValue(
      "Every DAG declares an effective owner",
    );
    expect(within(dialog).getByLabelText("Tags")).toHaveValue("owner, core");
    expect(within(dialog).getByLabelText("Configuration")).toHaveValue(
      JSON.stringify(POLICY_OWN.configuration, null, 2),
    );

    fireEvent.change(within(dialog).getByLabelText("Title"), {
      target: { value: "Every DAG declares an accountable owner" },
    });
    fireEvent.change(within(dialog).getByLabelText("Tags"), {
      target: { value: "owner, core, reliability" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(updatePolicyMock).toHaveBeenCalledTimes(1));
    const call = updatePolicyMock.mock.calls[0];
    expect(call?.[0]).toBe("core");
    expect(call?.[1]).toBe("OWN-001");
    const payload = call?.[2] as unknown as Record<string, unknown> | undefined;
    expect(payload?.title).toBe("Every DAG declares an accountable owner");
    expect(payload?.version).toBe("2");
    expect(payload?.status).toBe("ACTIVE");
    expect(payload?.severity).toBe("high");
    expect(payload?.invariant).toBe(POLICY_OWN.invariant);
    expect(payload?.tags).toEqual(["owner", "core", "reliability"]);
    expect(payload?.deterministic_checks).toEqual(["effective-owner"]);
    expect(payload?.configuration).toEqual(POLICY_OWN.configuration);
    expect(payload).not.toHaveProperty("check_kind");
    expect(payload).not.toHaveProperty("check_config");
    expect(payload?.source_document).toBe("standards/ownership.md");
    expect(payload?.source_section).toBe("Owner of record");
    expect(payload?.source_version).toBe("2026-09");
    expect(payload?.safe_path).toBeNull();
    expect(payload?.ownership).toEqual(POLICY_OWN.ownership);
    expect(payload?.scope).toEqual(POLICY_OWN.scope);
    expect(payload?.exceptions).toEqual(POLICY_OWN.exceptions);
    expect(payload?.enforcement).toEqual(POLICY_OWN.enforcement);

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(listPackPoliciesMock).toHaveBeenCalledTimes(2);
  });

  it("rolls back draft changes when the editor is cancelled", async () => {
    await renderAndSelectCore();

    fireEvent.click(screen.getByRole("button", { name: "Edit policy OWN-001" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Title"), {
      target: { value: "Temporary draft title" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Edit policy OWN-001" }));
    const reopened = await screen.findByRole("dialog");
    expect(within(reopened).getByLabelText("Title")).toHaveValue(
      "Every DAG declares an effective owner",
    );
  });

  it("keeps the editor open with a safe error on 422 and shows no success state", async () => {
    updatePolicyMock.mockRejectedValue(
      new ApiError(
        422,
        "req-2",
        "source section was not found",
        "/packs/core/policies/OWN-001 failed with 422",
      ),
    );
    await renderAndSelectCore();

    fireEvent.click(screen.getByRole("button", { name: "Edit policy OWN-001" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Title"), {
      target: { value: "Renamed policy" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));

    const alert = await within(dialog).findByRole("alert");
    expect(alert).toHaveTextContent(/rejected the input/);
    expect(alert).toHaveTextContent("source section was not found");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Title")).toHaveValue("Renamed policy");
  });

  it("blocks saving while the configuration is not valid JSON", async () => {
    await renderAndSelectCore();

    fireEvent.click(screen.getByRole("button", { name: "Edit policy OWN-001" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Configuration"), {
      target: { value: "{not-json" },
    });
    expect(within(dialog).getByText(/must be valid JSON/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Save changes" })).toBeDisabled();

    fireEvent.change(within(dialog).getByLabelText("Configuration"), {
      target: { value: '{"kind": "required-owner"}' },
    });
    expect(within(dialog).queryByText(/must be valid JSON/)).not.toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Save changes" })).toBeEnabled();
  });

  it("sends an explicit empty tag list when tags are cleared", async () => {
    await renderAndSelectCore();

    // An earlier test installs a persistent 422 rejection; make the save in
    // this test succeed explicitly instead of inheriting it.
    updatePolicyMock.mockResolvedValue({ status: "ok", policy_id: "OWN-001" });
    fireEvent.click(screen.getByRole("button", { name: "Edit policy OWN-001" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Tags"), { target: { value: "" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(updatePolicyMock).toHaveBeenCalledTimes(1));
    expect(updatePolicyMock.mock.calls[0]?.[2]?.tags).toEqual([]);
  });

  it("creates a gate and prevents an empty rules list in the client", async () => {
    await renderAndSelectCore();

    fireEvent.click(await screen.findByRole("button", { name: "New gate" }));
    const dialog = await screen.findByRole("dialog");
    const save = within(dialog).getByRole("button", { name: "Save gate" });
    expect(save).toBeDisabled();

    fireEvent.change(within(dialog).getByLabelText("Gate ID"), {
      target: { value: "release-critical" },
    });
    expect(within(dialog).getByText(/At least one rule is required/)).toBeInTheDocument();
    expect(save).toBeDisabled();

    fireEvent.click(within(dialog).getByRole("button", { name: "Add rule" }));
    expect(within(dialog).getByLabelText("Rule 1 type")).toHaveValue("no-new-findings");
    expect(save).toBeEnabled();
    fireEvent.click(save);

    await waitFor(() =>
      expect(upsertGateMock).toHaveBeenCalledWith("core", "release-critical", {
        rules: [{ type: "no-new-findings" }],
      }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(listPackGatesMock).toHaveBeenCalledTimes(2);
  });

  it("replaces gate rules with typed controls for every rule type", async () => {
    await renderAndSelectCore();

    fireEvent.click(await screen.findByRole("button", { name: "Edit gate release" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Gate ID")).toHaveValue("release");
    expect(within(dialog).getByLabelText("Gate ID")).toBeDisabled();
    expect(within(dialog).getByLabelText("Rule 1 type")).toHaveValue("max-severity");
    expect(within(dialog).getByLabelText("Rule 1 severity")).toHaveValue("high");
    expect(within(dialog).getByLabelText("Rule 2 type")).toHaveValue("no-new-findings");

    fireEvent.change(within(dialog).getByLabelText("Rule 1 type"), {
      target: { value: "failure-rate" },
    });
    fireEvent.change(within(dialog).getByLabelText("Rule 1 max percent"), {
      target: { value: "50" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add rule" }));
    fireEvent.change(within(dialog).getByLabelText("Rule 3 type"), {
      target: { value: "always-block" },
    });
    fireEvent.change(within(dialog).getByLabelText("Rule 3 policy IDs"), {
      target: { value: "OWN-001, DOC-002" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save gate" }));

    await waitFor(() =>
      expect(upsertGateMock).toHaveBeenCalledWith("core", "release", {
        rules: [
          { type: "failure-rate", max_percent: 50 },
          { type: "no-new-findings" },
          { type: "always-block", policy_ids: ["OWN-001", "DOC-002"] },
        ],
      }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("shows a server rejection beside the gate form and preserves the draft", async () => {
    upsertGateMock.mockRejectedValue(
      new ApiError(
        422,
        "req-4",
        "rules must not be empty",
        "/packs/core/gates/release failed with 422",
      ),
    );
    await renderAndSelectCore();

    fireEvent.click(await screen.findByRole("button", { name: "Edit gate release" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Rule 1 type"), {
      target: { value: "max-findings" },
    });
    fireEvent.change(within(dialog).getByLabelText("Rule 1 count"), { target: { value: "3" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save gate" }));

    const alert = await within(dialog).findByRole("alert");
    expect(alert).toHaveTextContent(/rejected the input/);
    expect(alert).toHaveTextContent("rules must not be empty");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Rule 1 type")).toHaveValue("max-findings");
    expect(within(dialog).getByLabelText("Rule 1 count")).toHaveValue(3);
  });

  it("validates the pack on demand and shows the server verdict", async () => {
    await renderAndSelectCore();

    validatePackMock.mockResolvedValueOnce({ valid: true, errors: [] });
    fireEvent.click(screen.getByRole("button", { name: "Validate pack" }));
    expect(await screen.findByText("Pack is valid.")).toBeInTheDocument();
    expect(validatePackMock).toHaveBeenCalledWith("core");

    validatePackMock.mockResolvedValueOnce({
      valid: false,
      errors: ["policy DOC-002 requires complete ownership metadata"],
    });
    fireEvent.click(screen.getByRole("button", { name: "Validate pack" }));
    expect(
      await screen.findByText("policy DOC-002 requires complete ownership metadata"),
    ).toBeInTheDocument();
  });

  it("deletes a gate, mapping rejections to an actionable banner", async () => {
    await renderAndSelectCore();

    deleteGateMock.mockRejectedValueOnce(
      new ApiError(
        409,
        "req-3",
        "gate is referenced by a repository",
        "/packs/core/gates/release failed with 409",
      ),
    );
    deleteGateMock.mockResolvedValue({ status: "ok", gate_id: "release" });

    fireEvent.click(await screen.findByRole("button", { name: "Delete gate release" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/rejected the change/);
    expect(alert).toHaveTextContent("gate is referenced by a repository");
    expect(deleteGateMock).toHaveBeenCalledWith("core", "release");

    fireEvent.click(screen.getByRole("button", { name: "Delete gate release" }));
    await waitFor(() => expect(listPackGatesMock).toHaveBeenCalledTimes(2));
  });

  it("maps policy load failures to an actionable banner with retry", async () => {
    loadedPacks();
    listPackPoliciesMock.mockRejectedValue(
      new ApiError(503, "req-9", null, "/packs/core/policies failed with 503"),
    );
    renderPolicies();
    fireEvent.click(await screen.findByRole("button", { name: /core/ }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/temporarily unavailable/i);

    listPackPoliciesMock.mockResolvedValue(POLICIES);
    fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("OWN-001")).toBeInTheDocument();
  });
});
