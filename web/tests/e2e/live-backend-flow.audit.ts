import { test, expect } from "@playwright/test";
import path from "node:path";

const fixturePath = path.resolve(
  __dirname,
  "fixtures",
  "kb-live-sample.txt",
);

const USERNAME = "yi_live_pw";
const PASSWORD = "secret123";
const KB_NAME = "kb-live-playwright";

async function registerViaBackend(page: import("@playwright/test").Page) {
  await page.request.post("http://127.0.0.1:8001/api/v1/auth/register", {
    data: {
      username: USERNAME,
      password: PASSWORD,
    },
  });
}

test("live backend auth, knowledge and settings flows are clickable", async ({
  page,
}) => {
  await registerViaBackend(page);

  await page.goto("http://127.0.0.1:3000/");
  await expect(page.getByRole("link", { name: "Knowledge" })).toBeVisible();

  await page.goto("http://127.0.0.1:3000/knowledge");
  await expect(page.getByRole("button", { name: "New source library" })).toBeVisible();

  await page.getByRole("button", { name: "New source library" }).click();
  await expect(page.getByText("Create source library")).toBeVisible();

  const nameInput = page.getByPlaceholder("e.g. project-papers");
  await expect(nameInput).toBeVisible();
  await nameInput.fill(KB_NAME);

  const fileInput = page.locator('input[type="file"]');
  await expect(fileInput).toHaveCount(1);
  await fileInput.setInputFiles(fixturePath);

  const createButton = page.getByRole("button", { name: "Create" });
  await expect(createButton).toBeEnabled();
  await createButton.click();

  await expect(page.getByText(KB_NAME)).toBeVisible({ timeout: 10000 });
  await expect(page.getByText("kb-live-sample.txt")).toBeVisible({ timeout: 10000 });

  await page.getByRole("button", { name: "Add documents" }).click();
  await expect(page.getByRole("button", { name: "Upload" })).toBeVisible();

  await page.getByRole("button", { name: "Index versions" }).click();
  await expect(page.getByText("Index versions")).toBeVisible();

  await page.goto("http://127.0.0.1:3000/settings");
  const runButtons = page.getByRole("button", { name: "Run test" });
  await expect(runButtons.first()).toBeVisible();
  await runButtons.first().click();

  await expect(page.getByText("Diagnostics")).toBeVisible();
  await expect(page.getByText("diagnostics completed", { exact: false })).toBeVisible({
    timeout: 10000,
  });
});
