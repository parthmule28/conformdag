import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError, exportUrl, type Finding } from "../api";
import { FindingDetailPanel } from "../components/findings/FindingDetailPanel";
import { FindingsTable } from "../components/findings/FindingsTable";
import { FindingsToolbar } from "../components/findings/FindingsToolbar";
import { GateResultPanel } from "../components/scans/GateResultPanel";
import { IssueList } from "../components/scans/IssueList";
import { RuntimeObservations } from "../components/scans/RuntimeObservations";
import { ScanHeader } from "../components/scans/ScanHeader";
import { Banner, Button, Card, EmptyState, Modal, Pagination } from "../components/ui";
import {
  describeApiError,
  EMPTY_FINDINGS_FILTERS,
  FINDINGS_PAGE_SIZE,
  findingsQueryParams,
  isActiveScan,
  useCancelScanMutation,
  useScanFindingsQuery,
  useScanReportQuery,
  useScanStatusQuery,
  type FindingsFilterState,
} from "../hooks/usePlatformQueries";
import { usePageTitle } from "../layout/AppShell";

const EXPORT_FORMATS = ["json", "sarif", "html"] as const;

function ExportLink({ scanId, format }: { scanId: string; format: "json" | "sarif" | "html" }) {
  return (
    <a className="text-accent hover:underline" href={exportUrl(scanId, format)}>
      {format.toUpperCase()}
    </a>
  );
}

