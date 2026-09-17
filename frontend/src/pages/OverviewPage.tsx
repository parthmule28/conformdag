import { EmptyState } from "../components/ui";
import { usePageTitle } from "../layout/AppShell";

export default function OverviewPage() {
  usePageTitle("Overview");
  return (
    <EmptyState
      title="Overview"
      description="Platform metrics, trends, and recent scans will appear here."
    />
  );
}
