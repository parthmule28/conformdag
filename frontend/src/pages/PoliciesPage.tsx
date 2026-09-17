import { EmptyState } from "../components/ui";
import { usePageTitle } from "../layout/AppShell";

export default function PoliciesPage() {
  usePageTitle("Policies");
  return (
    <EmptyState
      title="Policies"
      description="Policy packs, policy editors, and quality gates will appear here."
    />
  );
}
