/**
 * Journey 5: add and edit a quality gate, validate the pack, scan the healthy
 * repository and render the returned gate result. The engine records the
 * first failing gate as the verdict, so the seeded zero-findings gate fails
 * on the demo workspace's non-conforming DAG and the added gate's passing
 * rule is not part of the recorded verdict. Then the seeded broken
 * repository's scan is asserted incomplete with "Gates not evaluated".
 */
import {
  BROKEN_REPOSITORY_NAME,
  HEALTHY_REPOSITORY_NAME,
  expect,
  repositoryByName,
  scanHistory,
  test,
  useAdminToken,
} from "./fixtures";
import type { Page } from "@playwright/test";
import type { ScanSummary } from "../src/api";

const PACK_BUTTON = "conformdag-e2e-pack";
const GATE_ID = "release-readiness";

async function waitForTerminalScan(page: Page, knownScans: number): Promise<string> {
  const history = page.getByRole("table", { name: "Scan history" });
  await expect(
    history.getByRole("row"),
    "the triggered scan reaches a terminal state",
  ).toHaveCount(knownScans + 2, { timeout: 30_000 });
  const newRow = history.getByRole("row").nth(1);
  await expect(newRow.getByText("PASS").first()).toBeVisible({ timeout: 30_000 });
  const href = await newRow.getByRole("link").first().getAttribute("href");
  expect(href, "the history row links to the scan").toMatch(/^\/scans\/[0-9a-f]{32}$/);
  return (href as string).split("/")[2] as string;
}

test("gate add/edit drives a real gate result, and the broken scan stays incomplete", async ({ page }) => {
  await useAdminToken(page);

  const healthy = await repositoryByName(page.request, HEALTHY_REPOSITORY_NAME);
  const broken = await repositoryByName(page.request, BROKEN_REPOSITORY_NAME);
  const brokenScans = await scanHistory(page.request, broken.id);
  const brokenScan = brokenScans.find((scan) => scan.complete === false);
  expect(brokenScan, "the broken repository seeds an incomplete scan").toBeDefined();
  const brokenScanId = (brokenScan as ScanSummary).scan_id;

  await page.goto("/policies");
  await expect(page).toHaveURL(/\/policies$/);
  await page.getByRole("button", { name: new RegExp(PACK_BUTTON) }).click();

  const gates = page.getByRole("table", { name: "Quality gates" });
  await expect(gates).toBeVisible();

  await page.getByRole("button", { name: "New gate" }).click();
  const dialog = page.getByRole("dialog", { name: "New gate" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Gate ID").fill(GATE_ID);
  await dialog.getByRole("button", { name: "Add rule" }).click();
  await dialog.getByLabel("Rule 1 type").selectOption("max-findings");
  await dialog.getByLabel("Rule 1 count").fill("10");
  await dialog.getByRole("button", { name: "Save gate" }).click();
  await expect(dialog).toBeHidden();
  await expect(gates.getByRole("row", { name: new RegExp(GATE_ID) })).toContainText(
    "at most 10 findings",
  );

  await gates
    .getByRole("row", { name: new RegExp(GATE_ID) })
    .getByRole("button", { name: `Edit gate ${GATE_ID}` })
    .click();
  const editDialog = page.getByRole("dialog", { name: `Edit gate ${GATE_ID}` });
  await expect(editDialog).toBeVisible();
  await editDialog.getByLabel("Rule 1 count").fill("25");
  await editDialog.getByRole("button", { name: "Save gate" }).click();
  await expect(editDialog).toBeHidden();
  await expect(gates.getByRole("row", { name: new RegExp(GATE_ID) })).toContainText(
    "at most 25 findings",
  );

  await page.getByRole("button", { name: "Validate pack" }).click();
  await expect(page.getByText("Pack is valid.")).toBeVisible();

  await page.goto(`/repos/${healthy.id}`);
  await expect(page).toHaveURL(new RegExp(`/repos/${healthy.id}$`));
  const knownScans = (await scanHistory(page.request, healthy.id)).length;
  await page.getByRole("button", { name: "Trigger scan" }).click();
  const scanId = await waitForTerminalScan(page, knownScans);

  await page.goto(`/scans/${scanId}`);
  await expect(page).toHaveURL(new RegExp(`/scans/${scanId}$`));
  // The engine records the first failing gate as the verdict. The demo
  // workspace's healthy DAG is deliberately non-conforming after the
  // baseline, so the seeded zero-findings gate fails on the triggered scan.
  const gateResult = page.getByRole("region", { name: "Gate result" });
  await expect(gateResult.getByText("Gate failed")).toBeVisible();
  const gateRules = gateResult.getByRole("table", { name: "Gate rules" });
  await expect(gateRules).toContainText("max-findings");
  await expect(gateRules.getByRole("row", { name: /limit is 0/ })).toContainText("FAIL");

  await page.goto(`/scans/${brokenScanId}`);
  await expect(page).toHaveURL(new RegExp(`/scans/${brokenScanId}$`));
  const brokenGate = page.getByRole("region", { name: "Gate result" });
  await expect(brokenGate.getByText("Gates not evaluated")).toBeVisible();
  await expect(brokenGate.getByText("Not evaluated", { exact: true })).toBeVisible();
  const summary = page.getByRole("region", { name: "Scan summary" });
  await expect(summary.getByText("Incomplete", { exact: true })).toBeVisible();
  await expect(summary.getByText(/scan incomplete: PARSE_ERROR/)).toBeVisible();
  await expect(page.getByRole("table", { name: "Run issues" })).toContainText("PARSE_ERROR");
});
