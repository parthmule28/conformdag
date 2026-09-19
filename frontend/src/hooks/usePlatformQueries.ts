/**
 * Query and mutation layer between the typed client and the console pages.
 *
 * Pages consume hooks only — no fetch or mutation logic lives in components.
 * Polling is bounded (ACTIVE_POLL_INTERVAL_MS) and runs only while scans are
 * queued/running; every mutation invalidates the overview, repository-scoped,
 * and scan-specific query keys explicitly.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ApiError,
  cancelScan,
  createSuppression,
  deleteGate,
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
  setBaseline,
  triggerScan,
  updatePolicy,
  updateSuppression,
  upsertGate,
  validatePack,
} from "../api";
import type {
  FindingParams,
  GateUpsertRequest,
  PolicyUpsertRequest,
  Suppression,
  SuppressionInput,
  SuppressionUpdateInput,
} from "../api";
import type { Status } from "../components/ui";

export const OVERVIEW_DAYS = 30;
export const HISTORY_PAGE_SIZE = 10;
export const ACTIVE_POLL_INTERVAL_MS = 5000;
export const FINDINGS_PAGE_SIZE = 25;

const ACTIVE_SCAN_STATUSES = new Set(["queued", "running"]);

export function isActiveScan(status: string): boolean {
  return ACTIVE_SCAN_STATUSES.has(status);
}

/**
 * Mirrors the documented server contract for baseline eligibility
 * (`succeeded` plus `complete`); the server re-validates and rejects
 * ineligible scans, so the UI never computes baseline state itself.
 */
export function isBaselineEligible(scan: { status: string; complete: boolean | null }): boolean {
  return scan.status === "succeeded" && scan.complete === true;
}

export function scanBadgeStatus(status: string): Status {
  if (status === "succeeded") {
    return "PASS";
  }
  if (status === "failed") {
    return "ERROR";
  }
  if (isActiveScan(status) || status === "cancelled") {
    return "INCOMPLETE";
  }
  return "NOT EVALUATED";
}

/** null when the server did not evaluate a gate result — callers render "Not evaluated". */
export function gateBadgeStatus(gatePassed: boolean | null): Status | null {
  if (gatePassed === true) {
    return "PASS";
  }
  if (gatePassed === false) {
    return "FAIL";
  }
  return null;
}

/**
 * Finding statuses without a badge tone (e.g. NEEDS_REVIEW) return null so
 * callers render the raw status text instead of a misleading badge.
 */
export function findingBadgeStatus(status: string): Status | null {
  switch (status) {
    case "PASS":
      return "PASS";
    case "FAIL":
      return "FAIL";
    case "ERROR":
      return "ERROR";
    default:
      return null;
  }
}

export function formatTimestamp(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return iso;
  }
  const text = parsed.toISOString();
  return `${text.slice(0, 10)} ${text.slice(11, 16)} UTC`;
}

export function describeApiError(error: unknown): string {
  if (error instanceof ApiError) {
    const detail =
      typeof error.detail === "string" && error.detail.trim() !== "" ? error.detail.trim() : null;
    switch (error.status) {
      case 401:
        return "This action needs an admin token. Save one with the header control and try again.";
      case 404:
        return detail === null
          ? "This item does not exist. It may have been removed or never registered."
          : `Not found: ${detail}. It may have been removed or never registered.`;
      case 409:
        return detail === null
          ? "The platform rejected the change because the item changed state. Refresh the page and try again."
          : `The platform rejected the change: ${detail}. Refresh the page to see the current state.`;
      case 422:
        return detail === null
          ? "The platform rejected the input as invalid. Check the values and try again."
          : `The platform rejected the input: ${detail}`;
      case 503:
        return "The platform service is temporarily unavailable. Try again in a moment.";
      default:
        return detail === null
          ? `The request failed with status ${error.status}. Try again.`
          : `The request failed with status ${error.status}: ${detail}`;
    }
  }
  return "Something went wrong while contacting the platform. Try again.";
}

