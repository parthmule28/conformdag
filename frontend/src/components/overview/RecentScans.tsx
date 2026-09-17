import { Link } from "react-router-dom";

import type { OverviewScan } from "../../api";
import { formatTimestamp, gateBadgeStatus, scanBadgeStatus } from "../../hooks/usePlatformQueries";
import { StatusBadge, Table, Td, Th } from "../ui";

export function RecentScans({ scans }: { scans: OverviewScan[] }) {
  return (
    <Table
      caption="Recent scans"
      empty={scans.length === 0}
      emptyMessage="No scans have run yet. Open a repository to trigger one."
    >
      <thead>
        <tr>
          <Th>Repository</Th>
          <Th>Scan</Th>
          <Th>Status</Th>
          <Th>Created</Th>
          <Th>Finished</Th>
          <Th>Gate</Th>
        </tr>
      </thead>
      <tbody>
        {scans.map((scan) => {
          const gate = gateBadgeStatus(scan.gate_passed);
          return (
            <tr key={scan.scan_id}>
              <Td>
                <Link className="text-accent hover:underline" to={`/repos/${scan.repository_id}`}>
                  {scan.repository_name}
                </Link>
              </Td>
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
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}
