/**
 * Golden journey: the guided demo tour (`/?demo=1`) over the real seeded
 * platform. Scenario ids and data are resolved through `/api/v1` only — the
 * journey never locates a target by a seeded repository name, policy title,
 * scan id, or suppression reason. Each stage asserts its stable `data-tour`
 * target and that the URL keeps `demo=1`; Skip hides the dialog and Restart
 * returns it to the overview step.
 */
import {
  currentCompletedScan,
  expect,
  failFindings,
  firstFinding,
  repositoryByName,
  suppressionsByState,
  test,
  HEALTHY_REPOSITORY_NAME,
} from "./fixtures";
import type { Finding, Suppression } from "../src/api";

test("demo tour advances through every stage, then skips and restarts", async ({ page }) => {
  // Resolve the golden-story data from the platform, never from display text.
  // The shared seed makes the healthy current gate-failed scan the newest
  // scan, so the tour's first hop lands here without any test-only setup.
  const healthy = await repositoryByName(page.request, HEALTHY_REPOSITORY_NAME);
  const current = await currentCompletedScan(page.request, healthy.id);
  expect(current.gate_passed, "the current scan records a failed gate").toBe(false);

  const finding = await firstFinding(page.request, current.scan_id);
  const failures = await failFindings(page.request, current.scan_id);
  expect(
    failures.map((item) => item.fingerprint),
    "firstFinding resolves one of the current scan's FAIL findings",
  ).toContain(finding.fingerprint);

  const suppressedFinding = failures.find((item) => item.suppressed);
  const unsuppressedFinding = failures.find((item) => !item.suppressed);
  expect(suppressedFinding, "the current scan keeps a suppressed FAIL finding").toBeDefined();
  expect(unsuppressedFinding, "the current scan keeps an unsuppressed FAIL finding").toBeDefined();

  const { active, expired } = await suppressionsByState(page.request);
  const activeSuppression = active.find(
    (suppression) => suppression.fingerprint === (suppressedFinding as Finding).fingerprint,
  );
  const expiredSuppression = expired.find(
    (suppression) => suppression.fingerprint === (unsuppressedFinding as Finding).fingerprint,
  );
  expect(activeSuppression, "an active waiver matches the suppressed finding").toBeDefined();
  expect(expiredSuppression, "an expired waiver matches the unsuppressed finding").toBeDefined();
  expect(
    (activeSuppression as Suppression).id !== (expiredSuppression as Suppression).id,
    "the active and expired waivers are distinct records",
  ).toBe(true);

  const tour = page.getByRole("dialog", { name: "ConformDAG demo tour" });
  const tourNext = page.getByRole("button", { name: "Tour next" });
  const target = (marker: string) => page.locator(`[data-tour="${marker}"]`);

  await page.goto("/?demo=1");
  await expect(page).toHaveURL(/\/\?demo=1$/);
  await expect(tour).toBeVisible();
  await expect(target("overview-signal")).toBeVisible();

  // Overview → repository: the tour follows the overview's repository link.
  await tourNext.click();
  await expect(page).toHaveURL(new RegExp(`/repos/${healthy.id}\\?demo=1$`));
  await expect(target("scan-link")).toBeVisible();

  // Repository → scan: the tour follows the newest scan link.
  await tourNext.click();
  await expect(page).toHaveURL(new RegExp(`/scans/${current.scan_id}\\?demo=1$`));
  const gate = target("gate-result");
  await expect(gate).toBeVisible();
  await expect(gate.getByText("Gate failed")).toBeVisible();

  // Scan → remediation: the tour presses the finding's Details button and the
  // detail dialog shows the remediation section.
  await tourNext.click();
  await expect(target("finding-remediation")).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`/scans/${current.scan_id}\\?demo=1$`));

  // Remediation → policy pack: tour-owned navigation.
  await tourNext.click();
  await expect(page).toHaveURL(/\/policies\?demo=1$/);
  // The tour presses the first marked pack button, so assert that one.
  await expect(target("policy-pack").first()).toBeVisible();

  // Policy pack → quality gate: the tour presses the marked pack button.
  await tourNext.click();
  await expect(page).toHaveURL(/\/policies\?demo=1$/);
  await expect(target("policy-gate")).toBeVisible();

  // Quality gate → suppressions: tour-owned navigation.
  await tourNext.click();
  await expect(page).toHaveURL(/\/suppressions\?demo=1$/);
  // The tour highlights the first marker match (querySelector), so the rows
  // are asserted the same way.
  const activeRow = target("suppression-active")
    .filter({ hasText: (activeSuppression as Suppression).fingerprint })
    .first();
  const expiredRow = target("suppression-expired")
    .filter({ hasText: (expiredSuppression as Suppression).fingerprint })
    .first();
  await expect(activeRow).toBeVisible();
  await expect(activeRow.getByText("SUPPRESSED")).toBeVisible();
  await expect(expiredRow).toBeVisible();
  await expect(expiredRow.getByText("Expired")).toBeVisible();

  // Active → expired suppression: same route, next step.
  await tourNext.click();
  await expect(page).toHaveURL(/\/suppressions\?demo=1$/);
  await expect(expiredRow).toBeVisible();

  // Expired → export: the tour revisits the recorded scan route.
  await tourNext.click();
  await expect(page).toHaveURL(new RegExp(`/scans/${current.scan_id}\\?demo=1$`));
  const exportAnchor = target("scan-export");
  await expect(exportAnchor).toBeVisible();
  await expect(exportAnchor).toHaveAttribute("href", `/api/v1/scans/${current.scan_id}/export/json`);

  // Skip hides the dialog; the dismissal survives a reload as the restart chip.
  await page.getByRole("button", { name: "Skip tour" }).click();
  await expect(tour).toBeHidden();
  await page.goto("/?demo=1");
  await expect(page.getByRole("button", { name: "Restart tour" })).toBeVisible();

  // Restart returns the tour to the overview step.
  await page.getByRole("button", { name: "Restart tour" }).click();
  await expect(tour).toBeVisible();
  await expect(tour.getByText(/^Step 1 of/)).toBeVisible();
  await expect(target("overview-signal")).toBeVisible();
});
