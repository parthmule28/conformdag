import type { FindingsFilterState } from "../../hooks/usePlatformQueries";
import { Input, Select } from "../ui";

const STATUS_OPTIONS = ["FAIL", "ERROR", "PASS", "NEEDS_REVIEW", "SKIPPED", "NOT_APPLICABLE"];
const SEVERITY_OPTIONS = ["info", "low", "medium", "high", "critical"];
const PAGE_SIZE_OPTIONS = [10, 25, 50];

export interface FindingsToolbarProps {
  filters: FindingsFilterState;
  pageSize: number;
  /** Applies one filter patch; the page resets to 1 and the query reloads. */
  onChange: (patch: Partial<FindingsFilterState>) => void;
  onPageSizeChange: (pageSize: number) => void;
}

/**
 * Controls for the exact server-side finding filters. Every control maps
 * straight onto a `findings()` query parameter; nothing is filtered in the
 * browser.
 */
export function FindingsToolbar({
  filters,
  pageSize,
  onChange,
  onPageSizeChange,
}: FindingsToolbarProps) {
  return (
    <section aria-label="Finding filters" className="grid gap-3">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Select
          label="Status"
          value={filters.status}
          onChange={(event) => onChange({ status: event.target.value })}
        >
          <option value="">All statuses</option>
          {STATUS_OPTIONS.map((status) => (
            <option key={status} value={status}>
              {status}
            </option>
          ))}
        </Select>
        <Select
          label="Severity"
          value={filters.severity}
          onChange={(event) => onChange({ severity: event.target.value })}
        >
          <option value="">All severities</option>
          {SEVERITY_OPTIONS.map((severity) => (
            <option key={severity} value={severity}>
              {severity}
            </option>
          ))}
        </Select>
        <Input
          label="Policy ID"
          type="text"
          placeholder="e.g. OWN-001"
          value={filters.policyId}
          onChange={(event) => onChange({ policyId: event.target.value })}
        />
        <Input
          label="File path"
          type="text"
          placeholder="dags/example.py"
          value={filters.filePath}
          onChange={(event) => onChange({ filePath: event.target.value })}
        />
        <Select
          label="Suppressed"
          value={filters.suppressed}
          onChange={(event) =>
            onChange({ suppressed: event.target.value as FindingsFilterState["suppressed"] })
          }
        >
          <option value="">All findings</option>
          <option value="true">Suppressed only</option>
          <option value="false">Not suppressed</option>
        </Select>
        <Select
          label="Baseline"
          value={filters.baselineStatus}
          onChange={(event) =>
            onChange({
              baselineStatus: event.target.value as FindingsFilterState["baselineStatus"],
            })
          }
        >
          <option value="">All findings</option>
          <option value="new">New findings</option>
          <option value="existing">Existing findings</option>
        </Select>
        <Select
          label="Per page"
          value={String(pageSize)}
          onChange={(event) => onPageSizeChange(Number.parseInt(event.target.value, 10))}
        >
          {PAGE_SIZE_OPTIONS.map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </Select>
      </div>
    </section>
  );
}
