import { expect, test } from "@playwright/test";

test("public homepage renders, routes to sign-in, and logs no console errors", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(err.message));

  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/credit bureaus can/i);
  await expect(page.getByRole("main")).toBeVisible();
  await page.getByRole("link", { name: /see how it works/i }).click();
  await expect(page.getByRole("heading", { name: /consent to decision/i })).toBeVisible();
  await page.getByRole("link", { name: /^sign in$/i }).first().click();
  await expect(page).toHaveURL(/\/signin$/);

  expect(consoleErrors, `console errors: ${consoleErrors.join(" | ")}`).toEqual([]);
});

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
