import { Link } from "react-router-dom";

import { exportUrl, type ScanSummary } from "../../api";
import {
  formatTimestamp,
  gateBadgeStatus,
  isBaselineEligible,
  isActiveScan,
  scanBadgeStatus,
} from "../../hooks/usePlatformQueries";
import { Button, StatusBadge, Table, Td, Th } from "../ui";

export interface ScanHistoryTableProps {
  scans: ScanSummary[];
  baselineScanId: string | null;
  /** Scan a pending cancel/baseline action is working on, if any. */
  busyScanId: string | null;
  onSetBaseline: (scanId: string) => void;
  onCancel: (scanId: string) => void;
}

export function ScanHistoryTable({
  scans,
  baselineScanId,
  busyScanId,
  onSetBaseline,
  onCancel,
}: ScanHistoryTableProps) {
  const busy = busyScanId !== null;
  return (
    <Table
      caption="Scan history"
      empty={scans.length === 0}
      emptyMessage="No scans have run yet. Trigger the first scan to start building history."
    >
      <thead>
        <tr>
          <Th>Scan</Th>
          <Th>Status</Th>
          <Th>Created</Th>
          <Th>Finished</Th>
          <Th>Gate</Th>
          <Th>Exports</Th>
          <Th>Actions</Th>
        </tr>
      </thead>
      <tbody>
        {scans.map((scan) => {
          const gate = gateBadgeStatus(scan.gate_passed);
          const isCurrentBaseline = scan.scan_id === baselineScanId;
          const rowBusy = scan.scan_id === busyScanId;
          return (
            <tr key={scan.scan_id}>
              <Td>
                <Link className="font-mono text-accent hover:underline" to={`/scans/${scan.scan_id}`}>
                  {scan.scan_id}
                </Link>
              </Td>
              <Td>
                <StatusBadge status={scanBadgeStatus(scan.status)} />
              </Td>
              <Td className="whitespace-nowrap">{formatTimestamp(scan.created_at)}</Td>
              <Td className="whitespace-nowrap">
                {scan.finished_at === null ? "\u2014" : formatTimestamp(scan.finished_at)}
              </Td>
              <Td>
                {gate === null ? (
                  <span className="text-muted">Not evaluated</span>
                ) : (
                  <StatusBadge status={gate} />
                )}
              </Td>
              <Td>
                {scan.complete === true ? (
                  <span className="flex flex-wrap gap-x-2 gap-y-1">
                    <ExportLink scanId={scan.scan_id} format="json" />
                    <ExportLink scanId={scan.scan_id} format="sarif" />
                    <ExportLink scanId={scan.scan_id} format="html" />
                  </span>
                ) : (
                  <span className="text-muted">{"\u2014"}</span>
                )}
              </Td>
              <Td>
                {isBaselineEligible(scan) ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={rowBusy}
                    disabled={busy || isCurrentBaseline}
                    title={isCurrentBaseline ? "This scan is the current baseline" : undefined}
                    onClick={() => onSetBaseline(scan.scan_id)}
                  >
                    {isCurrentBaseline ? "Current baseline" : "Set as baseline"}
                  </Button>
                ) : isActiveScan(scan.status) ? (
                  <Button
                    variant="danger"
                    size="sm"
                    loading={rowBusy}
                    disabled={busy}
                    onClick={() => onCancel(scan.scan_id)}
                  >
                    Cancel
                  </Button>
                ) : (
                  <span className="text-muted">{"\u2014"}</span>
                )}
              </Td>
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}

function ExportLink({ scanId, format }: { scanId: string; format: "json" | "sarif" | "html" }) {
  return (
    <a className="text-accent hover:underline" href={exportUrl(scanId, format)}>
      {format.toUpperCase()}
    </a>
  );
}
