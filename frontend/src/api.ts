/**
 * Typed client for the stable /api/v1 platform contract.
 *
 * Hand-written for the dashboard; generate from the OpenAPI document with
 * openapi-typescript once the surface settles further.
 */

const BASE = "/api/v1";

export interface Repository {
  id: string;
  name: string;
  path: string;
  policy_pack: string | null;
  airflow_profile: string | null;
}

export interface ScanSummary {
  scan_id: string;
  status: string;
  created_at: string;
  finished_at: string | null;
  result_fingerprint: string | null;
}

export interface Finding {
  policy_id: string;
  policy_version: string;
  status: string;
  severity: string;
  file_path: string | null;
  start_line: number | null;
  fingerprint: string;
  explanation: string | null;
  remediation: string | null;
  suppressed: boolean;
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

export function adminToken(): string | null {
  return window.sessionStorage.getItem("conformdag-admin-token");
}

export function setAdminToken(token: string): void {
  window.sessionStorage.setItem("conformdag-admin-token", token);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = adminToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
  const response = await fetch(`${BASE}${path}`, { headers, ...init });
  if (!response.ok) {
    throw new Error(`${path} failed with ${response.status}`);
  }
  return (await response.json()) as T;
}

export function listRepositories(): Promise<Repository[]> {
  return request<Repository[]>("/repos");
}

export function scanHistory(repositoryId: string): Promise<ScanSummary[]> {
  return request<ScanSummary[]>(`/repos/${repositoryId}/scans`);
}

export function findings(scanId: string, status?: string): Promise<Finding[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return request<Finding[]>(`/scans/${scanId}/findings${query}`);
}

export function triggerScan(repositoryId: string): Promise<{ scan_id: string }> {
  return request(`/repos/${repositoryId}/scans`, { method: "POST" });
}

export function listSuppressions(): Promise<Suppression[]> {
  return request<Suppression[]>("/suppressions");
}

export function createSuppression(payload: SuppressionInput): Promise<Suppression> {
  return request("/suppressions", { method: "POST", body: JSON.stringify(payload) });
}

export function updateSuppression(
  id: string,
  payload: { reason?: string; owner?: string; expires_at?: string },
): Promise<Suppression> {
  return request(`/suppressions/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function exportUrl(scanId: string, format: "sarif" | "html" | "json"): string {
  return `${BASE}/scans/${scanId}/export/${format}`;
}
