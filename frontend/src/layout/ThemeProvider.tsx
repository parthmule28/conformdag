/**
 * Theme state for the console.
 *
 * Reads `conformdag-theme` from localStorage; with no stored value the UI
 * follows `prefers-color-scheme`. An explicit choice is written back to
 * localStorage and applied as `data-theme` on the document root, which the
 * token stylesheet uses to switch surfaces. While no explicit choice is
 * stored the provider tracks OS scheme changes live and leaves the document
 * root untouched so the CSS media query drives resolution.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "conformdag-theme";

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function storedTheme(): Theme | null {
  const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
  return raw === "light" || raw === "dark" ? raw : null;
}

function systemTheme(): Theme {
  if (typeof window.matchMedia !== "function") {
    return "light";
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyDocumentTheme(theme: Theme | null): void {
  if (theme === null) {
    document.documentElement.removeAttribute("data-theme");
    return;
  }
  document.documentElement.setAttribute("data-theme", theme);
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [override, setOverride] = useState<Theme | null>(() => storedTheme());
  const [system, setSystem] = useState<Theme>(() => systemTheme());

  useEffect(() => {
    if (typeof window.matchMedia !== "function") {
      return undefined;
    }
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (event: MediaQueryListEvent): void => {
      setSystem(event.matches ? "dark" : "light");
    };
    media.addEventListener("change", onChange);
    return () => {
      media.removeEventListener("change", onChange);
    };
  }, []);

  useEffect(() => {
    applyDocumentTheme(override);
  }, [override]);

  const setTheme = useCallback((theme: Theme): void => {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    setOverride(theme);
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({
      theme: override ?? system,
      setTheme,
      toggleTheme: () => setTheme((override ?? system) === "dark" ? "light" : "dark"),
    }),
    [override, system, setTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (context === null) {
    throw new Error("useTheme must be used inside a ThemeProvider");
  }
  return context;
}
