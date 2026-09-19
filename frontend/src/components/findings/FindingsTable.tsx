import type { Finding } from "../../api";
import { findingBadgeStatus } from "../../hooks/usePlatformQueries";
import { Button, StatusBadge, Table, Td, Th } from "../ui";

const EXPLANATION_MAX_LENGTH = 120;

function summarize(text: string | null): string {
  if (text === null) {
    return "\u2014";
  }
  return text.length <= EXPLANATION_MAX_LENGTH
    ? text
    : `${text.slice(0, EXPLANATION_MAX_LENGTH - 1)}\u2026`;
}

function baselineLabel(baseline: Finding["baseline_status"]): string {
  if (baseline === "new") {
    return "New";
  }
  if (baseline === "existing") {
    return "Existing";
  }
  return "\u2014";
}

export interface FindingsTableProps {
  findings: Finding[];
  emptyMessage?: string;
  onInspect: (finding: Finding) => void;
}

export function FindingsTable({ findings, emptyMessage, onInspect }: FindingsTableProps) {
  return (
    <div className="grid gap-2">
      <p className="text-xs text-muted">
        Findings table. Scroll horizontally to see all columns on narrow screens.
      </p>
      <Table
        caption="Findings"
        empty={findings.length === 0}
        emptyMessage={emptyMessage ?? "No findings match the current filters."}
      >
        <thead>
          <tr>
            <Th>Policy</Th>
            <Th>Severity</Th>
            <Th>Status</Th>
            <Th>Location</Th>
            <Th>Suppression</Th>
            <Th>Baseline</Th>
            <Th>Explanation</Th>
            <Th>
              <span className="sr-only">Actions</span>
            </Th>
          </tr>
        </thead>
        <tbody>
          {findings.map((finding) => {
            const badge = findingBadgeStatus(finding.status);
            return (
              <tr key={finding.fingerprint}>
                <Td>
                  <span className="font-mono">{finding.policy_id}</span>{" "}
                  <span className="text-muted">v{finding.policy_version}</span>
                </Td>
                <Td>{finding.severity}</Td>
                <Td>
                  <span className="flex flex-wrap items-center gap-1.5">
                    {badge === null ? (
                      <span className="font-mono text-xs text-muted">{finding.status}</span>
                    ) : (
                      <StatusBadge status={badge} />
                    )}
                    {finding.suppressed && <StatusBadge status="SUPPRESSED" />}
                  </span>
                </Td>
                <Td>
                  {finding.file_path === null ? (
                    <span className="text-muted">{"\u2014"}</span>
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
                </Td>
                <Td>
                  {finding.suppressed ? (
                    <span className="text-suppressed">Suppressed</span>
                  ) : (
                    "Active"
                  )}
                </Td>
                <Td>{baselineLabel(finding.baseline_status)}</Td>
                <Td className="max-w-xs break-words">{summarize(finding.explanation)}</Td>
                <Td>
                  <Button
                    variant="secondary"
                    size="sm"
                    aria-label={`Details for ${finding.policy_id}`}
                    data-tour="finding-details"
                    onClick={() => onInspect(finding)}
                  >
                    Details
                  </Button>
                </Td>
              </tr>
            );
          })}
        </tbody>
      </Table>
    </div>
  );
}
