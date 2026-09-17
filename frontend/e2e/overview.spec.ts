/**
 * Journey 1: load the overview, open a repository from it, inspect scan
 * history and trends, and identify the current baseline. Includes the mobile
 * shell/table pass required by the plan.
 */
import {
  BROKEN_REPOSITORY_NAME,
  HEALTHY_REPOSITORY_NAME,
  expect,
  repositoryByName,
  test,
} from "./fixtures";

test("overview drill-down to repository history, trends, and baseline", async ({ page }) => {
  const healthy = await repositoryByName(page.request, HEALTHY_REPOSITORY_NAME);
  const broken = await repositoryByName(page.request, BROKEN_REPOSITORY_NAME);
  expect(healthy.baseline_scan_id).not.toBeNull();

  await page.goto("/");
  await expect(page).toHaveURL(/\/$/);

  const overviewMetrics = page.getByText("Repositories", { exact: true });
  await expect(overviewMetrics).toBeVisible();
  await expect(page.getByText("Completed scans", { exact: true })).toBeVisible();

  const recentScans = page.getByRole("table", { name: "Recent scans" });
  await expect(recentScans).toBeVisible();
  await expect(
    recentScans.getByRole("link", { name: HEALTHY_REPOSITORY_NAME }).first(),
  ).toBeVisible();
  await expect(
    recentScans.getByRole("link", { name: BROKEN_REPOSITORY_NAME }).first(),
  ).toBeVisible();

  await expect(page.getByRole("img", { name: /daily points from/ })).toBeVisible();

  await recentScans.getByRole("link", { name: HEALTHY_REPOSITORY_NAME }).first().click();
  await expect(page).toHaveURL(new RegExp(`/repos/${healthy.id}$`));

  const history = page.getByRole("table", { name: "Scan history" });
  await expect(history).toBeVisible();
  await expect(history.getByRole("link", { name: healthy.baseline_scan_id as string })).toBeVisible();
  await expect(history.getByRole("button", { name: "Current baseline" })).toBeVisible();

  await expect(page.getByRole("img", { name: /daily points from/ })).toBeVisible();

  await history.getByRole("link", { name: healthy.baseline_scan_id as string }).click();
  await expect(page).toHaveURL(new RegExp(`/scans/${healthy.baseline_scan_id}$`));
  const baselineSummary = page.getByRole("region", { name: "Scan summary" });
  await expect(baselineSummary.getByText("Succeeded")).toBeVisible();
  await expect(baselineSummary.getByText("Complete", { exact: true })).toBeVisible();
});

test.describe("mobile shell and table", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("mobile navigation opens and the overview table stays reachable", async ({ page }) => {
    const healthy = await repositoryByName(page.request, HEALTHY_REPOSITORY_NAME);

    await page.goto("/");
    await expect(page).toHaveURL(/\/$/);

    const mobileNav = page.getByRole("navigation", { name: "Primary mobile" });
    await expect(mobileNav).toBeHidden();

    await page.getByRole("button", { name: "Open navigation" }).click();
    await expect(mobileNav).toBeVisible();
    await mobileNav.getByRole("link", { name: "Overview" }).click();
    await expect(page).toHaveURL(/\/$/);

    const recentScans = page.getByRole("table", { name: "Recent scans" });
    await expect(recentScans).toBeVisible();
    await expect(
      recentScans.getByRole("link", { name: HEALTHY_REPOSITORY_NAME }).first(),
    ).toBeVisible();

    await recentScans.getByRole("link", { name: HEALTHY_REPOSITORY_NAME }).first().click();
    await expect(page).toHaveURL(new RegExp(`/repos/${healthy.id}$`));
    await expect(page.getByRole("table", { name: "Scan history" })).toBeVisible();
  });
});
