/**
 * Typed client for the stable /api/v1 platform contract.
 *
 * Hand-written for the dashboard; components never construct endpoint URLs and
 * never parse transport details — every call goes through `request()` or
 * `requestPage()`, which own headers, error parsing, and page metadata.
 */

const BASE = "/api/v1";
const TOKEN_KEY = "conformdag-admin-token";

export interface Repository {
  id: string;
  name: string;
  path: string;
  policy_pack: string | null;
  airflow_profile: string | null;
  baseline_scan_id: string | null;
}

export interface ScanSummary {
  scan_id: string;
  status: string;
  created_at: string;
  finished_at: string | null;
  result_fingerprint: string | null;
  complete: boolean | null;
  gate_passed: boolean | null;
  artifact_available: boolean;
}

export interface Finding {
  policy_id: string;
  policy_version: string;
  status: string;
  severity: string;
  file_path: string | null;
  start_line: number | null;
  end_line: number | null;
  fingerprint: string;
  explanation: string | null;
  remediation: string | null;
  fix: Record<string, unknown> | null;
  suppressed: boolean;
  baseline_status: "existing" | "new" | null;
}

export interface Suppression {
  id: string;
  policy_id: string;
  fingerprint: string;
  reason: string;
  owner: string;
  created_at: string;
  expires_at: string;
  source: string;
}

export interface SuppressionInput {
  policy_id: string;
  fingerprint: string;
  reason: string;
  owner: string;
  expires_at: string;
}

export interface SuppressionUpdateInput {
  reason?: string;
  owner?: string;
  expires_at?: string;
}

export interface TrendPoint {
  date: string;
  completed_scan_count: number;
  fail_finding_count: number;
  error_finding_count: number;
  suppressed_finding_count: number;
  new_finding_count: number;
}

export interface OverviewScan {
  scan_id: string;
  repository_id: string;
  repository_name: string;
  status: string;
  created_at: string;
  finished_at: string | null;
  complete: boolean | null;
  gate_passed: boolean | null;
}

export interface OverviewResponse {
  repository_count: number;
  completed_scan_count: number;
  active_scan_count: number;
  current_failure_count: number;
  current_error_count: number;
  current_new_finding_count: number;
  trends: TrendPoint[];
  recent_scans: OverviewScan[];
}

export interface RepositoryTrendsResponse {
  repository_id: string;
  points: TrendPoint[];
}

export interface ScanStatus {
  scan_id: string;
  repository_id: string;
  status: string;
  created_at: string;
  finished_at: string | null;
  complete: boolean | null;
  result_fingerprint: string | null;
  error: string | null;
  gate_passed: boolean | null;
}

export interface GateRuleResult {
  rule_type: string;
  passed: boolean;
  detail: string;
  matching_findings: number;
}

export interface GateResult {
  gate_id: string;
  passed: boolean;
  rules: GateRuleResult[];
}

export interface ReportFindingLocation {
  file: string | null;
  start_line: number | null;
  end_line: number | null;
}

export interface ReportFindingEvidence {
  text: string;
  start_line: number | null;
  end_line: number | null;
  code_hash: string | null;
}

export interface ReportFinding {
  policy_id: string;
  policy_version: string;
  status: string;
  severity: string;
  enforcement: string;
  location: ReportFindingLocation;
  evidence: ReportFindingEvidence | null;
  explanation: string | null;
  remediation: string | null;
  confidence: string | null;
  fix: Record<string, unknown> | null;
  audit_evidence: Record<string, unknown>[];
  fingerprint: string;
  blocking: boolean;
  suppressed: boolean;
  suppression: Record<string, unknown> | null;
}

export interface ReportIssue {
  code: string;
  message: string;
  path: string | null;
  phase: string;
  fatal: boolean;
}

export interface ScanReport {
  report_version: string;
  complete: boolean;
  result_fingerprint: string;
  files_scanned: string[];
  policies_evaluated: string[];
  policies_skipped: string[];
  findings: ReportFinding[];
  runtime_observations: Record<string, unknown>[];
  issues: ReportIssue[];
  gate_result: GateResult | null;
  run: Record<string, unknown>;
}

export type GateRule =
  | { type: "no-new-findings" }
  | { type: "max-severity"; severity: string }
  | { type: "max-findings"; count: number }
  | { type: "always-block"; policy_ids: string[] }
  | { type: "failure-rate"; max_percent: number };

export interface Gate {
  id: string;
  rules: GateRule[];
}

export interface GateUpsertRequest {
  rules: GateRule[];
}

export interface Page<T> {
  items: T[];
  total: number;
}

