import { useState } from "react";

import type { PolicyInfo } from "../api";
import { GateEditor } from "../components/policies/GateEditor";
import { PackList } from "../components/policies/PackList";
import { PolicyEditor } from "../components/policies/PolicyEditor";
import { PolicyTable } from "../components/policies/PolicyTable";
import { Banner, Button, Card, EmptyState, Select } from "../components/ui";
import {
  describeApiError,
  usePackGatesQuery,
  usePackPoliciesQuery,
  usePacksQuery,
} from "../hooks/usePlatformQueries";
import { usePageTitle } from "../layout/AppShell";

const SEVERITIES = ["info", "low", "medium", "high", "critical"] as const;

const LIFECYCLE_STATUSES = [
  "DRAFT",
  "APPROVED",
  "ACTIVE",
  "CONFLICTED",
  "DEPRECATED",
  "REJECTED",
] as const;

interface PolicyFilterState {
  tag: string;
  checkKind: string;
  severity: string;
  status: string;
}

const EMPTY_FILTERS: PolicyFilterState = { tag: "", checkKind: "", severity: "", status: "" };

/**
 * Policy governance surface: pack summaries with server-reported validation
 * state, a selected pack's policies with filters and the lossless editor, and
 * the pack's quality gates. All validation and gate evaluation is delegated
 * to the platform.
 */
export default function PoliciesPage() {
  usePageTitle("Policies");
  const packsQuery = usePacksQuery();
  const [selectedPack, setSelectedPack] = useState<string | null>(null);
  const [filters, setFilters] = useState<PolicyFilterState>(EMPTY_FILTERS);
  const [editing, setEditing] = useState<PolicyInfo | null>(null);

  const packs = packsQuery.data ?? [];
  const packName = selectedPack ?? "";
  const policiesQuery = usePackPoliciesQuery(packName);
  const gatesQuery = usePackGatesQuery(packName);
  const policies = policiesQuery.data ?? [];

  const selectPack = (name: string): void => {
    setSelectedPack(name);
    setFilters(EMPTY_FILTERS);
  };

  const patchFilters = (part: Partial<PolicyFilterState>): void => {
    setFilters((previous) => ({ ...previous, ...part }));
  };

  const tagOptions = [...new Set(policies.flatMap((policy) => policy.tags))].sort();
  const kindOptions = [...new Set(policies.map((policy) => policy.check_kind))].sort();
  const filteredPolicies = policies.filter(
    (policy) =>
      (filters.tag === "" || policy.tags.includes(filters.tag)) &&
      (filters.checkKind === "" || policy.check_kind === filters.checkKind) &&
      (filters.severity === "" || policy.severity === filters.severity) &&
      (filters.status === "" || policy.status === filters.status),
  );

  return (
    <div className="grid gap-5">
      <Card title="Policy packs" subtitle="Select a pack to manage its policies and quality gates.">
        {packsQuery.isPending ? (
          <p role="status" className="text-sm text-muted">
            Loading packs…
          </p>
        ) : packsQuery.isError ? (
          <Banner
            variant="error"
            title="Policy packs could not be loaded"
            action={
              <Button variant="secondary" size="sm" onClick={() => packsQuery.refetch()}>
                Retry
              </Button>
            }
          >
            <p>{describeApiError(packsQuery.error)}</p>
          </Banner>
        ) : packs.length === 0 ? (
          <EmptyState
            title="No policy packs"
            description="Register a pack in the workspace file to manage it here."
          />
        ) : (
          <PackList packs={packs} selected={selectedPack} onSelect={selectPack} />
        )}
      </Card>
      {packName !== "" && (
        <>
          <Card
            title={`Policies in ${packName}`}
            subtitle="Filters narrow the pack's loaded policies; edits are validated by the platform."
          >
            <div className="grid gap-3">
              <div className="grid gap-3 sm:grid-cols-4">
                <Select
                  label="Domain tag"
                  value={filters.tag}
                  onChange={(event) => patchFilters({ tag: event.target.value })}
                >
                  <option value="">All tags</option>
                  {tagOptions.map((tag) => (
                    <option key={tag} value={tag}>
                      {tag}
                    </option>
                  ))}
                </Select>
                <Select
                  label="Check kind"
                  value={filters.checkKind}
                  onChange={(event) => patchFilters({ checkKind: event.target.value })}
                >
                  <option value="">All kinds</option>
                  {kindOptions.map((kind) => (
                    <option key={kind} value={kind}>
                      {kind}
                    </option>
                  ))}
                </Select>
                <Select
                  label="Severity"
                  value={filters.severity}
                  onChange={(event) => patchFilters({ severity: event.target.value })}
                >
                  <option value="">All severities</option>
                  {SEVERITIES.map((severity) => (
                    <option key={severity} value={severity}>
                      {severity}
                    </option>
                  ))}
                </Select>
                <Select
                  label="Lifecycle status"
                  value={filters.status}
                  onChange={(event) => patchFilters({ status: event.target.value })}
                >
                  <option value="">All statuses</option>
                  {LIFECYCLE_STATUSES.map((status) => (
                    <option key={status} value={status}>
                      {status}
                    </option>
                  ))}
                </Select>
              </div>
              {policiesQuery.isPending ? (
                <p role="status" className="text-sm text-muted">
                  Loading policies…
                </p>
              ) : policiesQuery.isError ? (
                <Banner
                  variant="error"
                  title="Policies could not be loaded"
                  action={
                    <Button variant="secondary" size="sm" onClick={() => policiesQuery.refetch()}>
                      Retry
                    </Button>
                  }
                >
                  <p>{describeApiError(policiesQuery.error)}</p>
                </Banner>
              ) : (
                <PolicyTable policies={filteredPolicies} onEdit={setEditing} />
              )}
            </div>
          </Card>
          <Card
            title={`Quality gates in ${packName}`}
            subtitle="The platform validates gate rules on save and evaluates them during scans."
          >
            {gatesQuery.isPending ? (
              <p role="status" className="text-sm text-muted">
                Loading gates…
              </p>
            ) : gatesQuery.isError ? (
              <Banner
                variant="error"
                title="Quality gates could not be loaded"
                action={
                  <Button variant="secondary" size="sm" onClick={() => gatesQuery.refetch()}>
                    Retry
                  </Button>
                }
              >
                <p>{describeApiError(gatesQuery.error)}</p>
              </Banner>
            ) : (
              <div data-tour="policy-gate">
                <GateEditor packName={packName} gates={gatesQuery.data ?? []} />
              </div>
            )}
          </Card>
        </>
      )}
      {editing !== null && (
        <PolicyEditor
          key={editing.id}
          packName={packName}
          policy={editing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}
