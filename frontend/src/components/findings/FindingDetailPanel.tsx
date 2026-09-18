import type { Finding, ReportFinding } from "../../api";
import { findingBadgeStatus } from "../../hooks/usePlatformQueries";
import { Banner, StatusBadge } from "../ui";

function DetailField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-0.5 text-sm text-ink">{children}</dd>
    </div>
  );
}

function DetailSection({
  title,
  tourTarget,
  children,
}: {
  title: string;
  tourTarget?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="grid gap-1" data-tour={tourTarget}>
      <h3 className="text-sm font-semibold text-ink">{title}</h3>
      {children}
    </section>
  );
}

export interface FindingDetailPanelProps {
  /** Normalized finding row; always available regardless of artifact retention. */
  finding: Finding;
  /** Matching finding from the canonical report, or null when unavailable. */
  reportFinding: ReportFinding | null;
  /** True when the report artifact is pruned (report endpoint returned 404). */
  artifactUnavailable: boolean;
}

/**
 * Detail view for one finding. Normalized fields render from the finding row;
 * evidence and suppression records come only from the canonical report. When
 * the artifact is pruned, the panel keeps the normalized fields and shows a
 * non-error banner instead of failing.
 */
export function FindingDetailPanel({
  finding,
  reportFinding,
  artifactUnavailable,
}: FindingDetailPanelProps) {
  const badge = findingBadgeStatus(finding.status);
  const evidence = reportFinding?.evidence ?? null;
  const suppression = reportFinding?.suppression ?? null;
  return (
    <div className="grid gap-3 text-sm">
      {finding.suppressed && (
        <Banner variant="info" title="Suppressed finding">
          <p>
            This finding is suppressed. It stays visible here but does not count toward the
            platform's unsuppressed failure totals.
          </p>
        </Banner>
      )}
      {finding.status === "ERROR" && !finding.suppressed && (
        <Banner variant="error" title="Unsuppressed ERROR">
          <p>
            This finding has status ERROR and is not suppressed, so the scan cannot be treated as
            passing its gate.
          </p>
        </Banner>
      )}
      {artifactUnavailable && (
        <Banner variant="info" title="Report artifact unavailable">
          <p>
            The canonical report artifact for this scan has been pruned, so evidence and
            suppression records cannot be shown.
          </p>
        </Banner>
      )}
      <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
        <DetailField label="Status">
          <span className="flex items-center gap-2">
            {badge === null ? (
              <span className="font-mono text-xs text-muted">{finding.status}</span>
            ) : (
              <StatusBadge status={badge} />
            )}
            severity {finding.severity}
          </span>
        </DetailField>
        <DetailField label="Policy">
          <span className="font-mono">
            {finding.policy_id} v{finding.policy_version}
          </span>
        </DetailField>
        <DetailField label="Location">
          {finding.file_path === null ? (
            <span className="text-muted">No file location</span>
          ) : (
            <span className="break-all font-mono">
              {finding.file_path}
              {finding.start_line !== null && (
                <span className="text-muted">
                  {" "}
                  {finding.start_line}
                  {"\u2013"}
                  {finding.end_line ?? finding.start_line}
                </span>
              )}
            </span>
          )}
        </DetailField>
        <DetailField label="Baseline">
          {finding.baseline_status === "new"
            ? "New since the baseline"
            : finding.baseline_status === "existing"
              ? "Existing at the baseline"
              : "Not baseline-compared"}
        </DetailField>
        <DetailField label="Suppression">
          {finding.suppressed ? (
            <span className="text-suppressed">Suppressed</span>
          ) : (
            "Active"
          )}
        </DetailField>
        <DetailField label="Fingerprint">
          <span className="break-all font-mono">{finding.fingerprint}</span>
        </DetailField>
      </dl>
      <DetailSection title="Explanation">
        <p className="break-words">{finding.explanation ?? "No explanation was recorded."}</p>
      </DetailSection>
      <DetailSection title="Remediation" tourTarget="finding-remediation">
        <p className="break-words">{finding.remediation ?? "No remediation was recorded."}</p>
      </DetailSection>
      {finding.fix !== null && (
        <DetailSection title="Fix">
          <pre className="overflow-x-auto rounded-sm border border-line bg-sunken p-2 font-mono text-xs text-ink">
            {JSON.stringify(finding.fix, null, 2)}
          </pre>
        </DetailSection>
      )}
      {evidence !== null && (
        <DetailSection title="Retained evidence">
          <pre className="overflow-x-auto rounded-sm border border-line bg-sunken p-2 font-mono text-xs text-ink">
            {evidence.text}
          </pre>
          {(evidence.start_line !== null || evidence.end_line !== null) && (
            <p className="text-xs text-muted">
              Lines {evidence.start_line ?? "?"}
              {"\u2013"}
              {evidence.end_line ?? "?"}
            </p>
          )}
        </DetailSection>
      )}
      {suppression !== null && (
        <DetailSection title="Suppression record">
          <pre className="overflow-x-auto rounded-sm border border-line bg-sunken p-2 font-mono text-xs text-ink">
            {JSON.stringify(suppression, null, 2)}
          </pre>
        </DetailSection>
      )}
    </div>
  );
}
