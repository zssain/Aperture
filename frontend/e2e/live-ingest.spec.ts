import path from "node:path";

import { expect, test } from "@playwright/test";

async function signIn(page: import("@playwright/test").Page) {
  await page.goto("/ingest");
  await page.getByLabel("Email").fill("e2e-analyst@aperture.test");
  await page.getByLabel("Password").fill("E2e-Strong-Passw0rd!");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/ingest/);
  await expect(page.getByLabel("Applicant name")).toBeVisible();
}

test("clean_gig.csv runs through the live backend and worker to a case decision", async ({
  page,
}) => {
  test.setTimeout(60_000);
  await signIn(page);

  await page.getByLabel("Applicant name").fill("Live Upload Applicant");
  await page.getByLabel("External reference").fill(`PW-${Date.now()}`);
  await page.getByLabel("Occupation").selectOption("GIG");
  await page.getByLabel("Declared monthly income (₹)").fill("50000");
  await page.getByLabel("Requested amount (₹)").fill("20000");
  await page.getByLabel("Requested tenor (months)").fill("12");
  await page.getByLabel(/Upload statement/).check();
  await page
    .getByLabel("Statement file")
    .setInputFiles(path.resolve("../backend/tests/fixtures/statements/clean_gig.csv"));
  const uploadResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/v1/applications/documents"),
  );
  await page.getByRole("button", { name: "Upload and start case" }).click();

  const upload = await uploadResponse;
  expect(upload.status()).toBe(201);
  const body = (await upload.json()) as {
    already_ingested: boolean;
    ingestion: { ingested: number; rejected: number } | null;
  };
  if (body.already_ingested) {
    await page.getByRole("link", { name: "Open the existing case" }).click();
  } else {
    expect(body.ingestion).toMatchObject({ ingested: 7, rejected: 0 });
  }
  await expect(page).toHaveURL(/\/cases\/[0-9a-f-]+(?:\?tab=[a-z-]+)?$/, { timeout: 30_000 });
  const decision = page.getByRole("region", { name: "Decision" });
  await expect(decision).toBeVisible();
  await expect(decision.getByText(/APPROVE|DECLINE|REVIEW/)).toBeVisible();
});

test("connected account runs through the live mock AA adapter and worker to a case", async ({
  page,
}) => {
  test.setTimeout(60_000);
  await signIn(page);

  await page.getByLabel("Applicant name").fill("Live Connect Applicant");
  await page.getByLabel("External reference").fill(`PW-CONNECT-${Date.now()}`);
  await page.getByLabel("Occupation").selectOption("GIG");
  await page.getByLabel("Declared monthly income (₹)").fill("50000");
  await page.getByLabel("Requested amount (₹)").fill("20000");
  await page.getByLabel("Requested tenor (months)").fill("12");
  await page.getByLabel(/Connect financial accounts/).check();
  await page.getByLabel("Bank accounts").check();
  await page.getByLabel(/explicitly grants this consent/).check();

  const createResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/applications") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Connect and start pipeline" }).click();
  expect((await createResponse).status()).toBe(201);

  await expect(page).toHaveURL(/\/cases\/[0-9a-f-]+(?:\?tab=[a-z-]+)?$/, { timeout: 30_000 });
  const decision = page.getByRole("region", { name: "Decision" });
  await expect(decision).toBeVisible();
  await expect(decision.getByText(/APPROVE|DECLINE|REVIEW/)).toBeVisible();
});
