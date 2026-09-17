/**
 * Route table contract: the five canonical console paths map to their page
 * modules, deep links render a matched page inside the shell, and unknown
 * paths get a not-found view that links back to `/`.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { isValidElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, type RouteObject } from "react-router-dom";

import { ThemeProvider } from "./layout/ThemeProvider";
import OverviewPage from "./pages/OverviewPage";
import PoliciesPage from "./pages/PoliciesPage";
import RepositoryPage from "./pages/RepositoryPage";
import ScanPage from "./pages/ScanPage";
import SuppressionsPage from "./pages/SuppressionsPage";
import { AppRoutes, appRoutes } from "./routes";

function stubMatchMedia(): void {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  })) as unknown as typeof window.matchMedia;
}

function shellChildren(): RouteObject[] {
  const layout = appRoutes[0];
  if (layout === undefined) {
    throw new Error("route table must have a shell layout route");
  }
  return layout.children ?? [];
}

function routeElementType(route: RouteObject | undefined): unknown {
  return route !== undefined && isValidElement(route.element) ? route.element.type : null;
}

function renderAt(path: string): void {
  render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

afterEach(cleanup);

describe("route table", () => {
  beforeEach(() => {
    stubMatchMedia();
  });

  it("maps / to OverviewPage", () => {
    const route = shellChildren().find((candidate) => candidate.index === true);
    expect(route?.path).toBeUndefined();
    expect(routeElementType(route)).toBe(OverviewPage);
  });

  it("maps /repos/:repositoryId to RepositoryPage", () => {
    const route = shellChildren().find((candidate) => candidate.path === "repos/:repositoryId");
    expect(routeElementType(route)).toBe(RepositoryPage);
  });

  it("maps /scans/:scanId to ScanPage", () => {
    const route = shellChildren().find((candidate) => candidate.path === "scans/:scanId");
    expect(routeElementType(route)).toBe(ScanPage);
  });

  it("maps /policies to PoliciesPage", () => {
    const route = shellChildren().find((candidate) => candidate.path === "policies");
    expect(routeElementType(route)).toBe(PoliciesPage);
  });

  it("maps /suppressions to SuppressionsPage", () => {
    const route = shellChildren().find((candidate) => candidate.path === "suppressions");
    expect(routeElementType(route)).toBe(SuppressionsPage);
  });

  it("keeps a catch-all route after the five canonical paths", () => {
    const last = shellChildren()[shellChildren().length - 1];
    expect(last?.path).toBe("*");
  });

  it("renders the shell around the overview page at /", () => {
    renderAt("/");
    expect(screen.getByRole("banner")).toHaveTextContent("ConformDAG Platform");
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  it.each(["/repos/repo-1", "/scans/scan-1", "/policies", "/suppressions"])(
    "renders a matched page for deep link %s",
    (path) => {
      renderAt(path);
      expect(screen.getByRole("main")).toBeInTheDocument();
      expect(screen.queryByRole("link", { name: "Back to overview" })).not.toBeInTheDocument();
    },
  );

  it("renders a not-found view linking back to /", () => {
    renderAt("/definitely-not-a-page");
    expect(screen.getByText("Page not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to overview" })).toHaveAttribute("href", "/");
  });
});
