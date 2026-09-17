import { QueryClient, QueryClientProvider, useMutation, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import {
  adminToken,
  createSuppression,
  deletePolicy,
  findings,
  listPackPolicies,
  listPacks,
  listRepositories,
  listSuppressions,
  scanHistory,
  setAdminToken,
  triggerScan,
  updatePolicy,
  updateSuppression,
  validatePack,
  type Finding,
  type PackSummary,
  type Page,
  type PolicyInfo,
  type Repository,
  type ScanSummary,
} from "./api";

const queryClient = new QueryClient();

type PageName = "repos" | "policies" | "suppressions";

function App() {
  const [page, setPage] = useState<PageName>("repos");
  const [token, setToken] = useState(adminToken() ?? "");
  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-gray-950 text-gray-100">
        <header className="border-b border-gray-800 px-6 py-3">
          <div className="mx-auto flex max-w-6xl items-center justify-between">
            <h1 className="text-lg font-semibold text-gray-100">ConformDAG Platform</h1>
            <nav className="flex items-center gap-1">
              {(["repos", "policies", "suppressions"] as PageName[]).map((item) => (
                <button
                  key={item}
                  className={`rounded px-3 py-1.5 text-sm capitalize ${
                    page === item
                      ? "bg-blue-600 text-white"
                      : "text-gray-400 hover:bg-gray-800 hover:text-gray-200"
                  }`}
                  onClick={() => setPage(item)}
                >
                  {item}
                </button>
              ))}
            </nav>
            <TokenInput token={token} onSet={(next) => { setAdminToken(next); setToken(next); }} />
          </div>
        </header>
        <main className="mx-auto max-w-6xl p-6">
          {page === "repos" && <RepositoriesPage />}
          {page === "policies" && <PoliciesPage />}
          {page === "suppressions" && <SuppressionsPage />}
        </main>
      </div>
    </QueryClientProvider>
  );
}

function TokenInput({ token, onSet }: { token: string; onSet: (token: string) => void }) {
  if (token) {
    return (
      <span className="text-xs text-gray-500">
        admin authenticated
        <button className="ml-2 text-blue-400 hover:underline" onClick={() => onSet("")}>
          clear
        </button>
      </span>
    );
  }
  return (
    <form
      onSubmit={(e: FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        const input = e.currentTarget.elements.namedItem("admin-token") as HTMLInputElement;
        onSet(input.value);
      }}
      className="flex items-center gap-2"
    >
      <input
        className="w-48 rounded border border-gray-700 bg-gray-900 px-2 py-1 text-sm text-gray-200 placeholder-gray-500"
        type="password"
        name="admin-token"
        placeholder="Admin token…"
      />
      <button className="rounded bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-700">
        Save
      </button>
    </form>
  );
}

/* ─── Repositories ──────────────────────────────────────────────── */

function RepositoriesPage() {
  const repositories = useQuery({ queryKey: ["repos"], queryFn: listRepositories });
  return (
    <div className="grid gap-4">
      {(repositories.data ?? []).map((repository: Repository) => (
        <RepositoryCard key={repository.id} repository={repository} />
      ))}
      {repositories.isPending && <LoadingBanner text="Loading packs…" />}
      {repositories.isError && <ErrorBanner message="Failed to load repositories." />}
    </div>
  );
}

