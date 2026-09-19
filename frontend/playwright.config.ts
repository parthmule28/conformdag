/**
 * Playwright configuration for the platform browser journeys.
 *
 * Two web servers are started before the suite runs:
 * - the disposable backend on port 8642 (`scripts/e2e_platform.py`), which
 *   seeds the shared demo scenario (`conformdag.platform.demo`) into a
 *   temporary SQLite database and serves the real `/api/v1` routes from it;
 *   and
 * - the Vite dev server on port 4173, whose existing `/api` proxy forwards
 *   browser traffic to the seeded backend.
 *
 * The journeys run in Chromium only, single-worker (the seeded platform is
 * shared state), with a trace captured on the first retry.
 */
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "line" : "list",
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
  webServer: [
    {
      command: "uv run python ../scripts/e2e_platform.py",
      url: "http://127.0.0.1:8642/api/v1/health",
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 4173 --strictPort",
      url: "http://127.0.0.1:4173",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      stdout: "ignore",
      stderr: "pipe",
    },
  ],
});
