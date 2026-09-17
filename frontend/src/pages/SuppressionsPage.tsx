import { EmptyState } from "../components/ui";
import { usePageTitle } from "../layout/AppShell";

export default function SuppressionsPage() {
  usePageTitle("Suppressions");
  return (
    <EmptyState
      title="Suppressions"
      description="Operational suppressions and their audit details will appear here."
    />
  );
}