function RepositoryCard({ repository }: { repository: Repository }) {
  const history = useQuery({
    queryKey: ["scans", repository.id],
    queryFn: () => scanHistory(repository.id),
    refetchInterval: (query) => {
      const scans = query.state.data?.items ?? [];
      return scans.some((s) => s.status === "queued" || s.status === "running") ? 2000 : false;
    },
  });
  const latest = history.data?.items[0];
  const latestFindings = useQuery({
    queryKey: ["findings", latest?.scan_id],
    queryFn: () =>
      latest ? findings(latest.scan_id, { status: "fail" }) : Promise.resolve({ items: [], total: 0 }),
    enabled: latest?.status === "succeeded",
  });
  const trigger = useMutation({
    mutationFn: () => triggerScan(repository.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scans", repository.id] }),
  });

  return (
    <section className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="font-medium text-gray-100">{repository.name}</h2>
          <p className="text-sm text-gray-500">{repository.path}</p>
        </div>
        <button
          className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
          disabled={trigger.isPending}
          onClick={() => trigger.mutate()}
        >
          {trigger.isPending ? "Scanning…" : "Scan"}
        </button>
      </header>

      {trigger.isError && <ErrorBanner message="Trigger failed — check the admin token." />}
      {latest && (
        <p className="mt-2 text-sm text-gray-400">
          Latest scan: <strong className="text-gray-200">{latest.status}</strong>
          {latest.result_fingerprint && (
            <code className="ml-2 text-xs text-gray-600">
              {latest.result_fingerprint.slice(0, 12)}
            </code>
          )}
        </p>
      )}
      <ScanHistoryList scans={history.data?.items ?? []} />
      {latest?.status === "succeeded" && <ExportButtons scanId={latest.scan_id} />}
      <FindingsList scanId={latest?.scan_id ?? null} state={latestFindings} />
    </section>
  );
}

function ScanHistoryList({ scans }: { scans: ScanSummary[] }) {
  if (scans.length === 0) {
    return <p className="mt-2 text-sm text-gray-600">No scans yet.</p>;
  }
  const recent = scans.slice(0, 5);
  return (
    <div className="mt-3 space-y-1 text-sm">
      {recent.map((scan) => (
        <div key={scan.scan_id} className="flex items-center gap-3">
          <StatusBadge status={scan.status} />
          <span className="text-gray-500">{new Date(scan.created_at).toLocaleString()}</span>
          {scan.result_fingerprint && (
            <code className="text-xs text-gray-600">{scan.result_fingerprint.slice(0, 12)}</code>
          )}
        </div>
      ))}
      {scans.length > recent.length && (
        <p className="text-xs text-gray-600">{scans.length - recent.length} older scan(s) in history</p>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const color =
    status === "succeeded"
      ? "bg-green-900 text-green-300"
      : status === "failed" || status === "cancelled"
        ? "bg-red-900 text-red-300"
        : "bg-amber-900 text-amber-300";
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${color}`}>{status}</span>;
}

function ExportButtons({ scanId }: { scanId: string }) {
  return (
    <div className="mt-2 flex gap-2 text-sm">
      {(["sarif", "html", "json"] as const).map((format) => (
        <a
          key={format}
          className="rounded border border-gray-700 px-2 py-1 text-xs text-gray-300 hover:bg-gray-800"
          href={`/api/v1/scans/${scanId}/export/${format}`}
          download={`conformdag-report.${format}`}
        >
          {format.toUpperCase()}
        </a>
      ))}
    </div>
  );
}

interface FindingsState {
  data?: Page<Finding>;
  isLoading: boolean;
  isError: boolean;
}

function FindingsList({ scanId, state }: { scanId: string | null; state: FindingsState }) {
  const [prefill, setPrefill] = useState<Finding | null>(null);
  if (scanId === null || state.isLoading) {
    return null;
  }
  const rows = state.data?.items ?? [];
  return (
    <div className="mt-3">
      <h4 className="text-sm font-medium text-gray-300">Failing findings ({rows.length})</h4>
      {rows.length === 0 && <p className="text-sm text-green-500">No failing findings.</p>}
      <ul className="mt-1 space-y-1 text-sm">
        {rows.map((finding) => (
          <li key={finding.fingerprint} className="flex items-start justify-between gap-2">
            <div>
              <span className="font-mono text-xs text-gray-500">{finding.policy_id}</span>{" "}
              <span className="text-gray-300">
                {finding.file_path}
                {finding.start_line ? `:${finding.start_line}` : ""}
              </span>
              <p className="text-gray-500">{finding.explanation}</p>
            </div>
            <button
              className="shrink-0 rounded border border-gray-700 px-2 py-0.5 text-xs text-gray-300 hover:bg-gray-800"
              onClick={() => setPrefill(finding)}
            >
              Suppress…
            </button>
          </li>
        ))}
      </ul>
      {prefill && <SuppressionForm prefill={prefill} onClose={() => setPrefill(null)} />}
    </div>
  );
}

function SuppressionForm({ prefill, onClose }: { prefill: Finding; onClose: () => void }) {
  const [reason, setReason] = useState("");
  const [owner, setOwner] = useState("");
  const [expires, setExpires] = useState("2027-01-01");
  const create = useMutation({
    mutationFn: () =>
      createSuppression({
        policy_id: prefill.policy_id,
        fingerprint: prefill.fingerprint,
        reason,
        owner,
        expires_at: `${expires}T00:00:00Z`,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["suppressions"] });
      onClose();
    },
  });
  return (
    <form
      className="mt-2 grid gap-2 rounded border border-amber-800 bg-amber-950 p-3 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate();
      }}
    >
      <p className="text-amber-300">
        Suppress <strong>{prefill.policy_id}</strong> {prefill.file_path}
        {prefill.start_line ? `:${prefill.start_line}` : ""}
      </p>
      <input className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200" placeholder="Reason" value={reason} onChange={(e) => setReason(e.target.value)} required />
      <input className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200" placeholder="Owner" value={owner} onChange={(e) => setOwner(e.target.value)} required />
      <input className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200" type="date" value={expires} onChange={(e) => setExpires(e.target.value)} />
      <div className="flex gap-2">
        <button className="rounded bg-amber-600 px-3 py-1 text-white hover:bg-amber-700 disabled:opacity-50" disabled={create.isPending}>
          {create.isPending ? "Creating…" : "Create"}
        </button>
        <button type="button" className="rounded border border-gray-700 px-3 py-1 text-gray-300" onClick={onClose}>
          Cancel
        </button>
      </div>
      {create.isError && <p className="text-red-400">Creation failed — check the admin token.</p>}
    </form>
  );
}

/* ─── Policies ─────────────────────────────────────────────────── */

function PoliciesPage() {
  const packs = useQuery({ queryKey: ["packs"], queryFn: listPacks });

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-gray-100">Policy Packs</h2>
      {(packs.data ?? []).map((pack: PackSummary) => (
        <PackEditor key={pack.name} pack={pack} />
      ))}
      {packs.isPending && <LoadingBanner text="Loading packs…" />}
      {packs.isError && <ErrorBanner message="Failed to load packs." />}
    </div>
  );
}

function PackEditor({ pack }: { pack: PackSummary }) {
  const [expanded, setExpanded] = useState(false);
  const policies = useQuery({
    queryKey: ["policies", pack.name],
    queryFn: () => listPackPolicies(pack.name),
    enabled: expanded,
  });
  const validation = useMutation({
    mutationFn: () => validatePack(pack.name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["policies", pack.name] }),
  });

  return (
    <section className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      <header className="flex items-center justify-between">
        <div>
          <h3 className="font-medium text-gray-100">{pack.name}</h3>
          <p className="text-sm text-gray-500">
            {pack.version ?? "?"} · {pack.policy_count} policies · {pack.path}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            className="rounded border border-gray-700 px-2 py-1 text-xs text-gray-300 hover:bg-gray-800"
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? "Collapse" : "Manage"}
          </button>
          <button
            className="rounded border border-gray-700 px-2 py-1 text-xs text-gray-300 hover:bg-gray-800"
            onClick={() => validation.mutate()}
          >
            Validate
          </button>
        </div>
      </header>
      {pack.error && <ErrorBanner message={pack.error} />}
      {validation.isSuccess && (
        <p className={`mt-2 text-sm ${validation.data.valid ? "text-green-500" : "text-red-500"}`}>
          {validation.data.valid ? "✓ Pack is valid" : `✗ ${validation.data.errors.join("; ")}`}
        </p>
      )}
      {expanded && (
        <div className="mt-3">
          {(policies.data ?? []).map((policy: PolicyInfo) => (
            <PolicyEditor key={policy.id} packName={pack.name} policy={policy} />
          ))}
          {policies.isPending && <LoadingBanner text="Loading policies…" />}
        </div>
      )}
    </section>
  );
}

function PolicyEditor({ packName, policy }: { packName: string; policy: PolicyInfo }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(policy);
  const save = useMutation({
    mutationFn: () =>
      updatePolicy(packName, policy.id, {
        title: draft.title,
        version: draft.version,
        status: draft.status,
        severity: draft.severity,
        check_kind: draft.check_kind,
        check_config: draft.check_config,
        source_document: draft.source_document,
        source_section: draft.source_section,
        source_version: draft.source_version,
        invariant: draft.invariant,
        safe_path: draft.safe_path,
        ownership: draft.ownership,
        scope: draft.scope,
        exceptions: draft.exceptions,
        enforcement: draft.enforcement,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["policies", packName] });
      setEditing(false);
    },
  });
  const remove = useMutation({
    mutationFn: () => deletePolicy(packName, policy.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["policies", packName] }),
  });

  if (editing) {
    return (
      <div className="mt-2 rounded border border-blue-800 bg-blue-950 p-3 text-sm">
        <input className="mb-2 w-full rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
        <input className="mb-2 w-full rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200" value={draft.invariant} onChange={(e) => setDraft({ ...draft, invariant: e.target.value })} placeholder="Invariant" />
        <textarea className="mb-2 w-full rounded border border-gray-700 bg-gray-900 px-2 py-1 font-mono text-xs text-gray-200" rows={3} value={JSON.stringify(draft.check_config, null, 2)} onChange={(e) => { try { setDraft({ ...draft, check_config: JSON.parse(e.target.value) }); } catch { /* keep raw while editing */ } }} />
        <div className="flex gap-2">
          <button className="rounded bg-blue-600 px-3 py-1 text-white disabled:opacity-50" disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? "Saving…" : "Save"}
          </button>
          <button type="button" className="rounded border border-gray-700 px-3 py-1 text-gray-300" onClick={() => setEditing(false)}>
            Cancel
          </button>
        </div>
        {save.isError && <p className="text-red-500">Save failed — check the admin token and pack path.</p>}
      </div>
    );
  }
  return (
    <div className="flex items-center justify-between rounded border border-gray-800 p-2 text-sm">
      <div>
        <span className="font-mono text-xs text-gray-500">{policy.id}</span>{" "}
        <span className="text-gray-300">{policy.title}</span>
        <span className="ml-2 rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-400">{policy.check_kind}</span>
        <p className="text-xs text-gray-600">{policy.source_document} · {policy.version}</p>
      </div>
      <div className="flex gap-1">
        <button className="rounded border border-gray-700 px-2 py-0.5 text-xs hover:bg-gray-800" onClick={() => { setDraft(policy); setEditing(true); }}>
          Edit
        </button>
        <button className="rounded border border-red-800 px-2 py-0.5 text-xs text-red-400 hover:bg-red-900" onClick={() => remove.mutate()}>
          Delete
        </button>
      </div>
    </div>
  );
}

/* ─── Suppressions ─────────────────────────────────────────────── */

function SuppressionsPage() {
  const suppressions = useQuery({
    queryKey: ["suppressions"],
    queryFn: listSuppressions,
    refetchInterval: 15_000,
  });
  const rows = suppressions.data ?? [];
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftReason, setDraftReason] = useState("");
  const edit = useMutation({
    mutationFn: (input: { id: string; reason: string }) => updateSuppression(input.id, { reason: input.reason }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["suppressions"] }),
  });

  return (
    <section>
      <h2 className="mb-2 text-lg font-semibold text-gray-100">Suppressions</h2>
      <p className="mb-4 text-sm text-gray-500">
        Operational, audited exceptions. Pack-owned suppressions live in git.
      </p>
      {rows.length === 0 && <p className="text-sm text-gray-600">No suppressions recorded.</p>}
      <div className="space-y-2">
        {rows.map((suppression) => (
          <div key={suppression.id} className="rounded border border-gray-800 bg-gray-900 p-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs text-gray-500">{suppression.policy_id}</span>
              <span className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-400">{suppression.source}</span>
              <button
                className="rounded border border-gray-700 px-2 py-0.5 text-xs hover:bg-gray-800"
                onClick={() => { setEditingId(suppression.id); setDraftReason(suppression.reason); }}
              >
                Edit
              </button>
            </div>
            <p className="mt-1 text-gray-300">{suppression.reason}</p>
            <p className="text-xs text-gray-600">
              {suppression.owner} · expires {new Date(suppression.expires_at).toLocaleDateString()}
            </p>
            {editingId === suppression.id && (
              <form
                className="mt-2 flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  edit.mutate({ id: suppression.id, reason: draftReason });
                  setEditingId(null);
                }}
              >
                <input className="flex-1 rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200" value={draftReason} onChange={(e) => setDraftReason(e.target.value)} />
                <button className="rounded bg-blue-600 px-3 py-1 text-white">Save</button>
              </form>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

/* ─── Shared UI components ──────────────────────────────────────── */

function LoadingBanner({ text }: { text: string }) {
  return <p className="animate-pulse text-sm text-gray-500">{text}</p>;
}

function ErrorBanner({ message }: { message: string }) {
  return <p className="rounded border border-red-800 bg-red-950 p-3 text-sm text-red-400">{message}</p>;
}

export default App;
