const { test, expect } = require("@playwright/test");
const fs = require("fs");
const path = require("path");

async function openPage(page, pageId) {
  await page.goto(`/#${pageId}`);
  await expect(page.locator(`#${pageId}`)).toHaveClass(/active/);
}

function cleanupUploadedCsv(filename) {
  const uploadPath = path.join(process.cwd(), "uploaded_csv", filename);
  // Windows Defender can briefly lock freshly written files; cleanup must not fail the test.
  for (let attempt = 0; attempt < 5; attempt += 1) {
    try {
      if (fs.existsSync(uploadPath)) fs.unlinkSync(uploadPath);
      return;
    } catch (error) {
      if (!["EBUSY", "EPERM"].includes(error.code)) throw error;
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 200);
    }
  }
}

test.describe("CSV Email Assistant UI", () => {
  test("main pages render without clipped critical controls", async ({ page }) => {
    await page.route("**/api/replies**", async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          replies: [
            {
              id: 1,
              from_email: "david.wilson@email.com",
              subject: "interested",
              body: "Thanks for reaching out. I'm interested.",
              received_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              campaign_name: "sample",
            },
            {
              id: 2,
              from_email: "sarah.johnson@email.com",
              subject: "follow up",
              body: "I'm currently exploring new opportunities.",
              received_at: new Date(Date.now() - 3600000).toISOString(),
              updated_at: new Date(Date.now() - 3600000).toISOString(),
              campaign_name: "sample",
            },
          ],
        }),
      });
    });

    await openPage(page, "dashboard");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await page.screenshot({ path: `test-results/screenshots/dashboard-${test.info().project.name}.png`, fullPage: true });

    await openPage(page, "campaigns");
    await expect(page.getByRole("button", { name: "Create Campaign" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Review Contacts" })).toBeVisible();
    await page.getByRole("button", { name: "Review Contacts" }).click();
    await expect(page.getByRole("heading", { name: "Recipients", exact: true })).toBeVisible();
    await page.screenshot({ path: `test-results/screenshots/campaigns-${test.info().project.name}.png`, fullPage: true });

    await openPage(page, "templates");
    await expect(page.locator(".template-nav-group")).toHaveClass(/open/);
    await expect(page.locator(".template-nav-group")).not.toContainText("Software Engineer Outreach");
    await expect(page.locator(".template-nav-group")).not.toContainText("Full Stack Developer Outreach");
    await expect(page.getByRole("heading", { name: "Templates", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Preview" })).toBeVisible();
    await page.screenshot({ path: `test-results/screenshots/templates-${test.info().project.name}.png`, fullPage: true });

    await openPage(page, "replies");
    await expect(page.getByRole("heading", { name: "Replies" })).toBeVisible();
    await expect(page.locator(".reply-thread").first()).toBeVisible();
    await expect(page.locator(".reply-thread strong").first()).toHaveCSS("overflow", "hidden");
    await page.locator(".reply-thread").nth(1).click();
    await expect(page.locator(".reply-thread").nth(1)).toHaveClass(/active/);
    await expect(page.locator("#replySender")).toContainText("Sarah Johnson");
    await expect(page.locator("#replyMessage")).toContainText("exploring new opportunities");
    await page.screenshot({ path: `test-results/screenshots/replies-${test.info().project.name}.png`, fullPage: true });

    await openPage(page, "settings");
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
    await expect(page.locator("#businessStart")).toBeVisible();
    await expect(page.locator("#timezone")).toBeVisible();
    await expect(page.locator("#timezone")).toHaveCSS("min-width", "220px");
    await page.screenshot({ path: `test-results/screenshots/settings-${test.info().project.name}.png`, fullPage: true });
  });

  test("dashboard notification and theme buttons are functional", async ({ page }) => {
    await openPage(page, "dashboard");

    await page.locator("#notificationBtn").click();
    await expect(page.locator("#notificationPanel")).toBeVisible();
    await expect(page.locator("#notificationList .notification-item").first()).toBeVisible();
    await expect(page.locator("#notificationBtn")).toHaveAttribute("aria-expanded", "true");
    await page.keyboard.press("Escape");
    await expect(page.locator("#notificationPanel")).toBeHidden();

    await page.locator("#themeToggleBtn").click();
    await expect(page.locator("body")).toHaveAttribute("data-theme", "dark");
    await expect(page.locator("#themeToggleBtn")).toHaveAttribute("aria-pressed", "true");
    await page.reload();
    await expect(page.locator("body")).toHaveAttribute("data-theme", "dark");
    await page.locator("#themeToggleBtn").click();
    await expect(page.locator("body")).toHaveAttribute("data-theme", "light");
  });

  test("launch campaign requires confirmation", async ({ page }) => {
    await openPage(page, "campaigns");
    await page.getByRole("button", { name: "Review Contacts" }).click();
    await expect(page.getByRole("heading", { name: "Recipients", exact: true })).toBeVisible();

    await page.getByLabel("Include already contacted").check();
    await expect(page.locator("#previewRows tr").first()).toBeVisible();
    await page.getByLabel("Select all sendable").check();
    await expect(page.locator("#queueBtn")).toBeEnabled();

    await page.locator("#queueBtn").click();
    await expect(page.locator("#launchConfirmModal")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Launch campaign?" })).toBeVisible();
    await expect(page.locator("#confirmRecipientCount")).not.toHaveText("0 selected");

    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(page.locator("#launchConfirmModal")).toBeHidden();
  });

  test("campaign workflow supports step navigation, filtering, selection, and pagination", async ({ page }) => {
    await openPage(page, "campaigns");

    await page.getByRole("button", { name: "Create Campaign" }).click();
    await expect(page.locator("#campaignCreate")).toHaveClass(/active-card/);
    await expect(page.locator("#csvFile")).toBeVisible();
    await expect(page.locator("#validReady")).toContainText("valid emails ready");
    await expect(page.locator("#campaignContinueBtn")).toBeVisible();
    await expect(page.locator("#queueBtn")).toBeHidden();

    await page.locator('[data-workflow-step="2"]').click();
    await expect(page.locator('[data-workflow-panel="2"]')).toHaveClass(/active/);
    await expect(page.locator("#subjectStep")).toBeVisible();

    await page.locator('[data-workflow-step="3"]').click();
    await expect(page.locator('[data-workflow-panel="3"]')).toHaveClass(/active/);
    await expect(page.locator("#intervalStep")).toBeVisible();

    await page.locator('[data-workflow-step="4"]').click();
    await expect(page.getByRole("heading", { name: "Recipients", exact: true })).toBeVisible();
    await expect(page.locator("#campaignContinueBtn")).toBeHidden();
    await expect(page.locator("#queueBtn")).toBeVisible();
    await expect(page.locator("#previewRows tr").first()).toBeVisible();
    await expect(page.getByLabel("Include already contacted")).toBeVisible();

    const beforeMeta = await page.locator("#recipientsMeta").textContent();
    await page.getByLabel("Include already contacted").check();
    await expect(page.locator("#recipientsMeta")).not.toHaveText(beforeMeta || "");

    await page.getByLabel("Select all sendable").check();
    await expect(page.locator("#selectionStatus")).not.toContainText("0 of");
    await expect(page.locator("#queueBtn")).toBeEnabled();

    await page.locator("#contactsPageSize").selectOption("10");
    await expect(page.locator("#contactsPageLabel")).toContainText("/");
    await expect(page.locator("#contactsPageInfo")).toContainText("Showing");
  });

  test("review contacts defaults to not-contacted first and supports sort changes", async ({ page }) => {
    await page.route("**/api/preview", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          summary: {
            total: 3,
            sendable: 3,
            invalid: 0,
            already_contacted: 1,
            duplicates: 0,
            suppressed: 0,
            age_filtered: 0,
            company_filtered: 0,
          },
          rows: [
            {
              row_index: 2,
              email: "old@gmail.com",
              email_norm: "old@gmail.com",
              first_name: "Old",
              last_name: "Contact",
              subject: "Hi Old",
              body: "Hello Old",
              missing_variables: [],
              already_contacted: true,
              suppressed: false,
              duplicate_in_csv: false,
              errors: [],
              sendable: true,
              row_data: { first_name: "Old", state: "TX", age: "44" },
            },
            {
              row_index: 3,
              email: "fresh@gmail.com",
              email_norm: "fresh@gmail.com",
              first_name: "Fresh",
              last_name: "Contact",
              subject: "Hi Fresh",
              body: "Hello Fresh",
              missing_variables: [],
              already_contacted: false,
              suppressed: false,
              duplicate_in_csv: false,
              errors: [],
              sendable: true,
              row_data: { first_name: "Fresh", state: "TX", age: "25" },
            },
            {
              row_index: 4,
              email: "fresh.two@gmail.com",
              email_norm: "fresh.two@gmail.com",
              first_name: "Fresh",
              last_name: "Two",
              subject: "Hi Fresh",
              body: "Hello Fresh",
              missing_variables: [],
              already_contacted: false,
              suppressed: false,
              duplicate_in_csv: false,
              errors: [],
              sendable: true,
              row_data: { first_name: "Fresh", state: "TX", age: "35" },
            },
          ],
        }),
      });
    });

    await openPage(page, "campaigns");
    await page.getByRole("button", { name: "Create Campaign" }).click();
    await page.locator('[data-workflow-step="4"]').click();

    await expect(page.locator("#contactSortOrder")).toHaveValue("fresh_first");
    await expect(page.locator("#previewRows tr").first()).toContainText("fresh@gmail.com");

    await page.locator("#contactSortOrder").selectOption("contacted_first");
    await expect(page.locator("#previewRows tr").first()).toContainText("old@gmail.com");

    await page.locator("#contactSortOrder").selectOption("age_low_first");
    await expect(page.locator("#previewRows tr").first()).toContainText("fresh@gmail.com");

    await page.locator("#contactSortOrder").selectOption("age_high_first");
    await expect(page.locator("#previewRows tr").first()).toContainText("old@gmail.com");

    await page.locator("#recipientAgeFilter").selectOption("25-34");
    await expect(page.locator("#ageMinStep")).toHaveValue("25");
    await expect(page.locator("#ageMaxStep")).toHaveValue("34");

    await page.locator("#recipientAgeMin").fill("28");
    await page.locator("#recipientAgeMax").fill("39");
    await page.locator("#recipientAgeMax").blur();
    await expect(page.locator("#recipientAgeFilter")).toHaveValue("custom");
    await expect(page.locator("#ageMinStep")).toHaveValue("28");
    await expect(page.locator("#ageMaxStep")).toHaveValue("39");
  });

  test("template editor updates preview and preserves attachment controls", async ({ page }) => {
    await openPage(page, "templates");
    await page.locator("#newTemplateBtn").click();

    const templateName = `Playwright Template ${Date.now()}`;
    await page.locator("#campaignName").fill(templateName);
    await page.locator("#subject").fill("Testing {{first_name}} from Playwright");
    await page.locator("#body").fill("Hi {{first_name}},\n\nThis is a browser smoke test for {{city}}.");
    await page.locator("#previewBtn").click();

    await expect(page.locator("#liveSubject")).toContainText("Testing");
    await expect(page.locator("#liveBody")).toContainText("browser smoke test");
    await expect(page.locator("#wordCount")).toContainText("words");
    await expect(page.locator("#attachmentUpload")).toHaveAttribute("multiple", "");
    await expect(page.getByLabel("Choose Files")).toBeVisible();
    await page.locator("#saveTemplateBtn").click();
    await expect(page.locator(".toast.success")).toContainText("Template saved");
    await expect(page.locator("#sideTemplateList")).toContainText(templateName);

    await page.locator("#deleteTemplateBtn").click();
    await expect(page.locator("#confirmModal")).toBeVisible();
    await page.locator("#confirmModalConfirmBtn").click();
    await expect(page.locator("#confirmModal")).toBeHidden();
    await expect(page.locator(".toast.success")).toContainText("Template deleted");
    await expect(page.locator("#sideTemplateList")).not.toContainText(templateName);
  });

  test("Gmail sync shows starting, pending, and finished toast states", async ({ page }) => {
    await page.route("**/api/replies/sync", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1200));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ synced: 2, skipped: 1, replies: [] }),
      });
    });

    await openPage(page, "replies");
    await page.locator("#syncRepliesBtn").click();
    await expect(page.locator("#syncRepliesBtn")).toBeDisabled();
    await expect(page.locator(".toast.info", { hasText: "Gmail sync starting" })).toBeVisible();
    await expect(page.locator(".toast.info", { hasText: "Gmail sync pending" })).toBeVisible();
    await expect(page.locator(".toast.success", { hasText: "Gmail sync finished" })).toBeVisible();
    await expect(page.locator(".toast.success", { hasText: "2 Gmail replies synced" })).toBeVisible();
    await expect(page.locator("#syncRepliesBtn")).toBeEnabled();
  });

  test("settings controls update schedule preview", async ({ page }) => {
    await openPage(page, "settings");

    await page.locator("#interval").fill("15");
    await page.locator("#intervalJitter").fill("3");
    await page.locator("#dailySendLimit").fill("12");
    await page.locator("#businessStart").fill("09:30");
    await page.locator("#businessEnd").fill("16:45");
    await page.locator("#timezone").fill("America/Chicago");

    await expect(page.locator("#businessStart")).toHaveValue("09:30");
    await expect(page.locator("#businessEnd")).toHaveValue("16:45");
    await expect(page.locator("#timezone")).toHaveValue("America/Chicago");
    await expect(page.locator("#businessStart")).toHaveCSS("min-width", "180px");
    await expect(page.locator("#timezone")).toHaveCSS("min-width", "220px");
  });

  test("launch confirm can submit through mocked job creation", async ({ page }) => {
    await page.route("**/api/jobs/playwright-mocked-job/queue", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [{ row_index: 2, email: "mock@example.com", status: "pending", verification_detail: "" }] }),
      });
    });
    await page.route("**/api/jobs", async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      const requestBody = route.request().postDataJSON();
      expect(requestBody.selected_row_indexes.length).toBeGreaterThan(0);
      expect(requestBody.override_contacted).toBe(true);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ job_id: "playwright-mocked-job", queued: requestBody.selected_row_indexes.length }),
      });
    });

    await openPage(page, "campaigns");
    await page.getByRole("button", { name: "Review Contacts" }).click();
    await page.getByLabel("Include already contacted").check();
    await page.getByLabel("Select all sendable").check();
    await page.locator("#queueBtn").click();

    await expect(page.locator("#launchConfirmModal")).toBeVisible();
    await page.locator("#confirmLaunchBtn").click();
    await expect(page.locator("#launchConfirmModal")).toBeHidden();
    await expect(page.locator(".toast.success")).toContainText("Campaign launched");
    await expect(page.locator('[data-card-panel="campaigns"][data-card-id="campaigns-activity"]')).toHaveClass(/active-card/);
    await expect(page.locator("#queueDetails")).toContainText("mock@example.com");
  });

  test("CSV upload validation errors use toast notifications instead of browser alerts", async ({ page }) => {
    await openPage(page, "campaigns");
    await page.getByRole("button", { name: "Create Campaign" }).click();
    await page.locator("#csvUpload").setInputFiles({
      name: "invalid-contacts.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("name,email\nAda,ada@example.com\n"),
    });
    await page.locator("#uploadCsvBtn").click();
    await expect(page.locator(".toast.error")).toContainText("CSV could not be loaded");
    await expect(page.locator(".toast.error .toast-progress span")).toBeVisible();
    await expect(page.locator(".toast.error")).toHaveAttribute("style", /--toast-duration: 7000ms/);
  });

  test("CSV upload refreshes dependent metrics, insights, and contact previews", async ({ page }) => {
    const runId = Date.now();
    const filename = `playwright-metrics-${runId}.csv`;
    const csv = [
      "first_name,last_name,email,phone,city,state,birth_date,age,gender",
      `Ada,Lovelace,ada.${runId}@gmail.com,555-0101,Austin,TX,2000-01-01,26,M`,
      `Grace,Hopper,grace.${runId}@outlook.com,555-0102,Arlington,VA,1990-01-01,36,M`,
      `Linus,Torvalds,linus.${runId}@yahoo.com,555-0103,Portland,OR,1985-01-01,41,M`,
    ].join("\n");

    await openPage(page, "campaigns");
    await page.getByRole("button", { name: "Create Campaign" }).click();
    await page.locator("#csvUpload").setInputFiles({
      name: filename,
      mimeType: "text/csv",
      buffer: Buffer.from(csv),
    });
    await expect(page.locator("#csvMeta")).toContainText(`Selected ${filename}`);
    await expect(page.locator("#csvFile")).toHaveValue("__pending_upload__");
    await expect(page.locator("#csvUploadLabel")).toContainText(filename);
    await page.locator("#uploadCsvBtn").click();

    await expect(page.locator(".toast.success")).toContainText("CSV imported");
    await expect(page.locator("#csvFile")).toHaveValue(/uploaded_csv\//);
    await expect(page.locator("#csvFile")).toContainText(`playwright-metrics-${runId}`);
    await expect(page.locator("#csvMeta")).toContainText(`playwright-metrics-${runId}`);
    await expect(page.locator("#csvMeta")).toContainText("3 contacts");
    await expect(page.locator("#summaryTotal")).toHaveText("3");
    await expect(page.locator("#metricTotal")).toHaveText("3");
    await expect(page.locator("#metricValid")).toHaveText("3");
    await expect(page.locator("#validReady")).toContainText("3 valid emails ready for campaign");
    await expect(page.locator("#topStates")).toContainText("TX");
    await expect(page.locator("#topStatesMirror")).toContainText("VA");
    await expect(page.locator("#recipientPreviewRows tr")).toHaveCount(3);

    await page.getByRole("button", { name: "Review Contacts" }).click();
    await expect(page.locator("#previewRows tr")).toHaveCount(3);
    await expect(page.locator("#selectionStatus")).toContainText("3 of 3 selected");
    await expect(page.locator("#queueBtn")).toBeEnabled();

    await page.reload();
    await openPage(page, "campaigns");
    await expect(page.locator("#csvFile")).toHaveValue(/uploaded_csv\//);
    await expect(page.locator("#csvFile")).toContainText(`playwright-metrics-${runId}`);
    await expect(page.locator("#csvMeta")).toContainText(`playwright-metrics-${runId}`);
    cleanupUploadedCsv(filename);
  });

  test("manual recipients can drive preview without using CSV contacts", async ({ page }) => {
    await openPage(page, "campaigns");
    await page.getByRole("button", { name: "Create Campaign" }).click();

    await page.locator("#manualRecipients").fill("Ada Lovelace <ada.manual@gmail.com>\ngrace.hopper@gmail.com");
    await expect(page.locator("#manualOnlyRecipients")).toBeChecked();
    await page.locator("#manualPreviewBtn").click();
    await expect(page.locator(".toast.success")).toContainText("Manual recipients applied");
    await expect(page.locator("#csvStatus")).toContainText("Manual recipients");
    await expect(page.locator("#validReady")).toContainText("2 valid emails ready for campaign");
    await expect(page.locator("#campaignContinueBtn")).toBeHidden();
    await expect(page.locator("#queueBtn")).toBeVisible();

    await page.locator('[data-workflow-step="4"]').click();
    await expect(page.locator("#previewRows")).toContainText("ada.manual@gmail.com");
    await expect(page.locator("#previewRows")).toContainText("grace.hopper@gmail.com");
    await expect(page.locator("#selectionStatus")).toContainText("2 of 2 selected");
  });

  test("reply filter tabs filter unread, replied, starred, and archived views", async ({ page }) => {
    await page.route("**/api/replies**", async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          replies: [
            {
              id: 101,
              from_email: "fresh.reply@gmail.com",
              subject: "Fresh reply",
              body: "Unread reply body.",
              received_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              campaign_name: "sample",
            },
            {
              id: 102,
              from_email: "done.reply@gmail.com",
              subject: "Handled reply",
              body: "Already responded.",
              response_body: "Thanks",
              responded_at: new Date().toISOString(),
              received_at: new Date(Date.now() - 3600000).toISOString(),
              updated_at: new Date(Date.now() - 3600000).toISOString(),
              campaign_name: "sample",
            },
          ],
        }),
      });
    });

    await openPage(page, "replies");
    await expect(page.locator('[data-reply-filter="all"] span')).toHaveText("2");
    await page.locator('[data-reply-filter="unread"]').click();
    await expect(page.locator("#replyThreads")).toContainText("fresh.reply@gmail.com");
    await expect(page.locator("#replyThreads")).not.toContainText("done.reply@gmail.com");
    await page.locator('[data-reply-filter="replied"]').click();
    await expect(page.locator("#replyThreads")).toContainText("done.reply@gmail.com");
    await page.locator("#starReplyBtn").click();
    await page.locator('[data-reply-filter="starred"]').click();
    await expect(page.locator("#replyThreads")).toContainText("done.reply@gmail.com");
    await page.locator("#archiveReplyBtn").click();
    await expect(page.locator('[data-reply-filter="archived"] span')).toHaveText("1");
  });

  test("CSV import allows missing age columns and exposes age range rules", async ({ page }) => {
    const runId = Date.now();
    const filename = `playwright-no-age-${runId}.csv`;
    const csv = [
      "first_name,last_name,email,phone,city,state,gender",
      `No,Age,no-age-${runId}@gmail.com,555-0111,Austin,TX,M`,
    ].join("\n");

    await openPage(page, "campaigns");
    await page.getByRole("button", { name: "Create Campaign" }).click();
    await page.locator("#csvUpload").setInputFiles({
      name: filename,
      mimeType: "text/csv",
      buffer: Buffer.from(csv),
    });
    await page.locator("#uploadCsvBtn").click();

    await expect(page.locator(".toast.success")).toContainText("CSV imported");
    await expect(page.locator("#summaryTotal")).toHaveText("1");
    await expect(page.locator("#metricValid")).toHaveText("1");

    await page.locator('[data-workflow-step="3"]').click();
    await expect(page.locator('[data-workflow-panel="3"]')).toHaveClass(/active/);
    await expect(page.getByRole("heading", { name: "Audience Range" })).toBeVisible();
    await expect(page.locator("#ageMinStep")).toHaveValue("18");
    await expect(page.locator("#ageMaxStep")).toHaveValue("44");

    await page.locator('[data-workflow-step="4"]').click();
    await expect(page.locator("#previewRows tr")).toHaveCount(1);
    await expect(page.locator("#previewRows")).toContainText("sendable");
    await expect(page.locator("#previewRows")).not.toContainText("missing_age");
    cleanupUploadedCsv(filename);
  });

  test("company email filter excludes custom-domain addresses until disabled", async ({ page }) => {
    const runId = Date.now();
    const filename = `playwright-company-filter-${runId}.csv`;
    const csv = [
      "first_name,last_name,email,phone,city,state,age,gender",
      `Personal,Person,personal-${runId}@gmail.com,555-0111,Austin,TX,32,M`,
      `Company,Person,admin-${runId}@alayacare.com,555-0112,Austin,TX,32,M`,
    ].join("\n");

    await openPage(page, "campaigns");
    await page.getByRole("button", { name: "Create Campaign" }).click();
    await page.locator("#csvUpload").setInputFiles({
      name: filename,
      mimeType: "text/csv",
      buffer: Buffer.from(csv),
    });
    await page.locator("#uploadCsvBtn").click();

    await expect(page.locator(".toast.success")).toContainText("CSV imported");
    await page.getByRole("button", { name: "Review Contacts" }).click();
    await expect(page.locator("#previewRows")).toContainText("company email");
    await expect(page.locator("#selectionStatus")).toContainText("1 of 1 selected");

    await page.locator("#excludeCompanyEmails").uncheck();
    await expect(page.locator("#previewRows")).not.toContainText("company email");
    await expect(page.locator("#selectionStatus")).toContainText("2 of 2 selected");
    cleanupUploadedCsv(filename);
  });

  test("gender filter defaults to male only and can show all genders", async ({ page }) => {
    const runId = Date.now();
    const filename = `playwright-gender-filter-${runId}.csv`;
    const csv = [
      "first_name,last_name,email,phone,city,state,age,gender",
      `Male,Person,male-${runId}@gmail.com,555-0111,Austin,TX,32,M`,
      `Female,Person,female-${runId}@gmail.com,555-0112,Austin,TX,32,F`,
    ].join("\n");

    await openPage(page, "campaigns");
    await page.getByRole("button", { name: "Create Campaign" }).click();
    await page.locator("#csvUpload").setInputFiles({
      name: filename,
      mimeType: "text/csv",
      buffer: Buffer.from(csv),
    });
    await page.locator("#uploadCsvBtn").click();

    await expect(page.locator(".toast.success")).toContainText("CSV imported");
    await page.getByRole("button", { name: "Review Contacts" }).click();
    await expect(page.locator("#genderFilter")).toHaveValue("male");
    await expect(page.locator("#previewRows")).toContainText("gender filtered");
    await expect(page.locator("#selectionStatus")).toContainText("1 of 1 selected");

    await page.locator("#genderFilter").selectOption("all");
    await expect(page.locator("#previewRows")).not.toContainText("gender filtered");
    await expect(page.locator("#selectionStatus")).toContainText("2 of 2 selected");
    cleanupUploadedCsv(filename);
  });
});
