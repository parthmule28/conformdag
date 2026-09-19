/**
 * Route table for the console. The shell is a layout route; the five
 * canonical paths map to their page modules and unknown paths fall through
 * to a not-found view linking back to `/`.
 */
import { Link, useRoutes, type RouteObject } from "react-router-dom";

import { EmptyState } from "./components/ui";
import { AppShell, usePageTitle } from "./layout/AppShell";
import OverviewPage from "./pages/OverviewPage";
import PoliciesPage from "./pages/PoliciesPage";
import RepositoryPage from "./pages/RepositoryPage";
import ScanPage from "./pages/ScanPage";
import SuppressionsPage from "./pages/SuppressionsPage";

export const appRoutes: RouteObject[] = [
  {
    element: <AppShell />,
    children: [
      { index: true, element: <OverviewPage /> },
      { path: "repos/:repositoryId", element: <RepositoryPage /> },
      { path: "scans/:scanId", element: <ScanPage /> },
      { path: "policies", element: <PoliciesPage /> },
      { path: "suppressions", element: <SuppressionsPage /> },
      { path: "*", element: <NotFoundView /> },
    ],
  },
];

export function AppRoutes() {
  return useRoutes(appRoutes);
}

function NotFoundView() {
  usePageTitle("Not found");
  return (
    <div className="mx-auto max-w-md py-12">
      <EmptyState
        title="Page not found"
        description="The address does not match a console page. Check the URL or return to the overview."
        action={
          <Link
            to="/"
            className="inline-flex items-center justify-center gap-1.5 rounded-sm bg-accent px-3 py-1.5 text-sm font-medium text-on-accent transition-colors hover:bg-accent-strong"
          >
            Back to overview
          </Link>
        }
      />
    </div>
  );
}