export const queryKeys = {
  overview: (days: number) => ["overview", { days }] as const,
  repositories: () => ["repositories"] as const,
  repositoryTrends: (repositoryId: string, days: number) =>
    ["repositories", repositoryId, "trends", { days }] as const,
  scanHistory: (repositoryId: string, limit: number, offset: number) =>
    ["repositories", repositoryId, "scans", { limit, offset }] as const,
  scanStatus: (scanId: string) => ["scans", scanId, "status"] as const,
  scanReport: (scanId: string) => ["scans", scanId, "report"] as const,
  scanFindings: (scanId: string, params: FindingParams) =>
    ["scans", scanId, "findings", params] as const,
  packs: () => ["packs"] as const,
  packPolicies: (packName: string) => ["packs", packName, "policies"] as const,
  packGates: (packName: string) => ["packs", packName, "gates"] as const,
  suppressions: () => ["suppressions"] as const,
};

/**
 * Toolbar state for finding investigation. Empty strings mean "no filter";
 * `findingsQueryParams` turns this into the exact server contract where
 * unset filters are omitted rather than sent as empty values.
 */
export interface FindingsFilterState {
  status: string;
  severity: string;
  policyId: string;
  filePath: string;
  suppressed: "" | "true" | "false";
  baselineStatus: "" | "new" | "existing";
}

export const EMPTY_FINDINGS_FILTERS: FindingsFilterState = {
  status: "",
  severity: "",
  policyId: "",
  filePath: "",
  suppressed: "",
  baselineStatus: "",
};

export function findingsQueryParams(
  filters: FindingsFilterState,
  limit: number,
  offset: number,
): FindingParams {
  const policyId = filters.policyId.trim();
  const filePath = filters.filePath.trim();
  return {
    status: filters.status === "" ? undefined : filters.status,
    severity: filters.severity === "" ? undefined : filters.severity,
    policy_id: policyId === "" ? undefined : policyId,
    file_path: filePath === "" ? undefined : filePath,
    suppressed: filters.suppressed === "" ? undefined : filters.suppressed === "true",
    baseline_status: filters.baselineStatus === "" ? undefined : filters.baselineStatus,
    limit,
    offset,
  };
}

const OVERVIEW_ROOT = ["overview"] as const;
const SCANS_ROOT = ["scans"] as const;

export function useOverviewQuery(days: number = OVERVIEW_DAYS) {
  return useQuery({
    queryKey: queryKeys.overview(days),
    queryFn: () => getOverview(days),
    refetchInterval: (query) =>
      (query.state.data?.active_scan_count ?? 0) > 0 ? ACTIVE_POLL_INTERVAL_MS : false,
  });
}

export function useRepositoriesQuery() {
  return useQuery({
    queryKey: queryKeys.repositories(),
    queryFn: () => listRepositories(),
  });
}

export function useRepositoryTrendsQuery(repositoryId: string, days: number = OVERVIEW_DAYS) {
  return useQuery({
    queryKey: queryKeys.repositoryTrends(repositoryId, days),
    queryFn: () => getRepositoryTrends(repositoryId, days),
    enabled: repositoryId !== "",
  });
}

export function useScanHistoryQuery(repositoryId: string, limit: number, offset: number) {
  return useQuery({
    queryKey: queryKeys.scanHistory(repositoryId, limit, offset),
    queryFn: () => scanHistory(repositoryId, { limit, offset }),
    enabled: repositoryId !== "",
    placeholderData: keepPreviousData,
    refetchInterval: (query) =>
      (query.state.data?.items.some((scan) => isActiveScan(scan.status)) ?? false)
        ? ACTIVE_POLL_INTERVAL_MS
        : false,
  });
}

export function useScanStatusQuery(scanId: string) {
  return useQuery({
    queryKey: queryKeys.scanStatus(scanId),
    queryFn: () => getScanStatus(scanId),
    enabled: scanId !== "",
    // Polling is bounded and stops on its own once a terminal status arrives.
    refetchInterval: (query) =>
      isActiveScan(query.state.data?.status ?? "") ? ACTIVE_POLL_INTERVAL_MS : false,
  });
}

export function useScanReportQuery(scanId: string, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.scanReport(scanId),
    queryFn: () => getScanReport(scanId),
    // The report artifact is immutable once written, so it is fetched only
    // after the scan reaches a terminal state and never refetched on focus.
    enabled: scanId !== "" && enabled,
    staleTime: Number.POSITIVE_INFINITY,
  });
}

export function useScanFindingsQuery(scanId: string, params: FindingParams) {
  return useQuery({
    queryKey: queryKeys.scanFindings(scanId, params),
    queryFn: () => findings(scanId, params),
    enabled: scanId !== "",
    placeholderData: keepPreviousData,
  });
}

