import { Banner, Button, Card, EmptyState } from "../components/ui";
import { MetricStrip, type MetricItem } from "../components/overview/MetricStrip";
import { RecentScans } from "../components/overview/RecentScans";
import { TrendChart } from "../components/overview/TrendChart";
import { describeApiError, OVERVIEW_DAYS, useOverviewQuery } from "../hooks/usePlatformQueries";
import { usePageTitle } from "../layout/AppShell";

export default function OverviewPage() {
  usePageTitle("Overview");
  const overview = useOverviewQuery();

  if (overview.isPending) {
    return (
      <p role="status" className="text-sm text-muted">
        Loading overview…
      </p>
    );
  }

  if (overview.isError) {
    return (
      <Banner
        variant="error"
        title="The overview could not be loaded"
        action={
          <Button variant="secondary" size="sm" onClick={() => overview.refetch()}>
            Retry
          </Button>
        }
      >
        <p>{describeApiError(overview.error)}</p>
      </Banner>
    );
  }

  const data = overview.data;
  const metrics: MetricItem[] = [
    { label: "Repositories", value: data.repository_count },
    { label: "Completed scans", value: data.completed_scan_count },
    {
      label: "Active scans",
      value: data.active_scan_count,
      tone: data.active_scan_count > 0 ? "accent" : "neutral",
    },
    {
      label: "Current failures",
      value: data.current_failure_count,
      tone: data.current_failure_count > 0 ? "fail" : "neutral",
    },
    {
      label: "Current errors",
      value: data.current_error_count,
      tone: data.current_error_count > 0 ? "error" : "neutral",
    },
    { label: "New findings", value: data.current_new_finding_count },
  ];

  return (
    <div className="grid gap-5">
      <div data-tour="overview-signal">
        <MetricStrip metrics={metrics} />
      </div>
      <Card
        title={`Trends (last ${OVERVIEW_DAYS} days)`}
        subtitle="Daily fail and error finding counts from completed scans. Dates without completed scans are omitted."
      >
        {data.trends.length === 0 ? (
          <EmptyState
            title="No trend data yet"
            description="Trend points appear once scans complete."
          />
        ) : (
          <TrendChart points={data.trends} />
        )}
      </Card>
      <Card title="Recent scans" subtitle="Active and recently finished scans across repositories.">
        <RecentScans scans={data.recent_scans} />
      </Card>
    </div>
  );
}