export interface PageParams {
  limit?: number;
  offset?: number;
}

export interface FindingParams extends PageParams {
  status?: string;
  severity?: string;
  policy_id?: string;
  file_path?: string;
  suppressed?: boolean;
  baseline_status?: "existing" | "new";
}

export interface ScanTransitionResponse {
  scan_id: string;
  status: string;
}

export interface BaselineResponse {
  repository_id: string;
  baseline_scan_id: string;
}

export interface PackSummary {
  name: string;
  path: string;
  id: string | null;
  version: string | null;
  policy_count: number;
  error: string | null;
}

export interface PolicyOwnership {
  owner: string;
  approvers: string[];
  approved_at: string | null;
  review_before: string | null;
  expires_at: string | null;
}

export interface PolicyScope {
  files: string[];
  operators: string[];
}

export interface PolicyExceptions {
  require_reason: boolean;
  require_expiry: boolean;
}

export interface PolicyEnforcement {
  type: string;
  deterministic_checks: string[];
  model_check: boolean;
  allow_abstention: boolean;
  blocking: boolean;
}

export interface PolicyInfo {
  id: string;
  title: string;
  version: string;
  status: string;
  severity: string;
  tags: string[];
  check_kind: string;
  check_config: Record<string, unknown>;
  source_document: string;
  source_section: string;
  source_version: string | null;
  invariant: string;
  safe_path: string | null;
  ownership: PolicyOwnership;
  scope: PolicyScope;
  exceptions: PolicyExceptions;
  enforcement: PolicyEnforcement;
}

export interface PolicyUpsertRequest {
  title: string;
  version: string;
  status: string;
  severity: string;
  check_kind: string;
  check_config: Record<string, unknown>;
  source_document: string;
  source_section: string;
  invariant: string;
  safe_path?: string | null;
  source_version?: string | null;
  ownership?: PolicyOwnership;
  scope?: PolicyScope;
  exceptions?: PolicyExceptions;
  enforcement?: PolicyEnforcement;
  tags?: string[];
}

export interface MutationResponse {
  status: string;
  policy_id?: string;
  gate_id?: string;
}

export interface PackValidation {
  valid: boolean;
  errors: string[];
}

export class ApiError extends Error {
  readonly status: number;
  readonly requestId: string | null;
  readonly detail: unknown;

  constructor(status: number, requestId: string | null, detail: unknown, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.requestId = requestId;
    this.detail = detail;
  }
}

export function adminToken(): string | null {
  return window.sessionStorage.getItem(TOKEN_KEY);
}

export function setAdminToken(token: string): void {
  if (token.trim() === "") {
    window.sessionStorage.removeItem(TOKEN_KEY);
    return;
  }
  window.sessionStorage.setItem(TOKEN_KEY, token);
}

function buildHeaders(init?: RequestInit): HeadersInit {
  const token = adminToken();
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...init?.headers,
  };
}

async function parseDetail(response: Response): Promise<unknown> {
  const text = await response.text();
  if (text === "") {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(text);
    if (parsed !== null && typeof parsed === "object" && "detail" in parsed) {
      return (parsed as { detail: unknown }).detail;
    }
    return parsed;
  } catch {
    return text;
  }
}

async function apiError(path: string, response: Response): Promise<ApiError> {
  const requestId = response.headers.get("X-Request-ID");
  const detail = await parseDetail(response);
  return new ApiError(response.status, requestId, detail, `${path} failed with ${response.status}`);
}

type QueryValue = string | number | boolean | undefined;

