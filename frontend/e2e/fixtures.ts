/**
 * Shared helpers for the platform browser journeys.
 *
 * Every journey drives the real production console against the real
 * `/api/v1` HTTP routes served by the disposable platform seed process
 * (`scripts/e2e_platform.py`). Test-side reads (resolving seeded ids) go
 * through the same-origin request context; the browser itself uses the
 * production typed client. No endpoint is mocked.
 */
import { expect, test as base, type APIRequestContext, type Page } from "@playwright/test";

import type { Finding, Repository, ScanSummary, Suppression } from "../src/api";

/** The seeded admin token; the seed process is started with the same value. */
export const ADMIN_TOKEN = process.env.CONFORMDAG_PLATFORM_TOKEN ?? "secret-token";

const TOKEN_STORAGE_KEY = "conformdag-admin-token";

/** Names the seed process registers; see scripts/e2e_platform.py. */
export const HEALTHY_REPOSITORY_NAME = "e2e-healthy";
export const BROKEN_REPOSITORY_NAME = "e2e-broken";

/**
 * Installs the admin token in sessionStorage before any app script runs, the
 * same storage the shell's token control writes to. The token comes from the
 * test environment, never from production.
 */
export async function useAdminToken(page: Page): Promise<void> {
  await page.addInitScript(
    ([key, token]) => {
      window.sessionStorage.setItem(key, token);
    },
    [TOKEN_STORAGE_KEY, ADMIN_TOKEN] as const,
  );
}

/** Reads one `/api/v1` collection through the real HTTP routes. */
async function apiGet<T>(request: APIRequestContext, path: string): Promise<T> {
  const response = await request.get(`/api/v1${path}`);
  expect(response.ok(), `GET ${path} failed with ${response.status()}`).toBe(true);
  return (await response.json()) as T;
}

export async function repositoryByName(
  request: APIRequestContext,
  name: string,
): Promise<Repository> {
  const repositories = await apiGet<Repository[]>(request, "/repos");
  const match = repositories.find((repository) => repository.name === name);
  expect(match, `repository ${name} is seeded`).toBeDefined();
  return match as Repository;
}

export async function scanHistory(
  request: APIRequestContext,
  repositoryId: string,
): Promise<ScanSummary[]> {
  return apiGet<ScanSummary[]>(request, `/repos/${repositoryId}/scans`);
}

/** Reads every FAIL finding of one scan through the real HTTP route. */
export async function failFindings(
  request: APIRequestContext,
  scanId: string,
): Promise<Finding[]> {
  const response = await request.get(`/api/v1/scans/${scanId}/findings?status=FAIL`);
  expect(response.ok(), `GET findings for ${scanId} failed with ${response.status()}`).toBe(true);
  return (await response.json()) as Finding[];
}

export async function firstFinding(
  request: APIRequestContext,
  scanId: string,
): Promise<Finding> {
  const items = await failFindings(request, scanId);
  expect(items.length, `scan ${scanId} seeds at least one FAIL finding`).toBeGreaterThan(0);
  return items[0] as Finding;
}

/**
 * Resolves the repository's current completed scan: the newest complete entry
 * of the scan history (the history route returns newest first).
 */
export async function currentCompletedScan(
  request: APIRequestContext,
  repositoryId: string,
): Promise<ScanSummary> {
  const scans = await scanHistory(request, repositoryId);
  const current = scans.find((scan) => scan.complete === true);
  expect(current, `repository ${repositoryId} has a completed scan`).toBeDefined();
  return current as ScanSummary;
}

/**
 * Mirrors the console's expiry rule (hooks/usePlatformQueries): an unparsable
 * or past expiry counts as expired so nothing unknown is presented as a
 * current waiver. The server re-checks expiry at scan time.
 */
export function isSuppressionExpired(suppression: Suppression, now: Date = new Date()): boolean {
  const expires = new Date(suppression.expires_at);
  return Number.isNaN(expires.getTime()) || expires.getTime() <= now.getTime();
}

export interface SuppressionStates {
  active: Suppression[];
  expired: Suppression[];
}

/** Splits the suppression inventory into active and expired records by API data. */
export async function suppressionsByState(
  request: APIRequestContext,
): Promise<SuppressionStates> {
  const response = await request.get("/api/v1/suppressions");
  expect(response.ok(), `GET suppressions failed with ${response.status()}`).toBe(true);
  const items = (await response.json()) as Suppression[];
  return {
    active: items.filter((suppression) => !isSuppressionExpired(suppression)),
    expired: items.filter((suppression) => isSuppressionExpired(suppression)),
  };
}

export const test = base.extend({});
export { expect };