export default function ScanPage() {
  const { scanId = "" } = useParams();
  const [filters, setFilters] = useState<FindingsFilterState>(EMPTY_FINDINGS_FILTERS);
  const [pageSize, setPageSize] = useState(FINDINGS_PAGE_SIZE);
  const [pageIndex, setPageIndex] = useState(0);
  const [actionError, setActionError] = useState<string | null>(null);
  const [inspected, setInspected] = useState<Finding | null>(null);

  const statusQuery = useScanStatusQuery(scanId);
  const scan = statusQuery.data ?? null;
  const scanActive = scan !== null && isActiveScan(scan.status);
  // The report artifact exists only after a terminal state, so the query stays
  // disabled (and never 404s spuriously) until the status has loaded.
  const reportQuery = useScanReportQuery(scanId, scan !== null && !scanActive);
  const findingsParams = findingsQueryParams(filters, pageSize, pageIndex * pageSize);
  const findingsQuery = useScanFindingsQuery(scanId, findingsParams);
  const cancel = useCancelScanMutation();

  usePageTitle(scanId === "" ? "Scan detail" : `Scan ${scanId}`);

  useEffect(() => {
    setFilters(EMPTY_FINDINGS_FILTERS);
    setPageSize(FINDINGS_PAGE_SIZE);
    setPageIndex(0);
    setActionError(null);
    setInspected(null);
  }, [scanId]);

  if (statusQuery.isPending) {
    return (
      <p role="status" className="text-sm text-muted">
        Loading scan…
      </p>
    );
  }

  if (statusQuery.isError) {
    if (statusQuery.error instanceof ApiError && statusQuery.error.status === 404) {
      return (
        <EmptyState
          title="Scan not found"
          description="No scan matches this address. It may have been removed or never registered."
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
      <Banner
        variant="error"
        title="Scan status could not be loaded"
        action={
          <Button variant="secondary" size="sm" onClick={() => statusQuery.refetch()}>
            Retry
          </Button>
        }
      >
        <p>{describeApiError(statusQuery.error)}</p>
      </Banner>
    );
  }

  if (scan === null) {
    return null;
  }

  const reportError = reportQuery.error;
  const artifactUnavailable =
    reportQuery.isError && reportError instanceof ApiError && reportError.status === 404;
  const reportAvailable = reportQuery.isSuccess;

  const updateFilters = (patch: Partial<FindingsFilterState>) => {
    setFilters((previous) => ({ ...previous, ...patch }));
    setPageIndex(0);
  };

  const changePageSize = (nextPageSize: number) => {
    setPageSize(Number.isNaN(nextPageSize) ? FINDINGS_PAGE_SIZE : nextPageSize);
    setPageIndex(0);
  };

  const handleCancel = () => {
    setActionError(null);
    cancel.mutate(scanId, {
      onError: (error) => setActionError(describeApiError(error)),
    });
  };

  const inspectedReportFinding =
    inspected === null
      ? null
      : (reportQuery.data?.findings.find((candidate) => candidate.fingerprint === inspected.fingerprint) ??
        null);

  return (
    <div className="grid gap-5">
      {actionError !== null && (
        <Banner variant="error" title="The action did not complete" onDismiss={() => setActionError(null)}>
          <p>{actionError}</p>
        </Banner>
      )}
      {scanActive && (
        <Banner variant="info" title={`This scan is ${scan.status}.`}>
          <p>The status refreshes automatically while the scan runs.</p>
        </Banner>
      )}
      <Card
        title={`Scan ${scanId}`}
        subtitle="Run summary and export actions"
        actions={
          reportAvailable ? (
            <span className="flex flex-wrap gap-x-2 gap-y-1">
              {EXPORT_FORMATS.map((format) => (
                <ExportLink key={format} scanId={scanId} format={format} />
              ))}
            </span>
          ) : undefined
        }
      >
        <ScanHeader
          scanId={scanId}
          status={scan}
          onCancel={handleCancel}
          cancelPending={cancel.isPending}
        />
      </Card>
      <Card title="Quality gate" subtitle="The recorded verdict from the canonical report artifact.">
        {reportQuery.isError && !artifactUnavailable && (
          <div className="mb-3">
            <Banner
              variant="error"
              title="The report artifact could not be loaded"
              action={
                <Button variant="secondary" size="sm" onClick={() => reportQuery.refetch()}>
                  Retry
                </Button>
              }
            >
              <p>{describeApiError(reportError)}</p>
            </Banner>
          </div>
        )}
        <GateResultPanel
          gateResult={reportQuery.data?.gate_result ?? null}
          reportComplete={reportQuery.data?.complete ?? null}
          artifactUnavailable={artifactUnavailable}
          scanActive={scanActive}
        />
      </Card>
      {reportAvailable && (
        <>
          <Card title="Run issues" subtitle="Parse and evaluation issues retained with the report.">
            <IssueList issues={reportQuery.data?.issues ?? []} />
          </Card>
          <Card title="Runtime observations" subtitle="Runtime facts retained with the report.">
            <RuntimeObservations observations={reportQuery.data?.runtime_observations ?? []} />
          </Card>
        </>
      )}
      <Card title="Findings" subtitle="Filters and pagination are applied by the server.">
        <div className="grid gap-3">
          <FindingsToolbar
            filters={filters}
            pageSize={pageSize}
            onChange={updateFilters}
            onPageSizeChange={changePageSize}
          />
          {findingsQuery.isPending ? (
            <p role="status" className="text-sm text-muted">
              Loading findings…
            </p>
          ) : findingsQuery.isError ? (
            <Banner
              variant="error"
              title="Findings could not be loaded"
              action={
                <Button variant="secondary" size="sm" onClick={() => findingsQuery.refetch()}>
                  Retry
                </Button>
              }
            >
              <p>{describeApiError(findingsQuery.error)}</p>
            </Banner>
          ) : (
            <>
              <FindingsTable
                findings={findingsQuery.data.items}
                emptyMessage={
                  scanActive ? "Findings appear when the scan finishes." : undefined
                }
                onInspect={setInspected}
              />
              <Pagination
                page={pageIndex + 1}
                pageSize={pageSize}
                total={findingsQuery.data.total}
                onPageChange={(nextPage) => setPageIndex(nextPage - 1)}
              />
            </>
          )}
        </div>
      </Card>
      <Modal
        open={inspected !== null}
        onClose={() => setInspected(null)}
        title={inspected === null ? "Finding" : `Finding ${inspected.policy_id}`}
      >
        {inspected !== null && (
          <FindingDetailPanel
            finding={inspected}
            reportFinding={inspectedReportFinding}
            artifactUnavailable={artifactUnavailable}
          />
        )}
      </Modal>
    </div>
  );
}
