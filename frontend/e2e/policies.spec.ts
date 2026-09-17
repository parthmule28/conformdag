/**
 * Journey 4: edit a policy's tags and metadata through the server-validated
 * editor, validate the pack, reload the route, and observe the saved value
 * served back by the platform.
 */
import { expect, test, useAdminToken } from "./fixtures";

const PACK_BUTTON = "conformdag-e2e-pack";
const POLICY_ID = "AIR-DET-001";

test("edit policy tags, validate the pack, and observe the persisted value", async ({ page }) => {
  await useAdminToken(page);

  await page.goto("/policies");
  await expect(page).toHaveURL(/\/policies$/);

  await page.getByRole("button", { name: new RegExp(PACK_BUTTON) }).click();

  const policies = page.getByRole("table", { name: "Policies" });
  await expect(policies).toBeVisible();
  const ownerRow = policies.getByRole("row", { name: new RegExp(POLICY_ID) });
  await expect(ownerRow).toBeVisible();

  await ownerRow.getByRole("button", { name: `Edit policy ${POLICY_ID}` }).click();
  const dialog = page.getByRole("dialog", { name: `Edit policy ${POLICY_ID}` });
  await expect(dialog).toBeVisible();

  await dialog.getByLabel("Tags").fill("governance, e2e-edited");
  await dialog.getByLabel("Safe path").fill("An approved owner is present.");
  await dialog.getByRole("button", { name: "Save changes" }).click();
  await expect(dialog).toBeHidden();

  await expect(ownerRow).toContainText("e2e-edited");

  await page.getByRole("button", { name: "Validate pack" }).click();
  await expect(page.getByText("Pack is valid.")).toBeVisible();

  await page.reload();
  await expect(page).toHaveURL(/\/policies$/);
  await page.getByRole("button", { name: new RegExp(PACK_BUTTON) }).click();
  await expect(policies.getByRole("row", { name: new RegExp(POLICY_ID) })).toContainText(
    "e2e-edited",
  );
});
