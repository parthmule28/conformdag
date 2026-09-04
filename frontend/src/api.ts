/**
 * Typed client for the stable /api/v1 platform contract.
 *
 * Hand-written for the scaffold; generate from the OpenAPI document with
 * openapi-typescript once the dashboard surface settles.
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...authHeaders() },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`${path} failed with ${response.status}`);
  }
  return (await response.json()) as T;
}

function authHeaders(): Record<string, string> {
  const token = window.sessionStorage.getItem("conformdag-admin-token");
  return token ? { Authorization: `Bearer ${token}` } : {};
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
