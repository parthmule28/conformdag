import { QueryClient, QueryClientProvider, useMutation, useQuery } from "@tanstack/react-query";

import { findings, listRepositories, scanHistory, triggerScan, type Finding } from "./api";

const queryClient = new QueryClient();

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <main className="mx-auto max-w-5xl p-8">
        <h1 className="mb-6 text-2xl font-semibold">ConformDAG Platform</h1>
        <RepositoryList />
      </main>
    </QueryClientProvider>
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
      {(repositories.data ?? []).map((repository) => (
        <RepositoryCard key={repository.id} repository={repository} />
      ))}
    </div>
  );
}

interface RepositoryRow {
  id: string;
  name: string;
  path: string;
}

function RepositoryCard({ repository }: { repository: RepositoryRow }) {
  const history = useQuery({
    queryKey: ["scans", repository.id],
    queryFn: () => scanHistory(repository.id),
    refetchInterval: (query) => {
      const statuses = query.state.data?.map((scan) => scan.status) ?? [];
      const active = statuses.some((status) => status === "queued" || status === "running");
      return active ? 2000 : false;
    },
  });
  const latest = history.data?.[0];
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
          <h2 className="font-medium">{repository.name}</h2>
          <p className="text-sm text-gray-500">{repository.path}</p>
        </div>
        <button
          className="rounded bg-blue-600 px-3 py-1 text-white hover:bg-blue-700"
          onClick={() => trigger.mutate()}
        >
          {trigger.isPending ? "Scanning…" : "Scan"}
        </button>
      </header>
      {latest && (
        <p className="mt-2 text-sm">
          Latest scan: <strong>{latest.status}</strong>
          {latest.result_fingerprint && (
            <span className="ml-2 text-gray-400">{latest.result_fingerprint.slice(0, 12)}</span>
          )}
        </p>
      )}
      {latestFindings.data && latestFindings.data.length > 0 && (
        <ul className="mt-2 space-y-1 text-sm">
          {latestFindings.data.map((finding: Finding) => (
            <li key={finding.fingerprint} className="text-red-700">
              {finding.policy_id} {finding.file_path}
              {finding.start_line ? `:${finding.start_line}` : ""} — {finding.explanation}
            </li>
          ))}
        </ul>
      )}
      {latest?.status === "succeeded" && latestFindings.data?.length === 0 && (
        <p className="mt-2 text-sm text-green-700">No failing findings.</p>
      )}
    </section>
  );
}

export default App;
