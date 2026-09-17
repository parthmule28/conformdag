import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import type { Repository } from "../../api";

function SummaryField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-0.5 text-sm text-ink">{children}</dd>
    </div>
  );
}

function NotConfigured() {
  return <span className="text-muted">Not configured</span>;
}

export function RepositorySummary({ repository }: { repository: Repository }) {
  return (
    <section aria-label="Repository configuration">
      <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-4">
        <SummaryField label="Path">
          <span className="break-all font-mono">{repository.path}</span>
        </SummaryField>
        <SummaryField label="Policy pack">
          {repository.policy_pack === null ? <NotConfigured /> : <span className="font-mono">{repository.policy_pack}</span>}
        </SummaryField>
        <SummaryField label="Airflow profile">
          {repository.airflow_profile === null ? <NotConfigured /> : repository.airflow_profile}
        </SummaryField>
        <SummaryField label="Baseline">
          {repository.baseline_scan_id === null ? (
            <span className="text-muted">No baseline set</span>
          ) : (
            <Link
              className="font-mono text-accent hover:underline"
              to={`/scans/${repository.baseline_scan_id}`}
            >
              {repository.baseline_scan_id}
            </Link>
          )}
        </SummaryField>
      </dl>
    </section>
  );
}
