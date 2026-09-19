/**
 * Theme state behavior: system-preference fallback, explicit localStorage
 * override, and toggle persistence on the `conformdag-theme` key.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ThemeToggle } from "../components/ui/ThemeToggle";
import { THEME_STORAGE_KEY, ThemeProvider } from "./ThemeProvider";

type ChangeListener = (event: MediaQueryListEvent) => void;

let systemDark = false;
let changeListeners: ChangeListener[] = [];

function mockMatchMedia(): void {
  changeListeners = [];
  const mediaQueryList = {
    get matches(): boolean {
      return systemDark;
    },
    media: "(prefers-color-scheme: dark)",
    addEventListener: (_type: string, listener: ChangeListener): void => {
      changeListeners.push(listener);
    },
    removeEventListener: (_type: string, listener: ChangeListener): void => {
      changeListeners = changeListeners.filter((candidate) => candidate !== listener);
    },
  };
  window.matchMedia = vi
    .fn()
    .mockImplementation((query: string) =>
      query.includes("prefers-color-scheme") ? mediaQueryList : { ...mediaQueryList, matches: false },
    ) as unknown as typeof window.matchMedia;
}

function renderToggle(): void {
  render(
    <ThemeProvider>
      <ThemeToggle />
    </ThemeProvider>,
  );
}

function toggleButton(): HTMLElement {
  return screen.getByRole("button", { name: /^Color theme:/ });
}

function emitSystemScheme(dark: boolean): void {
  act(() => {
    systemDark = dark;
    for (const listener of changeListeners) {
      listener({ matches: dark } as MediaQueryListEvent);
    }
  });
}

describe("ThemeProvider", () => {
  beforeEach(() => {
    mockMatchMedia();
    window.localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  afterEach(() => {
    cleanup();
    document.documentElement.removeAttribute("data-theme");
  });

  it("follows the system color scheme when no theme is stored", () => {
    systemDark = true;
    renderToggle();
    expect(toggleButton()).toHaveAccessibleName("Color theme: dark");
    expect(toggleButton()).toHaveAttribute("aria-pressed", "true");
    expect(document.documentElement).not.toHaveAttribute("data-theme");
  });

  it("prefers a stored explicit theme over the system preference", () => {
    systemDark = true;
    window.localStorage.setItem(THEME_STORAGE_KEY, "light");
    renderToggle();
    expect(toggleButton()).toHaveAccessibleName("Color theme: light");
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
  });

  it("falls back to the system scheme when the stored value is invalid", () => {
    systemDark = true;
    window.localStorage.setItem(THEME_STORAGE_KEY, "purple");
    renderToggle();
    expect(toggleButton()).toHaveAccessibleName("Color theme: dark");
    expect(document.documentElement).not.toHaveAttribute("data-theme");
  });

  it("persists a toggled theme and applies it to the document root", () => {
    systemDark = false;
    renderToggle();
    expect(toggleButton()).toHaveAccessibleName("Color theme: light");

    fireEvent.click(toggleButton());
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(toggleButton()).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(toggleButton());
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(toggleButton()).toHaveAttribute("aria-pressed", "false");
  });

  it("keeps following the OS scheme until an explicit theme is stored", () => {
    renderToggle();
    expect(toggleButton()).toHaveAccessibleName("Color theme: light");

    emitSystemScheme(true);
    expect(toggleButton()).toHaveAccessibleName("Color theme: dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
    expect(document.documentElement).not.toHaveAttribute("data-theme");
  });

  it("ignores OS scheme changes once an explicit theme is stored", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "light");
    renderToggle();
    emitSystemScheme(true);
    expect(toggleButton()).toHaveAccessibleName("Color theme: light");
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
  });
});
