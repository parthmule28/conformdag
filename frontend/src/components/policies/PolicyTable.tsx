import type { PolicyInfo } from "../../api";
import { Button, Table, Td, Th } from "../ui";

export interface PolicyTableProps {
  policies: PolicyInfo[];
  onEdit: (policy: PolicyInfo) => void;
}

/**
 * Readable policy rows. Tags render as ordered chips so the pack's tag order
 * is visible; the source cells show the provenance document and section.
 */
export function PolicyTable({ policies, onEdit }: PolicyTableProps) {
  return (
    <Table
      caption="Policies"
      empty={policies.length === 0}
      emptyMessage="No policies match the current filters."
    >
      <thead>
        <tr>
          <Th>Policy</Th>
          <Th>Status</Th>
          <Th>Severity</Th>
          <Th>Check kind</Th>
          <Th>Tags</Th>
          <Th>Source</Th>
          <Th>Actions</Th>
        </tr>
      </thead>
      <tbody>
        {policies.map((policy) => (
          <tr key={policy.id}>
            <Td>
              <div className="font-medium text-ink">{policy.id}</div>
              <div className="text-xs text-muted">{policy.title}</div>
            </Td>
            <Td>{policy.status}</Td>
            <Td>{policy.severity}</Td>
            <Td>{policy.check_kind}</Td>
            <Td>
              {policy.tags.length === 0 ? (
                <span className="text-muted">&mdash;</span>
              ) : (
                <span className="flex flex-wrap gap-1">
                  {policy.tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-sm border border-line bg-sunken px-1.5 py-0.5 text-xs text-muted"
                    >
                      {tag}
                    </span>
                  ))}
                </span>
              )}
            </Td>
            <Td>
              <div>{policy.source_document}</div>
              <div className="text-xs text-muted">{policy.source_section}</div>
            </Td>
            <Td>
              <Button
                variant="secondary"
                size="sm"
                aria-label={`Edit policy ${policy.id}`}
                onClick={() => onEdit(policy)}
              >
                Edit
              </Button>
            </Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
