/**
 * Routed application shell: product mark, desktop and mobile navigation,
 * admin-token control, theme toggle, page title slot, main content region,
 * and a global error boundary/banner slot. Navigation is URL-based only.
 */
import {
  Component,
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { Link, NavLink, Outlet } from "react-router-dom";

import { adminToken, setAdminToken } from "../api";
import { Banner, Button, Input, ThemeToggle, cx } from "../components/ui";

const NAV_ITEMS: Array<{ to: string; label: string }> = [
  { to: "/", label: "Overview" },
  { to: "/policies", label: "Policies" },
  { to: "/suppressions", label: "Suppressions" },
];

const PageTitleContext = createContext<(title: string) => void>(() => undefined);

export function usePageTitle(title: string): void {
  const setPageTitle = useContext(PageTitleContext);
  useEffect(() => {
    setPageTitle(title);
    document.title = `${title} \u00b7 ConformDAG Platform`;
    return () => {
      setPageTitle("");
      document.title = "ConformDAG Platform";
    };
  }, [setPageTitle, title]);
}

function navLinkClasses({ isActive }: { isActive: boolean }): string {
  return cx(
    "rounded-sm px-2.5 py-1.5 text-sm font-medium transition-colors",
    isActive ? "bg-accent/10 text-accent" : "text-muted hover:bg-sunken hover:text-ink",
  );
}

function BurgerIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
    >
      <path d="M2 4.5h12M2 8h12M2 11.5h12" />
    </svg>
  );
}

function TokenControl() {
  const [savedToken, setSavedToken] = useState<string>(() => adminToken() ?? "");
  const [draft, setDraft] = useState<string>(() => adminToken() ?? "");

  if (savedToken !== "") {
    return (
      <span className="flex items-center gap-1.5 text-xs text-muted">
        Admin token saved
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setAdminToken("");
            setSavedToken("");
            setDraft("");
          }}
        >
          Clear
        </Button>
      </span>
    );
  }

  return (
    <form
      className="flex items-end gap-1.5"
      onSubmit={(event) => {
        event.preventDefault();
        setAdminToken(draft);
        setSavedToken(draft);
      }}
    >
      <Input
        label="Admin token"
        name="admin-token"
        type="password"
        autoComplete="off"
        placeholder="Admin token…"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        className="w-44"
      />
      <Button type="submit" size="sm">
        Save
      </Button>
    </form>
  );
}

interface ShellErrorBoundaryState {
  error: Error | null;
}

class ShellErrorBoundary extends Component<{ children: ReactNode }, ShellErrorBoundaryState> {
  override state: ShellErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ShellErrorBoundaryState {
    return { error };
  }

  override render(): ReactNode {
    const { error } = this.state;
    if (error === null) {
      return this.props.children;
    }
    return (
      <div className="grid gap-3 py-6">
        <Banner
          variant="error"
          title="This page failed to render"
          action={
            <Button variant="secondary" size="sm" onClick={() => this.setState({ error: null })}>
              Try again
            </Button>
          }
        >
          <p>{error.message}</p>
        </Banner>
        <p className="text-sm">
          <Link className="text-accent underline-offset-2 hover:underline" to="/">
            Back to overview
          </Link>
        </p>
      </div>
    );
  }
}

export interface AppShellProps {
  banner?: ReactNode;
}

export function AppShell({ banner }: AppShellProps) {
  const [pageTitle, setPageTitle] = useState("");
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <PageTitleContext.Provider value={setPageTitle}>
      <div className="min-h-screen bg-surface text-ink">
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-sm focus:border focus:border-line focus:bg-raised focus:px-3 focus:py-2 focus:text-sm focus:text-ink"
        >
          Skip to content
        </a>
        <header className="border-b border-line bg-raised">
          <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3 sm:px-6">
            <Link to="/" className="flex shrink-0 items-center gap-2.5">
              <span
                aria-hidden="true"
                className="flex h-8 w-8 items-center justify-center rounded-md bg-accent font-mono text-xs font-bold text-on-accent shadow-sm"
              >
                CD
              </span>
              <span className="text-base font-semibold tracking-tight text-ink">ConformDAG Platform</span>
            </Link>
            <nav aria-label="Primary" className="ml-2 hidden items-center gap-1 md:flex">
              {NAV_ITEMS.map((item) => (
                <NavLink key={item.to} to={item.to} end={true} className={navLinkClasses}>
                  {item.label}
                </NavLink>
              ))}
            </nav>
            <div className="ml-auto flex items-center gap-2">
              <div className="hidden md:block">
                <TokenControl />
              </div>
              <ThemeToggle />
              <button
                type="button"
                className="inline-flex h-8 w-8 items-center justify-center rounded-sm border border-line text-muted transition-colors hover:bg-sunken hover:text-ink md:hidden"
                aria-expanded={mobileOpen}
                aria-controls="mobile-navigation"
                aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
                onClick={() => setMobileOpen((open) => !open)}
              >
                <BurgerIcon />
              </button>
            </div>
          </div>
          {mobileOpen && (
            <nav
              id="mobile-navigation"
              aria-label="Primary mobile"
              className="border-t border-line px-4 py-3 md:hidden"
            >
              <ul className="grid gap-1">
                {NAV_ITEMS.map((item) => (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      end={true}
                      className={navLinkClasses}
                      onClick={() => setMobileOpen(false)}
                    >
                      {item.label}
                    </NavLink>
                  </li>
                ))}
              </ul>
              <div className="mt-3 border-t border-line pt-3">
                <TokenControl />
              </div>
            </nav>
          )}
        </header>
        {banner !== undefined && (
           <div className="mx-auto max-w-7xl px-4 pt-5 sm:px-6">{banner}</div>
        )}
        <div className="mx-auto max-w-7xl px-4 pt-6 sm:px-6">
          {pageTitle !== "" && <h1 className="text-2xl font-semibold tracking-tight text-ink">{pageTitle}</h1>}
        </div>
        <main
          id="main-content"
          tabIndex={-1}
          className="mx-auto max-w-7xl px-4 pb-12 pt-5 focus:outline-none sm:px-6"
        >
          <ShellErrorBoundary>
            <Outlet />
          </ShellErrorBoundary>
        </main>
      </div>
    </PageTitleContext.Provider>
  );
}
