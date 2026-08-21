import { expect, test } from "@playwright/test";

test("skip link and visible keyboard focus work", async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: { user_id: "1", email: "a@b.test", full_name: "Analyst", role: "CREDIT_ANALYST", tenant_id: "2", tenant_name: "Acme" } }));
  await page.route("**/api/v1/queue?*", (route) => route.fulfill({ json: { view: "my-exceptions", counts: {}, rows: [], next_cursor: null, auto_decided_24h: 3 } }));
  await page.goto("/queue"); await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.keyboard.press("Enter"); await expect(page.locator("#main-content")).toBeFocused();
});

test("reduced motion removes transitions without disabling controls", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: { user_id: "1", email: "a@b.test", full_name: "Analyst", role: "CREDIT_ANALYST", tenant_id: "2", tenant_name: "Acme" } }));
  await page.route("**/api/v1/queue?*", (route) => route.fulfill({ json: { view: "my-exceptions", counts: {}, rows: [], next_cursor: null, auto_decided_24h: 3 } }));
  await page.goto("/queue");
  const control = page.getByRole("button", { name: "View all decisions" });
  await expect(control).toBeEnabled();
  const duration = await control.evaluate((element) => getComputedStyle(element).transitionDuration);
  expect(["0.01ms", "1e-05s"]).toContain(duration);
  await control.focus(); await expect(control).toBeFocused();
});
