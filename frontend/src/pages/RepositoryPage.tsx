import { EmptyState } from "../components/ui";
import { usePageTitle } from "../layout/AppShell";

export default function RepositoryPage() {
  usePageTitle("Repository");
  return (
    <EmptyState
      title="Repository"
      description="Repository detail, scan history, and baseline controls will appear here."
    />
  );
}