function useInvalidatePlatformQueries(): () => void {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: OVERVIEW_ROOT });
    void queryClient.invalidateQueries({ queryKey: queryKeys.repositories() });
    void queryClient.invalidateQueries({ queryKey: SCANS_ROOT });
  };
}

export function useTriggerScanMutation() {
  const invalidate = useInvalidatePlatformQueries();
  return useMutation({
    mutationFn: (repositoryId: string) => triggerScan(repositoryId),
    onSuccess: () => invalidate(),
  });
}

export function useCancelScanMutation() {
  const invalidate = useInvalidatePlatformQueries();
  return useMutation({
    mutationFn: (scanId: string) => cancelScan(scanId),
    onSuccess: () => invalidate(),
  });
}

export interface SetBaselineInput {
  repositoryId: string;
  scanId: string;
}

export function useSetBaselineMutation() {
  const invalidate = useInvalidatePlatformQueries();
  return useMutation({
    mutationFn: ({ repositoryId, scanId }: SetBaselineInput) => setBaseline(repositoryId, scanId),
    onSuccess: () => invalidate(),
  });
}

const PACKS_ROOT = ["packs"] as const;
const SUPPRESSIONS_ROOT = ["suppressions"] as const;

export function usePacksQuery() {
  return useQuery({
    queryKey: queryKeys.packs(),
    queryFn: () => listPacks(),
  });
}

export function usePackPoliciesQuery(packName: string) {
  return useQuery({
    queryKey: queryKeys.packPolicies(packName),
    queryFn: () => listPackPolicies(packName),
    enabled: packName !== "",
  });
}

export function usePackGatesQuery(packName: string) {
  return useQuery({
    queryKey: queryKeys.packGates(packName),
    queryFn: () => listPackGates(packName),
    enabled: packName !== "",
  });
}

export function useSuppressionsQuery() {
  return useQuery({
    queryKey: queryKeys.suppressions(),
    queryFn: () => listSuppressions(),
  });
}

/**
 * A suppression waives findings only while its expiry is in the future. An
 * unparsable expiry is treated as expired (fail closed) so the UI never
 * presents an unknown record as a current waiver; the server re-checks expiry
 * at scan time.
 */
export function isSuppressionExpired(
  suppression: Pick<Suppression, "expires_at">,
  now: Date = new Date(),
): boolean {
  const expires = new Date(suppression.expires_at);
  return Number.isNaN(expires.getTime()) || expires.getTime() <= now.getTime();
}

export interface UpdatePolicyInput {
  packName: string;
  policyId: string;
  payload: PolicyUpsertRequest;
}

export function useUpdatePolicyMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ packName, policyId, payload }: UpdatePolicyInput) =>
      updatePolicy(packName, policyId, payload),
    onSuccess: () => {
      // The packs root covers the pack summary list plus every pack's policy
      // and gate keys (prefix match), refreshing both in a single pass.
      void queryClient.invalidateQueries({ queryKey: PACKS_ROOT });
    },
  });
}

export interface UpsertGateInput {
  packName: string;
  gateId: string;
  payload: GateUpsertRequest;
}

export function useUpsertGateMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ packName, gateId, payload }: UpsertGateInput) =>
      upsertGate(packName, gateId, payload),
    onSuccess: () => {
      // Gates, pack policies, and pack summaries live under the packs root;
      // recorded scan results are refreshed so stale verdicts are re-read.
      void queryClient.invalidateQueries({ queryKey: PACKS_ROOT });
      void queryClient.invalidateQueries({ queryKey: SCANS_ROOT });
    },
  });
}

export interface DeleteGateInput {
  packName: string;
  gateId: string;
}

export function useDeleteGateMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ packName, gateId }: DeleteGateInput) => deleteGate(packName, gateId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: PACKS_ROOT });
      void queryClient.invalidateQueries({ queryKey: SCANS_ROOT });
    },
  });
}

export function useValidatePackMutation() {
  // A read-only server check over the pack file: nothing to invalidate.
  return useMutation({
    mutationFn: (packName: string) => validatePack(packName),
  });
}

export function useCreateSuppressionMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SuppressionInput) => createSuppression(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SUPPRESSIONS_ROOT });
    },
  });
}

export interface UpdateSuppressionInput {
  id: string;
  payload: SuppressionUpdateInput;
}

export function useUpdateSuppressionMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: UpdateSuppressionInput) => updateSuppression(id, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SUPPRESSIONS_ROOT });
    },
  });
}
