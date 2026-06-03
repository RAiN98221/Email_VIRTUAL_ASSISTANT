const fs = require("fs");
const path = require("path");
const { chromium, expect } = require("@playwright/test");

const BASE_URL = process.env.BASE_URL || "http://127.0.0.1:8000";
const DELAY_MS = Number(process.env.VISUAL_DELAY_MS || 1200);
const OUT_DIR = path.join("test-results", "visual-walkthrough");

function safeName(name) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

async function pause(page) {
  await page.waitForTimeout(DELAY_MS);
}

async function step(page, name, action) {
  console.log(`\n-- ${name}`);
  await action();
  await pause(page);
  await page.screenshot({ path: path.join(OUT_DIR, `${safeName(name)}.png`), fullPage: true });
}

async function openPage(page, pageId) {
  await page.goto(`${BASE_URL}/#${pageId}`);
  await expect(page.locator(`#${pageId}`)).toHaveClass(/active/);
}

(async () => {
  fs.mkdirSync(OUT_DIR, { recursive: true });

  const browser = await chromium.launch({
    headless: false,
    slowMo: 450,
  });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  page.on("dialog", async (dialog) => {
    console.log(`Dialog: ${dialog.message()}`);
    await dialog.accept();
  });

  await page.route("**/api/jobs", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    const requestBody = route.request().postDataJSON();
    console.log(`Mocked launch for ${requestBody.selected_row_indexes.length} recipients`);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "visual-walkthrough-mocked-job",
        queued: requestBody.selected_row_indexes.length,
      }),
    });
  });

  try {
    await step(page, "Dashboard overview", async () => {
      await openPage(page, "dashboard");
      await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    });

    await step(page, "Campaign create default", async () => {
      await page.locator("#newCampaignBtn").click();
      await expect(page.locator("#campaignCreate")).toHaveClass(/active-card/);
      await expect(page.locator("#csvFile")).toBeVisible();
      await expect(page.locator("#validReady")).toContainText("valid emails ready");
    });

    await step(page, "Campaign continue to review contacts", async () => {
      await page.locator("#campaignContinueBtn").click();
      await expect(page.getByRole("heading", { name: "Recipient Preview & Review Contacts" })).toBeVisible();
      await expect(page.locator("#previewRows tr").first()).toBeVisible();
    });

    await step(page, "Review contacts include already contacted and select all", async () => {
      await page.getByLabel("Include already contacted").check();
      await page.getByLabel("Select all sendable").check();
      await expect(page.locator("#selectionStatus")).not.toContainText("0 of");
      await expect(page.locator("#queueBtn")).toBeEnabled();
    });

    await step(page, "Review contacts pagination", async () => {
      await page.locator("#contactsPageSize").selectOption("10");
      await expect(page.locator("#contactsPageInfo")).toContainText("Showing");
      const next = page.locator("#contactsNextPage");
      if (await next.isEnabled()) await next.click();
      await expect(page.locator("#contactsPageLabel")).toContainText("/");
    });

    await step(page, "Launch confirmation modal cancel", async () => {
      await page.locator("#queueBtn").click();
      await expect(page.locator("#launchConfirmModal")).toBeVisible();
      await expect(page.getByRole("heading", { name: "Launch campaign?" })).toBeVisible();
      await page.locator("#cancelLaunchBtn").click();
      await expect(page.locator("#launchConfirmModal")).toBeHidden();
    });

    await step(page, "Launch confirmation mocked submit", async () => {
      await page.locator("#queueBtn").click();
      await expect(page.locator("#launchConfirmModal")).toBeVisible();
      await page.locator("#confirmLaunchBtn").click();
      await expect(page.locator("#launchConfirmModal")).toBeHidden();
    });

    await step(page, "Campaign activity table", async () => {
      await page.getByRole("button", { name: "Campaign Activity" }).click();
      await expect(page.locator("#jobs")).toBeVisible();
      await expect(page.locator("#jobsPageInfo")).toBeVisible();
    });

    await step(page, "Templates editor and preview", async () => {
      await openPage(page, "templates");
      await expect(page.locator(".template-nav-group")).toHaveClass(/open/);
      await expect(page.locator("#liveSubject")).not.toHaveText("");
      await page.locator("#subject").fill("Visual check for {{first_name}}");
      await page.locator("#body").fill("Hi {{first_name}},\n\nVisual workflow check for {{city}}.");
      await page.locator("#previewBtn").click();
      await expect(page.locator("#liveSubject")).toContainText("Visual check");
      await expect(page.locator("#liveBody")).toContainText("Visual workflow check");
      await expect(page.getByLabel("Choose Files")).toBeVisible();
    });

    await step(page, "Replies management layout", async () => {
      await openPage(page, "replies");
      await expect(page.getByRole("heading", { name: "Replies" })).toBeVisible();
      await expect(page.locator(".reply-thread").first()).toBeVisible();
      await expect(page.locator(".reply-thread strong").first()).toHaveCSS("overflow", "hidden");
    });

    await step(page, "Contacts insights and suppressions", async () => {
      await openPage(page, "contacts");
      await expect(page.getByRole("heading", { name: "Contacts", exact: true })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Contact Insights" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Suppressed Contacts" })).toBeVisible();
    });

    await step(page, "Settings time window and safety controls", async () => {
      await openPage(page, "settings");
      await page.locator("#businessStart").fill("09:30");
      await page.locator("#businessEnd").fill("16:45");
      await page.locator("#timezone").fill("America/Chicago");
      await expect(page.locator("#businessStart")).toHaveValue("09:30");
      await expect(page.locator("#businessEnd")).toHaveValue("16:45");
      await expect(page.locator("#timezone")).toHaveCSS("min-width", "220px");
    });

    console.log(`\nVisual walkthrough completed. Screenshots saved in ${OUT_DIR}`);
    await page.waitForTimeout(3000);
  } finally {
    await browser.close();
  }
})();
