import { EmptyState } from "../components/ui";
import { usePageTitle } from "../layout/AppShell";

export default function ScanPage() {
  usePageTitle("Scan detail");
  return (
    <EmptyState
      title="Scan detail"
      description="Findings, gate results, and export options will appear here."
    />
  );
}
