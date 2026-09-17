import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import type { ScanStatus } from "../../api";
import {
  formatTimestamp,
  isActiveScan,
  scanBadgeStatus,
} from "../../hooks/usePlatformQueries";
import { Button, StatusBadge } from "../ui";

function statusLabel(status: string): string {
  switch (status) {
    case "queued":
      return "Queued";
    case "running":
      return "Running";
    case "succeeded":
      return "Succeeded";
    case "failed":
      return "Failed";
    case "cancelled":
      return "Cancelled";
    default:
      return status;
  }
}

function completenessLabel(complete: boolean | null): string {
  if (complete === true) {
    return "Complete";
  }
  if (complete === false) {
    return "Incomplete";
  }
  return "Not evaluated";
}

function SummaryField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-0.5 text-sm text-ink">{children}</dd>
    </div>
  );
}

export interface ScanHeaderProps {
  scanId: string;
  status: ScanStatus;
  onCancel: () => void;
  cancelPending: boolean;
}

export function ScanHeader({ scanId, status, onCancel, cancelPending }: ScanHeaderProps) {
  const active = isActiveScan(status.status);
  return (
    <section aria-label="Scan summary">
      <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-4">
        <SummaryField label="Scan">
          <span className="font-mono">{scanId}</span>
        </SummaryField>
        <SummaryField label="Status">
          <span className="flex items-center gap-2">
            <StatusBadge status={scanBadgeStatus(status.status)} />
            {statusLabel(status.status)}
          </span>
        </SummaryField>
        <SummaryField label="Completeness">{completenessLabel(status.complete)}</SummaryField>
        <SummaryField label="Repository">
          <Link className="font-mono text-accent hover:underline" to={`/repos/${status.repository_id}`}>
            {status.repository_id}
          </Link>
        </SummaryField>
        <SummaryField label="Created">
          <span className="whitespace-nowrap">{formatTimestamp(status.created_at)}</span>
        </SummaryField>
        <SummaryField label="Finished">
          <span className="whitespace-nowrap">
            {status.finished_at === null ? "\u2014" : formatTimestamp(status.finished_at)}
          </span>
        </SummaryField>
        <SummaryField label="Result fingerprint">
          {status.result_fingerprint === null ? (
            <span className="text-muted">{"\u2014"}</span>
          ) : (
            <span className="break-all font-mono">{status.result_fingerprint}</span>
          )}
        </SummaryField>
        <SummaryField label="Actions">
          {active ? (
            <Button variant="danger" size="sm" loading={cancelPending} onClick={onCancel}>
              Cancel scan
            </Button>
          ) : (
            <span className="text-muted">{"\u2014"}</span>
          )}
        </SummaryField>
        {status.error !== null && (
          <div className="sm:col-span-2 lg:col-span-4">
            <dt className="text-xs font-medium uppercase tracking-wide text-muted">Error</dt>
            <dd className="mt-0.5 break-words text-sm text-fail">{status.error}</dd>
          </div>
        )}
      </dl>
    </section>
  );
}
