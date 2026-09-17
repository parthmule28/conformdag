import { useState } from "react";

import type { Suppression } from "../api";
import { SuppressionEditor } from "../components/suppressions/SuppressionEditor";
import { SuppressionTable } from "../components/suppressions/SuppressionTable";
import { Banner, Button, Card, Select } from "../components/ui";
import {
  describeApiError,
  isSuppressionExpired,
  useSuppressionsQuery,
} from "../hooks/usePlatformQueries";
import { usePageTitle } from "../layout/AppShell";

type StateFilter = "" | "active" | "expired";

/**
 * Operational suppression inventory: state (active/expired) and source
 * filters over the platform's suppression layer, with create/edit forms that
 * reuse the existing suppression routes. Expiry enforcement itself stays on
 * the server; the UI only presents it.
 */
export default function SuppressionsPage() {
  usePageTitle("Suppressions");
  const [stateFilter, setStateFilter] = useState<StateFilter>("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [editorSuppression, setEditorSuppression] = useState<Suppression | "new" | null>(null);

  const suppressionsQuery = useSuppressionsQuery();
  const suppressions = suppressionsQuery.data ?? [];
  const sources = [...new Set(suppressions.map((suppression) => suppression.source))].sort();

  const filtered = suppressions.filter((suppression) => {
    if (stateFilter === "active" && isSuppressionExpired(suppression)) {
      return false;
    }
    if (stateFilter === "expired" && !isSuppressionExpired(suppression)) {
      return false;
    }
    return sourceFilter === "" || suppression.source === sourceFilter;
  });

  return (
    <div className="grid gap-5">
      <Card
        title="Suppressions"
        subtitle="Operational waivers with audit details. The platform enforces expiry at scan time."
        actions={
          <Button onClick={() => setEditorSuppression("new")}>New suppression</Button>
        }
      >
        {suppressionsQuery.isPending ? (
          <p role="status" className="text-sm text-muted">
            Loading suppressions…
          </p>
        ) : suppressionsQuery.isError ? (
          <Banner
            variant="error"
            title="Suppressions could not be loaded"
            action={
              <Button variant="secondary" size="sm" onClick={() => suppressionsQuery.refetch()}>
                Retry
              </Button>
            }
          >
            <p>{describeApiError(suppressionsQuery.error)}</p>
          </Banner>
        ) : (
          <div className="grid gap-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <Select
                label="State"
                value={stateFilter}
                onChange={(event) => {
                  const next = event.target.value;
                  setStateFilter(next === "active" || next === "expired" ? next : "");
                }}
              >
                <option value="">All states</option>
                <option value="active">Active</option>
                <option value="expired">Expired</option>
              </Select>
              <Select
                label="Source"
                value={sourceFilter}
                onChange={(event) => setSourceFilter(event.target.value)}
              >
                <option value="">All sources</option>
                {sources.map((source) => (
                  <option key={source} value={source}>
                    {source}
                  </option>
                ))}
              </Select>
            </div>
            <SuppressionTable
              suppressions={filtered}
              onEdit={(suppression) => setEditorSuppression(suppression)}
            />
          </div>
        )}
      </Card>
      {editorSuppression !== null && (
        <SuppressionEditor
          key={editorSuppression === "new" ? "new" : editorSuppression.id}
          suppression={editorSuppression === "new" ? null : editorSuppression}
          onClose={() => setEditorSuppression(null)}
        />
      )}
    </div>
  );
}
