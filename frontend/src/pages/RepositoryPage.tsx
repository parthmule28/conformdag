import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Banner, Button, Card, EmptyState, Pagination } from "../components/ui";
import { RepositorySummary } from "../components/repositories/RepositorySummary";
import { ScanHistoryTable } from "../components/repositories/ScanHistoryTable";
import { TrendChart } from "../components/overview/TrendChart";
import {
  describeApiError,
  HISTORY_PAGE_SIZE,
  OVERVIEW_DAYS,
  useCancelScanMutation,
  useRepositoriesQuery,
  useRepositoryTrendsQuery,
  useScanHistoryQuery,
  useSetBaselineMutation,
  useTriggerScanMutation,
} from "../hooks/usePlatformQueries";
import { usePageTitle } from "../layout/AppShell";

export default function RepositoryPage() {
  const { repositoryId = "" } = useParams();
  const [pageIndex, setPageIndex] = useState(0);
  const [actionError, setActionError] = useState<string | null>(null);

  const repositories = useRepositoriesQuery();
  const history = useScanHistoryQuery(repositoryId, HISTORY_PAGE_SIZE, pageIndex * HISTORY_PAGE_SIZE);
  const trends = useRepositoryTrendsQuery(repositoryId);
  const trigger = useTriggerScanMutation();
  const cancel = useCancelScanMutation();
  const setBaseline = useSetBaselineMutation();

  const repository = repositories.data?.find((candidate) => candidate.id === repositoryId) ?? null;

  usePageTitle(repository === null ? "Repository" : repository.name);

  useEffect(() => {
    setPageIndex(0);
    setActionError(null);
  }, [repositoryId]);

  const busyScanId =
    cancel.isPending && cancel.variables !== undefined
      ? cancel.variables
      : setBaseline.isPending && setBaseline.variables !== undefined
        ? setBaseline.variables.scanId
        : null;

  const handleTrigger = () => {
    setActionError(null);
    trigger.mutate(repositoryId, {
      onError: (error) => setActionError(describeApiError(error)),
    });
  };

  const handleCancel = (scanId: string) => {
    setActionError(null);
    cancel.mutate(scanId, {
      onError: (error) => setActionError(describeApiError(error)),
    });
  };

  const handleSetBaseline = (scanId: string) => {
    setActionError(null);
    setBaseline.mutate(
      { repositoryId, scanId },
      { onError: (error) => setActionError(describeApiError(error)) },
    );
  };

  if (repositories.isPending) {
    return (
      <p role="status" className="text-sm text-muted">
        Loading repository…
      </p>
    );
  }

  if (repositories.isError) {
    return (
      <Banner
        variant="error"
        title="Repository data could not be loaded"
        action={
          <Button variant="secondary" size="sm" onClick={() => repositories.refetch()}>
            Retry
          </Button>
        }
      >
        <p>{describeApiError(repositories.error)}</p>
      </Banner>
    );
  }

  if (repository === null) {
    return (
      <EmptyState
        title="Repository not found"
        description="No registered repository matches this address. Check the URL or return to the overview."
        action={
          <Link
            to="/"
            className="inline-flex items-center justify-center gap-1.5 rounded-sm bg-accent px-3 py-1.5 text-sm font-medium text-on-accent transition-colors hover:bg-accent-strong"
          >
            Back to overview
          </Link>
        }
      />
    );
  }

  return (
    <div className="grid gap-5">
      {actionError !== null && (
        <Banner variant="error" title="The action did not complete" onDismiss={() => setActionError(null)}>
          <p>{actionError}</p>
        </Banner>
      )}
      {trigger.isSuccess && (
        <Banner variant="success" title="Scan queued" onDismiss={() => trigger.reset()}>
          <p>The history below refreshes as the scan progresses.</p>
        </Banner>
      )}
      <Card
        title={repository.name}
        subtitle="Configuration and scan controls"
        actions={
          <Button onClick={handleTrigger} loading={trigger.isPending}>
            Trigger scan
          </Button>
        }
      >
        <RepositorySummary repository={repository} />
      </Card>
      <Card title="Scan history" subtitle="Newest first. Exports appear for completed scans.">
        {history.isPending ? (
          <p role="status" className="text-sm text-muted">
            Loading history…
          </p>
        ) : history.isError ? (
          <Banner
            variant="error"
            title="Scan history could not be loaded"
            action={
              <Button variant="secondary" size="sm" onClick={() => history.refetch()}>
                Retry
              </Button>
            }
          >
            <p>{describeApiError(history.error)}</p>
          </Banner>
        ) : (
          <div className="grid gap-3">
            <ScanHistoryTable
              scans={history.data.items}
              baselineScanId={repository.baseline_scan_id}
              busyScanId={busyScanId}
              onSetBaseline={handleSetBaseline}
              onCancel={handleCancel}
            />
            <Pagination
              page={pageIndex + 1}
              pageSize={HISTORY_PAGE_SIZE}
              total={history.data.total}
              onPageChange={(nextPage) => setPageIndex(nextPage - 1)}
            />
          </div>
        )}
      </Card>
      <Card
        title={`Trends (last ${OVERVIEW_DAYS} days)`}
        subtitle="Daily fail and error finding counts from this repository's completed scans."
      >
        {trends.isPending ? (
          <p role="status" className="text-sm text-muted">
            Loading trends…
          </p>
        ) : trends.isError ? (
          <Banner
            variant="error"
            title="Repository trends could not be loaded"
            action={
              <Button variant="secondary" size="sm" onClick={() => trends.refetch()}>
                Retry
              </Button>
            }
          >
            <p>{describeApiError(trends.error)}</p>
          </Banner>
        ) : trends.data.points.length === 0 ? (
          <EmptyState
            title="No trend data yet"
            description="Trend points appear once this repository's scans complete."
          />
        ) : (
          <TrendChart points={trends.data.points} />
        )}
      </Card>
    </div>
  );
}
