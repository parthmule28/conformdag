import { Link } from "react-router-dom";

import type { Suppression } from "../../api";
import { formatTimestamp, isSuppressionExpired } from "../../hooks/usePlatformQueries";
import { Button, StatusBadge, Table, Td, Th } from "../ui";

export interface SuppressionTableProps {
  suppressions: Suppression[];
  onEdit: (suppression: Suppression) => void;
}

/**
 * Suppression inventory rows. Active waivers carry the SUPPRESSED badge;
 * expired rows get a distinct muted "Expired" treatment — the server, not the
 * UI, decides what actually waives a finding at scan time. Policy IDs link to
 * the policies page.
 */
export function SuppressionTable({ suppressions, onEdit }: SuppressionTableProps) {
  return (
    <Table
      caption="Suppressions"
      empty={suppressions.length === 0}
      emptyMessage="No suppressions match the current filters."
    >
      <thead>
        <tr>
          <Th>Policy</Th>
          <Th>Fingerprint</Th>
          <Th>Reason</Th>
          <Th>Owner</Th>
          <Th>Created</Th>
          <Th>Expires</Th>
          <Th>Status</Th>
          <Th>Actions</Th>
        </tr>
      </thead>
      <tbody>
        {suppressions.map((suppression) => {
          const expired = isSuppressionExpired(suppression);
          return (
            <tr key={suppression.id} className={expired ? "opacity-60" : undefined}>
              <Td>
                <Link className="font-medium text-accent hover:underline" to="/policies">
                  {suppression.policy_id}
                </Link>
              </Td>
              <Td>
                <code className="text-xs">{suppression.fingerprint}</code>
              </Td>
              <Td>{suppression.reason}</Td>
              <Td>{suppression.owner}</Td>
              <Td>{formatTimestamp(suppression.created_at)}</Td>
              <Td>{formatTimestamp(suppression.expires_at)}</Td>
              <Td>
                {expired ? (
                  <span className="inline-flex items-center whitespace-nowrap rounded-sm border border-line bg-sunken px-1.5 py-0.5 text-xs font-medium text-muted">
                    Expired
                  </span>
                ) : (
                  <StatusBadge status="SUPPRESSED" />
                )}
              </Td>
              <Td>
                <Button
                  variant="secondary"
                  size="sm"
                  aria-label={`Edit suppression ${suppression.id}`}
                  onClick={() => onEdit(suppression)}
                >
                  Edit
                </Button>
              </Td>
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}