function queryString(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) {
      search.set(key, String(value));
    }
  }
  const encoded = search.toString();
  return encoded === "" ? "" : `?${encoded}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { ...init, headers: buildHeaders(init) });
  if (!response.ok) {
    throw await apiError(path, response);
  }
  return (await response.json()) as T;
}

async function requestPage<T>(path: string, init?: RequestInit): Promise<Page<T>> {
  const response = await fetch(`${BASE}${path}`, { ...init, headers: buildHeaders(init) });
  if (!response.ok) {
    throw await apiError(path, response);
  }
  const items = (await response.json()) as T[];
  const total = Number.parseInt(response.headers.get("X-Total-Count") ?? "", 10);
  if (Number.isNaN(total)) {
    throw new ApiError(
      502,
      response.headers.get("X-Request-ID"),
      "response is missing a valid X-Total-Count header",
      `${path} failed with ${response.status}`,
    );
  }
  return { items, total };
}

/* ─── Overview and trends ───────────────────────────────────────── */

export function getOverview(days?: number): Promise<OverviewResponse> {
  return request(`/overview${queryString({ days })}`);
}

export function getRepositoryTrends(repositoryId: string, days?: number): Promise<RepositoryTrendsResponse> {
  return request(`/repos/${encodeURIComponent(repositoryId)}/trends${queryString({ days })}`);
}

/* ─── Repositories and scans ────────────────────────────────────── */

export function listRepositories(): Promise<Repository[]> {
  return request("/repos");
}

export function triggerScan(repositoryId: string): Promise<ScanTransitionResponse> {
  return request(`/repos/${encodeURIComponent(repositoryId)}/scans`, { method: "POST" });
}

export function cancelScan(scanId: string): Promise<ScanTransitionResponse> {
  return request(`/scans/${encodeURIComponent(scanId)}/cancel`, { method: "POST" });
}

export function getScanStatus(scanId: string): Promise<ScanStatus> {
  return request(`/scans/${encodeURIComponent(scanId)}`);
}

export function scanHistory(repositoryId: string, params?: PageParams): Promise<Page<ScanSummary>> {
  return requestPage(
    `/repos/${encodeURIComponent(repositoryId)}/scans${queryString({
      limit: params?.limit,
      offset: params?.offset,
    })}`,
  );
}

export function setBaseline(repositoryId: string, scanId: string): Promise<BaselineResponse> {
  return request(`/repos/${encodeURIComponent(repositoryId)}/baseline`, {
    method: "PUT",
    body: JSON.stringify({ scan_id: scanId }),
  });
}

export function getScanReport(scanId: string): Promise<ScanReport> {
  return request(`/scans/${encodeURIComponent(scanId)}/report`);
}

export function findings(scanId: string, params?: FindingParams): Promise<Page<Finding>> {
  return requestPage(
    `/scans/${encodeURIComponent(scanId)}/findings${queryString({
      status: params?.status,
      severity: params?.severity,
      policy_id: params?.policy_id,
      file_path: params?.file_path,
      suppressed: params?.suppressed,
      baseline_status: params?.baseline_status,
      limit: params?.limit,
      offset: params?.offset,
    })}`,
  );
}

export function exportUrl(scanId: string, format: "sarif" | "html" | "json"): string {
  return `${BASE}/scans/${encodeURIComponent(scanId)}/export/${format}`;
}

/* ─── Suppressions ──────────────────────────────────────────────── */

export function listSuppressions(): Promise<Suppression[]> {
  return request("/suppressions");
}

export function createSuppression(payload: SuppressionInput): Promise<Suppression> {
  return request("/suppressions", { method: "POST", body: JSON.stringify(payload) });
}

export function updateSuppression(id: string, payload: SuppressionUpdateInput): Promise<Suppression> {
  return request(`/suppressions/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

/* ─── Policy packs ──────────────────────────────────────────────── */

export function listPacks(): Promise<PackSummary[]> {
  return request("/packs");
}

export function listPackPolicies(packName: string): Promise<PolicyInfo[]> {
  return request(`/packs/${encodeURIComponent(packName)}/policies`);
}

export function upsertPolicy(
  packName: string,
  policyId: string,
  payload: PolicyUpsertRequest,
): Promise<MutationResponse> {
  return request(`/packs/${encodeURIComponent(packName)}/policies/${encodeURIComponent(policyId)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function updatePolicy(
  packName: string,
  policyId: string,
  payload: PolicyUpsertRequest,
): Promise<MutationResponse> {
  return upsertPolicy(packName, policyId, payload);
}

export function deletePolicy(packName: string, policyId: string): Promise<MutationResponse> {
  return request(`/packs/${encodeURIComponent(packName)}/policies/${encodeURIComponent(policyId)}`, {
    method: "DELETE",
  });
}

export function validatePack(packName: string): Promise<PackValidation> {
  return request(`/packs/${encodeURIComponent(packName)}/validate`, { method: "POST" });
}

/* ─── Quality gates ─────────────────────────────────────────────── */

export function listPackGates(packName: string): Promise<Gate[]> {
  return request(`/packs/${encodeURIComponent(packName)}/gates`);
}

export function upsertGate(
  packName: string,
  gateId: string,
  payload: GateUpsertRequest,
): Promise<MutationResponse> {
  return request(`/packs/${encodeURIComponent(packName)}/gates/${encodeURIComponent(gateId)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteGate(packName: string, gateId: string): Promise<MutationResponse> {
  return request(`/packs/${encodeURIComponent(packName)}/gates/${encodeURIComponent(gateId)}`, {
    method: "DELETE",
  });
}
