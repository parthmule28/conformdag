/**
 * Journey 2: trigger a scan from the repository page, observe the bounded
 * active polling until it completes, open the completed scan, filter a
 * finding server-side, and inspect its detail dialog.
 */
import {
  ADMIN_TOKEN,
  HEALTHY_REPOSITORY_NAME,
  expect,
  repositoryByName,
  scanHistory,
  test,
} from "./fixtures";

test("trigger scan, watch bounded polling, filter a finding, inspect its detail", async ({ page }) => {
  const healthy = await repositoryByName(page.request, HEALTHY_REPOSITORY_NAME);
  const seededScans = await scanHistory(page.request, healthy.id);

  await page.goto(`/repos/${healthy.id}`);
  await expect(page).toHaveURL(new RegExp(`/repos/${healthy.id}$`));

  // Scans are a mutation: the operator saves the admin token through the
  // shell first, exactly as the console expects outside the test environment.
  await page.getByLabel("Admin token").fill(ADMIN_TOKEN);
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Admin token saved")).toBeVisible();

  const history = page.getByRole("table", { name: "Scan history" });
  await expect(history).toBeVisible();

  await page.getByRole("button", { name: "Trigger scan" }).click();
  await expect(page.getByText("Scan queued")).toBeVisible();

  // The history gains the queued row and polling carries it to a terminal
  // state; the worker and bounded refetch decide when, the journey only
  // asserts a bounded wait.
  await expect(
    history.getByRole("row"),
    "triggered scan appears in the history table",
  ).toHaveCount(seededScans.length + 2, { timeout: 30_000 });

  const newRow = history.getByRole("row").nth(1);
  await expect(newRow.getByText("PASS").first()).toBeVisible({ timeout: 30_000 });

  await newRow.locator('a[href^="/scans/"]').click();
  await expect(page).toHaveURL(/\/scans\/[0-9a-f]{32}$/);

  const summary = page.getByRole("region", { name: "Scan summary" });
  await expect(summary.getByText("Succeeded")).toBeVisible();
  await expect(summary.getByText("Complete", { exact: true })).toBeVisible();

  const findings = page.getByRole("table", { name: "Findings" });
  await expect(findings).toBeVisible();
  await expect(findings.getByRole("row").first()).toBeVisible();

  await page.getByLabel("Status").selectOption("FAIL");
  await expect(findings.getByText("AIR-DET-002")).toBeVisible();

  await findings.getByRole("button", { name: "Details for AIR-DET-002" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(
    dialog.getByRole("paragraph").filter({ hasText: "missing tags=" }),
  ).toBeVisible();
  await expect(dialog.getByText("Explanation", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(dialog).toBeHidden();
});
