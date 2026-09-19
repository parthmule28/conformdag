/**
 * Journey 3: create a suppression with owner/expiry and confirm it appears,
 * and verify the seeded past-expiry waiver is visually distinct and is never
 * presented as active (its expiry is enforced at scan time by the server).
 */
import {
  HEALTHY_REPOSITORY_NAME,
  currentCompletedScan,
  expect,
  failFindings,
  repositoryByName,
  suppressionsByState,
  test,
  useAdminToken,
} from "./fixtures";

test("create a suppression and distinguish the seeded expired waiver", async ({ page }) => {
  await useAdminToken(page);

  const healthy = await repositoryByName(page.request, HEALTHY_REPOSITORY_NAME);
  const current = await currentCompletedScan(page.request, healthy.id);
  const [findings, suppressionStates] = await Promise.all([
    failFindings(page.request, current.scan_id),
    suppressionsByState(page.request),
  ]);
  const seededIdentities = new Set(
    [...suppressionStates.active, ...suppressionStates.expired].map(
      (suppression) => `${suppression.policy_id}:${suppression.fingerprint}`,
    ),
  );
  const finding = findings.find(
    (candidate) => !seededIdentities.has(`${candidate.policy_id}:${candidate.fingerprint}`),
  );
  expect(finding, "the demo seeds a real failure with an unused suppression identity").toBeDefined();
  if (finding === undefined) {
    throw new Error("the demo did not seed a failure with an unused suppression identity");
  }

  await page.goto("/suppressions");
  await expect(page).toHaveURL(/\/suppressions$/);

  const table = page.getByRole("table", { name: "Suppressions" });
  await expect(table).toBeVisible();

  // The seeded expired waiver: visually distinct, excluded from Active, and
  // the only row presented under Expired (the seeded active waiver stays a
  // current SUPPRESSED record).
  const expiredCell = table.getByText("Expired", { exact: true });
  await expect(expiredCell).toBeVisible();
  await page.getByLabel("State").selectOption("active");
  await expect(expiredCell).toBeHidden();
  await expect(table.getByText("SUPPRESSED").first()).toBeVisible();
  await page.getByLabel("State").selectOption("expired");
  await expect(expiredCell).toBeVisible();
  await expect(table.getByText("SUPPRESSED")).toHaveCount(0);
  await page.getByLabel("State").selectOption("");

  await page.getByRole("button", { name: "New suppression" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Policy ID").fill(finding.policy_id);
  await dialog.getByLabel("Fingerprint").fill(finding.fingerprint);
  await dialog.getByLabel("Reason").fill("Waived by the e2e browser journey");
  await dialog.getByLabel("Owner").fill("e2e-owner");
  await dialog.getByLabel("Expires at").fill("2099-01-01T00:00");
  await dialog.getByRole("button", { name: "Save suppression" }).click();
  await expect(dialog).toBeHidden();

  // The created row is a distinct suppression identity and is distinguished by
  // the owner the journey entered.
  const newRow = table
    .getByRole("row", { name: new RegExp(finding.fingerprint) })
    .filter({ hasText: "e2e-owner" });
  await expect(newRow).toBeVisible();
  await expect(newRow.getByText("SUPPRESSED")).toBeVisible();
  await expect(newRow.getByText("e2e-owner")).toBeVisible();
});
