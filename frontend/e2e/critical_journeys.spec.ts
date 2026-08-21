import { expect, test } from "@playwright/test";

test("release deployment is live and the authentication journey is actionable", async ({ page, request }) => {
  const health = await request.get("http://127.0.0.1:8000/api/v1/health");
  expect(health.ok()).toBeTruthy();
  expect(await health.json()).toMatchObject({ status: "ok" });

  await page.goto("/signin");
  await expect(page.getByRole("img", { name: "Aperture" })).toBeVisible();
  await expect(page.locator('link[rel="icon"]')).toHaveAttribute(
    "href",
    "/brand/aperture-favicon.svg",
  );
  await expect(page.getByRole("button", { name: /sign in/i })).toBeEnabled();
  await expect(page.getByLabel(/email/i)).toBeEditable();
  await expect(page.getByLabel(/password/i)).toBeEditable();
});
