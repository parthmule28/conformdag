import { QueryClient, QueryClientProvider, useMutation, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import {
  adminToken,
  createSuppression,
  exportUrl,
  findings,
  listRepositories,
  listSuppressions,
  scanHistory,
  setAdminToken,
  triggerScan,
  updateSuppression,
  type Finding,
  type Repository,
  type ScanSummary,
  type Suppression,
} from "./api";

const queryClient = new QueryClient();

function App() {
  const [token, setToken] = useState(adminToken() ?? "");
  return (
    <QueryClientProvider client={queryClient}>
      <main className="mx-auto max-w-5xl p-8">
        <h1 className="mb-2 text-2xl font-semibold">ConformDAG Platform</h1>
        <TokenBar token={token} onSet={(next) => { setAdminToken(next); setToken(next); }} />
        <SuppressionsPanel />
        <h2 className="mt-8 mb-2 text-xl font-semibold">Repositories</h2>
        <RepositoryList />
      </main>
    </QueryClientProvider>
  );
}

function TokenBar({ token, onSet }: { token: string; onSet: (token: string) => void }) {
  return (
    <form
      className="mb-6 flex items-center gap-2"
      onSubmit={(event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        const input = event.currentTarget.elements.namedItem("admin-token") as HTMLInputElement;
        onSet(input.value);
      }}
    >
      <input
        className="rounded border border-gray-300 px-2 py-1 text-sm"
        type="password"
        name="admin-token"
        placeholder="Admin token (kept in this tab only)"
        defaultValue={token}
      />
      <button className="rounded bg-gray-700 px-3 py-1 text-sm text-white hover:bg-gray-800">
        Save
      </button>
      <span className="text-sm text-gray-500">
        Required for scans, suppressions, and workspace registration
      </span>
    </form>
  );
}

function RepositoryList() {
  const repositories = useQuery({ queryKey: ["repos"], queryFn: listRepositories });

  if (repositories.isLoading) {
    return <p className="text-gray-500">Loading repositories…</p>;
  }
  if (repositories.isError) {
    return <p className="text-red-600">Failed to load repositories.</p>;
  }
  return (
    <div className="grid gap-4">
      {(repositories.data ?? []).map((repository: Repository) => (
        <RepositoryCard key={repository.id} repository={repository} />
      ))}
    </div>
  );
}

function RepositoryCard({ repository }: { repository: Repository }) {
  const history = useQuery({
    queryKey: ["scans", repository.id],
    queryFn: () => scanHistory(repository.id),
    refetchInterval: (query) => {
      const statuses = query.state.data?.map((scan: ScanSummary) => scan.status) ?? [];
      const active = statuses.some((status) => status === "queued" || status === "running");
      return active ? 2000 : false;
    },
  });
  const scans = history.data ?? [];
  const latest = scans[0];
  const latestFindings = useQuery({
    queryKey: ["findings", latest?.scan_id],
    queryFn: () => (latest ? findings(latest.scan_id, "fail") : Promise.resolve([])),
    enabled: latest !== undefined && latest.status === "succeeded",
  });
  const trigger = useMutation({
    mutationFn: () => triggerScan(repository.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scans", repository.id] }),
  });

  return (
    <section className="rounded-lg border border-gray-200 p-4">
      <header className="flex items-center justify-between">
        <div>
          <h3 className="font-medium">{repository.name}</h3>
          <p className="text-sm text-gray-500">{repository.path}</p>
          {repository.policy_pack && <p className="text-xs text-gray-400">pack: {repository.policy_pack}</p>}
        </div>
        <button
          className="rounded bg-blue-600 px-3 py-1 text-white hover:bg-blue-700 disabled:opacity-50"
          disabled={trigger.isPending}
          onClick={() => trigger.mutate()}
        >
          {trigger.isPending ? "Scanning…" : "Scan"}
        </button>
      </header>

      {trigger.isError && <p className="mt-2 text-sm text-red-600">Trigger failed — is the admin token set?</p>}

      <ScanHistoryList scans={scans} />
      {latest?.status === "succeeded" && (
        <ExportButtons scanId={latest.scan_id} />
      )}
      <FindingsList
        scanId={latest?.scan_id ?? null}
        state={latestFindings}
      />
    </section>
  );
}

function ScanHistoryList({ scans }: { scans: ScanSummary[] }) {
  const recent = scans.slice(0, 5);
  if (scans.length === 0) {
    return <p className="mt-2 text-sm text-gray-500">No scans yet.</p>;
  }
  return (
    <ul className="mt-3 space-y-1 text-sm">
      {recent.map((scan) => (
        <li key={scan.scan_id} className="flex items-center gap-3">
          <StatusBadge status={scan.status} />
          <span className="text-gray-500">{new Date(scan.created_at).toLocaleString()}</span>
          {scan.result_fingerprint && (
            <code className="text-xs text-gray-400">{scan.result_fingerprint.slice(0, 12)}</code>
          )}
        </li>
      ))}
      {scans.length > recent.length && (
        <li className="text-xs text-gray-400">{scans.length - recent.length} older scan(s) in history</li>
      )}
    </ul>
  );
}

function StatusBadge({ status }: { status: string }) {
  const color =
    status === "succeeded"
      ? "bg-green-100 text-green-800"
      : status === "failed" || status === "cancelled"
        ? "bg-red-100 text-red-800"
        : "bg-amber-100 text-amber-800";
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${color}`}>{status}</span>;
}

function ExportButtons({ scanId }: { scanId: string }) {
  return (
    <div className="mt-2 flex gap-2 text-sm">
      {(["sarif", "html", "json"] as const).map((format) => (
        <a
          key={format}
          className="rounded border border-gray-300 px-2 py-1 hover:bg-gray-50"
          href={exportUrl(scanId, format)}
          download={`conformdag-report.${format}`}
        >
          Export {format.toUpperCase()}
        </a>
      ))}
    </div>
  );
}

interface FindingsState {
  data?: Finding[];
  isLoading: boolean;
  isError: boolean;
}

function FindingsList({ scanId, state }: { scanId: string | null; state: FindingsState }) {
  const [prefill, setPrefill] = useState<Finding | null>(null);
  if (scanId === null || state.isLoading) {
    return null;
  }
  const rows = state.data ?? [];
  return (
    <div className="mt-3">
      <h4 className="text-sm font-medium">Failing findings ({rows.length})</h4>
      {rows.length === 0 && <p className="text-sm text-green-700">No failing findings.</p>}
      <ul className="mt-1 space-y-1 text-sm">
        {rows.map((finding) => (
          <li key={finding.fingerprint} className="flex items-start justify-between gap-2">
            <div>
              <span className="font-mono text-xs">{finding.policy_id}</span>{" "}
              <span className="text-gray-700">
                {finding.file_path}
                {finding.start_line ? `:${finding.start_line}` : ""}
              </span>
              <p className="text-gray-500">{finding.explanation}</p>
            </div>
            <button
              className="rounded border border-gray-300 px-2 py-0.5 text-xs hover:bg-gray-50"
              onClick={() => setPrefill(finding)}
            >
              Suppress…
            </button>
          </li>
        ))}
      </ul>
      {prefill && (
        <SuppressionForm
          prefill={prefill}
          onClose={() => setPrefill(null)}
        />
      )}
    </div>
  );
}

function SuppressionForm({ prefill, onClose }: { prefill: Finding; onClose: () => void }) {
  const [reason, setReason] = useState("");
  const [owner, setOwner] = useState("");
  const [expires, setExpires] = useState("2027-01-01T00:00:00Z");
  const create = useMutation({
    mutationFn: () =>
      createSuppression({
        policy_id: prefill.policy_id,
        fingerprint: prefill.fingerprint,
        reason,
        owner,
        expires_at: expires,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["suppressions"] });
      onClose();
    },
  });
  return (
    <form
      className="mt-2 grid gap-2 rounded border border-amber-200 bg-amber-50 p-3 text-sm"
      onSubmit={(event) => {
        event.preventDefault();
        create.mutate();
      }}
    >
      <p>
        Suppress <strong>{prefill.policy_id}</strong> {prefill.file_path}
        {prefill.start_line ? `:${prefill.start_line}` : ""} — requires admin token.
      </p>
      <input className="rounded border px-2 py-1" placeholder="Reason" value={reason} onChange={(e) => setReason(e.target.value)} required />
      <input className="rounded border px-2 py-1" placeholder="Owner" value={owner} onChange={(e) => setOwner(e.target.value)} required />
      <input className="rounded border px-2 py-1" type="datetime-local" value={expires} onChange={(e) => setExpires(e.target.value)} />
      <div className="flex gap-2">
        <button className="rounded bg-amber-600 px-3 py-1 text-white hover:bg-amber-700 disabled:opacity-50" disabled={create.isPending}>
          {create.isPending ? "Creating…" : "Create suppression"}
        </button>
        <button type="button" className="rounded border px-3 py-1" onClick={onClose}>
          Cancel
        </button>
      </div>
      {create.isError && <p className="text-red-600">Creation failed — check the admin token.</p>}
    </form>
  );
}

function SuppressionsPanel() {
  const suppressions = useQuery({
    queryKey: ["suppressions"],
    queryFn: listSuppressions,
    refetchInterval: 15_000,
  });
  const rows = suppressions.data ?? [];

  const editId = useMutation({
    mutationFn: async ({ id, reason }: { id: string; reason: string }) =>
      updateSuppression(id, { reason }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["suppressions"] }),
  });
  const [editing, setEditing] = useState<Suppression | null>(null);
  const [draftReason, setDraftReason] = useState("");

  return (
    <section className="rounded-lg border border-gray-200 p-4">
      <h2 className="text-xl font-semibold">Suppressions</h2>
      <p className="text-sm text-gray-500">
        Operational, audited exceptions owned by the platform. Pack-owned suppressions
        live in git.
      </p>
      {rows.length === 0 && <p className="mt-2 text-sm text-gray-500">No suppressions recorded.</p>}
      <ul className="mt-2 space-y-2 text-sm">
        {rows.map((suppression) => (
          <li key={suppression.id} className="rounded border border-gray-100 p-2">
            <div className="flex items-center justify-between">
              <div>
                <span className="font-mono text-xs">{suppression.policy_id}</span>{" "}
                <code className="text-xs text-gray-400">{suppression.fingerprint.slice(0, 12)}</code>{" "}
                <span className="rounded bg-gray-100 px-2 py-0.5 text-xs">{suppression.source}</span>
              </div>
              <button
                className="rounded border px-2 py-0.5 text-xs hover:bg-gray-50"
                onClick={() => {
                  setEditing(suppression);
                  setDraftReason(suppression.reason);
                }}
              >
                Edit…
              </button>
            </div>
            <p className="text-gray-600">{suppression.reason}</p>
            <p className="text-xs text-gray-400">
              {suppression.owner} · expires {new Date(suppression.expires_at).toLocaleDateString()}
            </p>
          </li>
        ))}
      </ul>
      {editing && (
        <form
          className="mt-2 flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            editId.mutate({ id: editing.id, reason: draftReason });
            setEditing(null);
          }}
        >
          <input
            className="flex-1 rounded border px-2 py-1"
            value={draftReason}
            onChange={(e) => setDraftReason(e.target.value)}
          />
          <button className="rounded bg-blue-600 px-3 py-1 text-white">Save reason</button>
        </form>
      )}
    </section>
  );
}

export default App;
