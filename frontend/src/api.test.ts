/**
 * Fixture-based contract tests for the typed /api/v1 client.
 *
 * These tests stub `globalThis.fetch` and pin the stable wire contract only;
 * they intentionally do not import Python, SQLAlchemy, generated server code,
 * or any browser component.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  adminToken,
  cancelScan,
  createSuppression,
  deleteGate,
  deletePolicy,
  exportUrl,
  findings,
  getOverview,
  getRepositoryTrends,
  getScanReport,
  getScanStatus,
  listPackGates,
  listPackPolicies,
  listPacks,
  listRepositories,
  listSuppressions,
  scanHistory,
  setAdminToken,
  setBaseline,
  triggerScan,
  updatePolicy,
  updateSuppression,
  upsertGate,
  upsertPolicy,
  validatePack,
  type GateUpsertRequest,
  type PolicyUpsertRequest,
  type SuppressionInput,
} from "./api";

const fetchMock = vi.fn();

const REPOSITORY_FIXTURE = {
  id: "repo-1",
  name: "etl-core",
  path: "/srv/repos/etl-core",
  policy_pack: "packs/core.yaml",
  airflow_profile: "3.3.0",
};

const SCAN_SUMMARY_FIXTURE = {
  scan_id: "scan-1",
  status: "succeeded",
  created_at: "2026-09-17T10:00:00Z",
  finished_at: "2026-09-17T10:01:30Z",
  result_fingerprint: "fp-abc",
  complete: true,
  gate_passed: true,
  artifact_available: true,
};

const FINDING_FIXTURE = {
  policy_id: "OWN-001",
  policy_version: "2",
  status: "FAIL",
  severity: "HIGH",
  file_path: "dags/load orders.py",
  start_line: 12,
  end_line: 20,
  fingerprint: "fp-own-1",
  explanation: "DAG lacks an effective owner",
  remediation: "Declare owner on every DAG call",
  fix: { fix_kind: "codemod", action: "add-owner", value: "data-platform" },
  suppressed: false,
  baseline_status: "new",
};

const POLICY_FIXTURE = {
  id: "OWN-001",
  title: "Effective owner",
  version: "2",
  status: "ACTIVE",
  severity: "HIGH",
  tags: ["ownership", "core"],
  check_kind: "effective-owner",
  check_config: { owner: "data-platform" },
  source_document: "standards.md",
  source_section: "§3 Owners",
  source_version: "2026-09",
  invariant: "Every DAG declares an effective owner",
  safe_path: "dags/retention.py",
  ownership: {
    owner: "data-platform",
    approvers: ["data-eng"],
    approved_at: "2026-09-01T00:00:00Z",
    review_before: "2027-01-01T00:00:00Z",
    expires_at: null,
  },
  scope: { files: ["dags/**"], operators: [] },
  exceptions: { require_reason: true, require_expiry: true },
  enforcement: {
    type: "blocking",
    deterministic_checks: ["effective-owner"],
    model_check: false,
    allow_abstention: true,
    blocking: true,
  },
};

const GATE_FIXTURE = {
  id: "release-critical",
  rules: [{ type: "max-severity", severity: "HIGH" }],
};

const TREND_POINT_FIXTURE = {
  date: "2026-09-16",
  completed_scan_count: 3,
  fail_finding_count: 2,
  error_finding_count: 1,
  suppressed_finding_count: 4,
  new_finding_count: 1,
};

const OVERVIEW_FIXTURE = {
  repository_count: 2,
  completed_scan_count: 7,
  active_scan_count: 1,
  current_failure_count: 3,
  current_error_count: 1,
  current_new_finding_count: 2,
  trends: [TREND_POINT_FIXTURE],
  recent_scans: [
    {
      scan_id: "scan-9",
      repository_id: "repo-1",
      repository_name: "etl-core",
      status: "running",
      created_at: "2026-09-17T12:00:00Z",
      finished_at: null,
      complete: null,
      gate_passed: null,
    },
  ],
};

const REPORT_FIXTURE = {
  report_version: "2",
  complete: true,
  result_fingerprint: "fp-abc",
  files_scanned: ["dags/example.py"],
  policies_evaluated: ["OWN-001"],
  policies_skipped: [],
  findings: [],
  runtime_observations: [],
  issues: [
    {
      code: "parse-error",
      message: "unexpected indent",
      path: "dags/broken.py",
      phase: "parse",
      fatal: false,
    },
  ],
  gate_result: {
    gate_id: "release-critical",
    passed: false,
    rules: [
      {
        rule_type: "max-severity",
        passed: false,
        detail: "1 failing finding at HIGH",
        matching_findings: 1,
      },
    ],
  },
  run: { timestamp: "2026-09-17T10:00:00Z" },
};

const SUPPRESSION_FIXTURE = {
  id: "sup-1",
  policy_id: "OWN-001",
  fingerprint: "fp-own-1",
  reason: "legacy DAG pending migration",
  owner: "data-platform",
  created_at: "2026-09-01T00:00:00Z",
  expires_at: "2027-01-01T00:00:00Z",
  source: "platform",
};

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers });
}

function lastCall(): { url: string; init: RequestInit } {
  const calls = fetchMock.mock.calls;
  const last = calls[calls.length - 1];
  if (last === undefined) {
    throw new Error("fetch was not called");
  }
  return { url: String(last[0]), init: (last[1] ?? {}) as RequestInit };
}

function headerValue(init: RequestInit, name: string): string | undefined {
  const headers = new Headers(init.headers ?? []);
  const value = headers.get(name);
  return value === null ? undefined : value;
}

async function requestError(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError);
    return error as ApiError;
  }
  throw new Error("expected the request to reject");
}

beforeEach(() => {
  window.sessionStorage.clear();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("admin token transport", () => {
  it("persists the token, sends it as a bearer header, and reads it back", async () => {
    setAdminToken("secret-token");
    expect(adminToken()).toBe("secret-token");
    expect(window.sessionStorage.getItem("conformdag-admin-token")).toBe("secret-token");

    fetchMock.mockResolvedValue(jsonResponse([REPOSITORY_FIXTURE]));
    await listRepositories();

    const { url, init } = lastCall();
    expect(url).toBe("/api/v1/repos");
    expect(init.method).toBeUndefined();
    expect(headerValue(init, "Authorization")).toBe("Bearer secret-token");
  });

  it("removes the session-storage key instead of storing a blank token", () => {
    setAdminToken("secret-token");
    setAdminToken("");
    expect(adminToken()).toBeNull();
    expect(window.sessionStorage.getItem("conformdag-admin-token")).toBeNull();
  });

  it("sends no authorization header when no token is stored", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));
    await listRepositories();
    expect(headerValue(lastCall().init, "Authorization")).toBeUndefined();
  });
});

describe("error contract", () => {
  it("exposes status, request id, and a string detail", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: "scan not found" }, 404, { "X-Request-ID": "req-abc" }),
    );
    const error = await requestError(getScanStatus("scan-1"));
    expect(error.status).toBe(404);
    expect(error.requestId).toBe("req-abc");
    expect(error.detail).toBe("scan not found");
    expect(error.name).toBe("ApiError");
  });

  it("exposes a list detail with a null request id when the header is absent", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: ["title is required", "version is required"] }, 422),
    );
    const error = await requestError(
      upsertPolicy("core-pack", "OWN-001", {
        title: "",
        version: "",
        status: "ACTIVE",
        severity: "HIGH",
        check_kind: "effective-owner",
        check_config: {},
        source_document: "standards.md",
        source_section: "§3 Owners",
        invariant: "invariant",
      }),
    );
    expect(error.status).toBe(422);
    expect(error.requestId).toBeNull();
    expect(error.detail).toEqual(["title is required", "version is required"]);
  });

  it("exposes an object detail", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: { error: "conflict", hint: "scan already finished" } },
        409,
        { "X-Request-ID": "req-409" },
      ),
    );
    const error = await requestError(cancelScan("scan-1"));
    expect(error.status).toBe(409);
    expect(error.requestId).toBe("req-409");
    expect(error.detail).toEqual({ error: "conflict", hint: "scan already finished" });
  });

  it("preserves non-JSON error bodies as the detail", async () => {
    fetchMock.mockResolvedValue(
      new Response("upstream proxy exploded", { status: 502 }),
    );
    const error = await requestError(listRepositories());
    expect(error.status).toBe(502);
    expect(error.requestId).toBeNull();
    expect(error.detail).toBe("upstream proxy exploded");
  });
});

describe("paginated list parsing", () => {
  it("reads scan history totals from X-Total-Count instead of item length", async () => {
    const second = { ...SCAN_SUMMARY_FIXTURE, scan_id: "scan-0", complete: false, gate_passed: null };
    fetchMock.mockResolvedValue(
      jsonResponse([SCAN_SUMMARY_FIXTURE, second], 200, { "X-Total-Count": "7" }),
    );
    const page = await scanHistory("repo-1");
    expect(lastCall().url).toBe("/api/v1/repos/repo-1/scans");
    expect(page.total).toBe(7);
    expect(page.items).toHaveLength(2);
    expect(page.items[0]?.scan_id).toBe("scan-1");
    expect(page.items[0]?.complete).toBe(true);
    expect(page.items[0]?.gate_passed).toBe(true);
    expect(page.items[1]?.complete).toBe(false);
  });

  it("serializes explicit history pagination parameters", async () => {
    fetchMock.mockResolvedValue(jsonResponse([], 200, { "X-Total-Count": "0" }));
    await scanHistory("repo-1", { limit: 25, offset: 50 });
    expect(lastCall().url).toBe("/api/v1/repos/repo-1/scans?limit=25&offset=50");
  });

  it("reads finding totals from X-Total-Count instead of item length", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse([FINDING_FIXTURE], 200, {
        "X-Total-Count": "12",
        "X-Request-ID": "req-42",
      }),
    );
    const page = await findings("scan-1");
    expect(page.total).toBe(12);
    expect(page.items).toHaveLength(1);
    expect(page.items[0]?.end_line).toBe(20);
    expect(page.items[0]?.baseline_status).toBe("new");
    expect(page.items[0]?.fix).toEqual(FINDING_FIXTURE.fix);
  });

  it("fails closed when the page total header is missing", async () => {
    fetchMock.mockResolvedValue(jsonResponse([FINDING_FIXTURE]));
    const error = await requestError(findings("scan-1"));
    expect(error.status).toBe(502);
    expect(error.detail).toBe("response is missing a valid X-Total-Count header");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("omits the query string when no finding filters are set", async () => {
    fetchMock.mockResolvedValue(jsonResponse([], 200, { "X-Total-Count": "0" }));
    await findings("scan-1");
    expect(lastCall().url).toBe("/api/v1/scans/scan-1/findings");
  });

  it("encodes set finding filters exactly once and omits unset ones", async () => {
    fetchMock.mockResolvedValue(jsonResponse([], 200, { "X-Total-Count": "0" }));
    await findings("scan-1", {
      status: "fail",
      severity: "HIGH",
      policy_id: "OWN-001",
      file_path: "dags/load orders.py",
      suppressed: false,
      baseline_status: "new",
      limit: 25,
      offset: 5,
    });
    const { url } = lastCall();
    expect(url).toContain("file_path=dags%2Fload+orders.py");
    const params = new URL(url, "http://localhost").searchParams;
    expect(params.get("file_path")).toBe("dags/load orders.py");
    expect(params.get("policy_id")).toBe("OWN-001");
    expect(params.get("status")).toBe("fail");
    expect(params.get("severity")).toBe("HIGH");
    expect(params.get("suppressed")).toBe("false");
    expect(params.get("baseline_status")).toBe("new");
    expect(params.get("limit")).toBe("25");
    expect(params.get("offset")).toBe("5");
  });

  it("sends only the filters that are set", async () => {
    fetchMock.mockResolvedValue(jsonResponse([], 200, { "X-Total-Count": "0" }));
    await findings("scan-1", { status: "fail" });
    const params = new URL(lastCall().url, "http://localhost").searchParams;
    expect([...params.keys()]).toEqual(["status"]);
  });
});

describe("scan lifecycle routes", () => {
  it("triggers a scan with POST", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ scan_id: "scan-2", status: "queued" }));
    const triggered = await triggerScan("repo-1");
    const { url, init } = lastCall();
    expect(url).toBe("/api/v1/repos/repo-1/scans");
    expect(init.method).toBe("POST");
    expect(triggered).toEqual({ scan_id: "scan-2", status: "queued" });
  });

  it("cancels a scan with POST", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ scan_id: "scan-2", status: "cancelled" }));
    const cancelled = await cancelScan("scan-2");
    const { url, init } = lastCall();
    expect(url).toBe("/api/v1/scans/scan-2/cancel");
    expect(init.method).toBe("POST");
    expect(cancelled).toEqual({ scan_id: "scan-2", status: "cancelled" });
  });

  it("fetches scan status including completion and gate outcome", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        scan_id: "scan-1",
        repository_id: "repo-1",
        status: "succeeded",
        created_at: "2026-09-17T10:00:00Z",
        finished_at: "2026-09-17T10:01:30Z",
        complete: true,
        result_fingerprint: "fp-abc",
        error: null,
        gate_passed: true,
      }),
    );
    const status = await getScanStatus("scan-1");
    expect(lastCall().url).toBe("/api/v1/scans/scan-1");
    expect(status.complete).toBe(true);
    expect(status.gate_passed).toBe(true);
    expect(status.error).toBeNull();
  });

  it("sets the repository baseline with a scan-id body", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ repository_id: "repo-1", baseline_scan_id: "scan-1" }),
    );
    const baseline = await setBaseline("repo-1", "scan-1");
    const { url, init } = lastCall();
    expect(url).toBe("/api/v1/repos/repo-1/baseline");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(String(init.body))).toEqual({ scan_id: "scan-1" });
    expect(baseline).toEqual({ repository_id: "repo-1", baseline_scan_id: "scan-1" });
  });

  it("builds export URLs without invoking fetch", () => {
    expect(exportUrl("scan-1", "sarif")).toBe("/api/v1/scans/scan-1/export/sarif");
    expect(exportUrl("scan-1", "html")).toBe("/api/v1/scans/scan-1/export/html");
    expect(exportUrl("scan-1", "json")).toBe("/api/v1/scans/scan-1/export/json");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("overview and trend routes", () => {
  it("fetches the overview without a days parameter when none is given", async () => {
    fetchMock.mockResolvedValue(jsonResponse(OVERVIEW_FIXTURE));
    const overview = await getOverview();
    expect(lastCall().url).toBe("/api/v1/overview");
    expect(overview.repository_count).toBe(2);
    expect(overview.current_new_finding_count).toBe(2);
    expect(overview.trends[0]?.date).toBe("2026-09-16");
    expect(overview.recent_scans[0]?.repository_name).toBe("etl-core");
  });

  it("serializes the overview days parameter", async () => {
    fetchMock.mockResolvedValue(jsonResponse(OVERVIEW_FIXTURE));
    await getOverview(90);
    expect(lastCall().url).toBe("/api/v1/overview?days=90");
  });

  it("fetches repository trends with an optional days parameter", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ repository_id: "repo-1", points: [TREND_POINT_FIXTURE] }),
    );
    const trends = await getRepositoryTrends("repo-1");
    expect(lastCall().url).toBe("/api/v1/repos/repo-1/trends");
    expect(trends.repository_id).toBe("repo-1");
    expect(trends.points[0]?.new_finding_count).toBe(1);

    fetchMock.mockResolvedValue(jsonResponse({ repository_id: "repo-1", points: [] }));
    await getRepositoryTrends("repo-1", 14);
    expect(lastCall().url).toBe("/api/v1/repos/repo-1/trends?days=14");
  });
});

describe("scan report route", () => {
  it("fetches the canonical report artifact", async () => {
    fetchMock.mockResolvedValue(jsonResponse(REPORT_FIXTURE));
    const report = await getScanReport("scan-1");
    expect(lastCall().url).toBe("/api/v1/scans/scan-1/report");
    expect(report.complete).toBe(true);
    expect(report.result_fingerprint).toBe("fp-abc");
    expect(report.policies_skipped).toEqual([]);
    expect(report.gate_result?.passed).toBe(false);
    expect(report.gate_result?.rules[0]?.rule_type).toBe("max-severity");
    expect(report.issues).toHaveLength(1);
  });
});

describe("suppression routes", () => {
  it("lists suppressions", async () => {
    fetchMock.mockResolvedValue(jsonResponse([SUPPRESSION_FIXTURE]));
    const rows = await listSuppressions();
    expect(lastCall().url).toBe("/api/v1/suppressions");
    expect(rows[0]?.id).toBe("sup-1");
    expect(rows[0]?.source).toBe("platform");
  });

  it("creates a suppression with a JSON body", async () => {
    const input: SuppressionInput = {
      policy_id: "OWN-001",
      fingerprint: "fp-own-1",
      reason: "legacy DAG pending migration",
      owner: "data-platform",
      expires_at: "2027-01-01T00:00:00Z",
    };
    fetchMock.mockResolvedValue(jsonResponse(SUPPRESSION_FIXTURE));
    const created = await createSuppression(input);
    const { url, init } = lastCall();
    expect(url).toBe("/api/v1/suppressions");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual(input);
    expect(created.id).toBe("sup-1");
  });

  it("patches suppression edits", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ...SUPPRESSION_FIXTURE, reason: "still migrating" }));
    const updated = await updateSuppression("sup-1", { reason: "still migrating" });
    const { url, init } = lastCall();
    expect(url).toBe("/api/v1/suppressions/sup-1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(String(init.body))).toEqual({ reason: "still migrating" });
    expect(updated.reason).toBe("still migrating");
  });
});

describe("policy pack routes", () => {
  it("lists packs", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse([
        { name: "core-pack", path: "/packs/core.yaml", id: "core", version: "1", policy_count: 1, error: null },
      ]),
    );
    const packs = await listPacks();
    expect(lastCall().url).toBe("/api/v1/packs");
    expect(packs[0]?.name).toBe("core-pack");
  });

  it("lists policies including tags", async () => {
    fetchMock.mockResolvedValue(jsonResponse([POLICY_FIXTURE]));
    const policies = await listPackPolicies("core-pack");
    expect(lastCall().url).toBe("/api/v1/packs/core-pack/policies");
    expect(policies[0]?.tags).toEqual(["ownership", "core"]);
    expect(policies[0]?.enforcement.deterministic_checks).toEqual(["effective-owner"]);
  });

  it("upserts a policy with PUT and a tags-bearing body", async () => {
    const payload: PolicyUpsertRequest = {
      title: POLICY_FIXTURE.title,
      version: POLICY_FIXTURE.version,
      status: POLICY_FIXTURE.status,
      severity: POLICY_FIXTURE.severity,
      check_kind: POLICY_FIXTURE.check_kind,
      check_config: POLICY_FIXTURE.check_config,
      source_document: POLICY_FIXTURE.source_document,
      source_section: POLICY_FIXTURE.source_section,
      invariant: POLICY_FIXTURE.invariant,
      tags: ["ownership", "core"],
    };
    fetchMock.mockResolvedValue(jsonResponse({ status: "saved", policy_id: "OWN-001" }));
    const saved = await upsertPolicy("core-pack", "OWN-001", payload);
    const { url, init } = lastCall();
    expect(url).toBe("/api/v1/packs/core-pack/policies/OWN-001");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(String(init.body))).toEqual(payload);
    expect(saved).toEqual({ status: "saved", policy_id: "OWN-001" });
  });

  it("exposes updatePolicy on the same route as upsertPolicy", async () => {
    const payload: PolicyUpsertRequest = {
      title: "Effective owner",
      version: "3",
      status: "ACTIVE",
      severity: "HIGH",
      check_kind: "effective-owner",
      check_config: {},
      source_document: "standards.md",
      source_section: "§3 Owners",
      invariant: "invariant",
    };
    fetchMock.mockResolvedValue(jsonResponse({ status: "saved", policy_id: "OWN-001" }));
    await updatePolicy("core-pack", "OWN-001", payload);
    const { url, init } = lastCall();
    expect(url).toBe("/api/v1/packs/core-pack/policies/OWN-001");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(String(init.body))).toEqual(payload);
  });

  it("deletes a policy with DELETE", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: "deleted", policy_id: "OWN-001" }));
    const deleted = await deletePolicy("core-pack", "OWN-001");
    const { url, init } = lastCall();
    expect(url).toBe("/api/v1/packs/core-pack/policies/OWN-001");
    expect(init.method).toBe("DELETE");
    expect(deleted).toEqual({ status: "deleted", policy_id: "OWN-001" });
  });

  it("validates a pack with POST", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ valid: true, errors: [] }));
    const validation = await validatePack("core-pack");
    const { url, init } = lastCall();
    expect(url).toBe("/api/v1/packs/core-pack/validate");
    expect(init.method).toBe("POST");
    expect(validation).toEqual({ valid: true, errors: [] });
  });
});

describe("quality gate routes", () => {
  it("lists gates with their typed rules", async () => {
    fetchMock.mockResolvedValue(jsonResponse([GATE_FIXTURE]));
    const gates = await listPackGates("core-pack");
    expect(lastCall().url).toBe("/api/v1/packs/core-pack/gates");
    expect(gates[0]?.id).toBe("release-critical");
    expect(gates[0]?.rules).toEqual([{ type: "max-severity", severity: "HIGH" }]);
  });

  it("upserts a gate with PUT and a rules body", async () => {
    const payload: GateUpsertRequest = {
      rules: [{ type: "no-new-findings" }, { type: "max-findings", count: 3 }],
    };
    fetchMock.mockResolvedValue(jsonResponse({ status: "saved", gate_id: "release-critical" }));
    const saved = await upsertGate("core-pack", "release-critical", payload);
    const { url, init } = lastCall();
    expect(url).toBe("/api/v1/packs/core-pack/gates/release-critical");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(String(init.body))).toEqual(payload);
    expect(saved).toEqual({ status: "saved", gate_id: "release-critical" });
  });

  it("deletes a gate with DELETE", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: "deleted", gate_id: "release-critical" }));
    const deleted = await deleteGate("core-pack", "release-critical");
    const { url, init } = lastCall();
    expect(url).toBe("/api/v1/packs/core-pack/gates/release-critical");
    expect(init.method).toBe("DELETE");
    expect(deleted).toEqual({ status: "deleted", gate_id: "release-critical" });
  });
});
