const state = {
  preview: null,
  selectedRows: new Set(),
  selectedCsv: localStorage.getItem("selectedCsv") || "",
  pendingCsvFileName: "",
  jobs: [],
  auth: null,
  attachments: [],
  statusSummary: null,
  theme: localStorage.getItem("theme") || "light",
  jobsPage: 1,
  jobsPageSize: 5,
  contactsPage: 1,
  contactsPageSize: 5,
  contactSortOrder: "fresh_first",
  campaignStep: 1,
  campaignPanelTouched: false,
  replies: [],
  selectedReplyIndex: 0,
  replyFilter: "all",
  replyFlags: JSON.parse(localStorage.getItem("replyFlags") || "{}"),
  templates: [],
  selectedTemplateId: null,
  rotationTemplateIds: new Set(),
};

const $ = (id) => document.getElementById(id);

const ICONS = {
  activity: '<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/>',
  archive: '<rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/><path d="M10 12h4"/>',
  arrowRight: '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
  bell: '<path d="M10.27 21a2 2 0 0 0 3.46 0"/><path d="M3.26 15.33A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.67C19.41 13.86 18 12.5 18 8a6 6 0 0 0-12 0c0 4.5-1.41 5.86-2.74 7.33"/>',
  calendar: '<path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/>',
  chart: '<path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  chevronDown: '<path d="m6 9 6 6 6-6"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  eye: '<path d="M2.06 12.35a1 1 0 0 1 0-.7C3.6 7.5 7.5 5 12 5s8.4 2.5 9.94 6.65a1 1 0 0 1 0 .7C20.4 16.5 16.5 19 12 19s-8.4-2.5-9.94-6.65"/><circle cx="12" cy="12" r="3"/>',
  fileText: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
  filter: '<path d="M22 3H2l8 9.46V19l4 2v-8.54z"/>',
  home: '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2h-4v-7H9v7H5a2 2 0 0 1-2-2z"/>',
  inbox: '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
  mail: '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a2 2 0 0 1-2.06 0L2 7"/>',
  message: '<path d="M21 15a4 4 0 0 1-4 4H7l-4 4V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/>',
  moon: '<path d="M12 3a6 6 0 0 0 9 7.5A9 9 0 1 1 12 3Z"/>',
  more: '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
  paperclip: '<path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 1 1-2.83-2.83l8.49-8.48"/>',
  pause: '<rect width="4" height="16" x="6" y="4"/><rect width="4" height="16" x="14" y="4"/>',
  play: '<polygon points="6 3 20 12 6 21 6 3"/>',
  plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
  reply: '<polyline points="9 17 4 12 9 7"/><path d="M20 18v-2a4 4 0 0 0-4-4H4"/>',
  rotateCcw: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  send: '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
  settings: '<path d="M9.67 2h4.66l.84 2.1 2.25.93 2.08-.9 2.33 4.04-1.67 1.35v2.96l1.67 1.35-2.33 4.04-2.08-.9-2.25.93-.84 2.1H9.67l-.84-2.1-2.25-.93-2.08.9-2.33-4.04 1.67-1.35V9.52L2.17 8.17 4.5 4.13l2.08.9 2.25-.93z"/><circle cx="12" cy="12" r="3"/>',
  shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.68 0C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.5 3.8 17 5 19 5a1 1 0 0 1 1 1z"/>',
  star: '<path d="m12 2 3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
  trash: '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/>',
  triangleAlert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  upload: '<path d="M12 3v12"/><path d="m17 8-5-5-5 5"/><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>',
  user: '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  arrowDownUp: '<path d="m3 16 4 4 4-4"/><path d="M7 20V4"/><path d="m21 8-4-4-4 4"/><path d="M17 4v16"/>',
  ban: '<circle cx="12" cy="12" r="10"/><path d="m4.9 4.9 14.2 14.2"/>',
};

function initIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((element) => {
    const name = element.dataset.icon;
    if (!ICONS[name]) return;
    element.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;
  });
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) throw new Error(readableMessage(await response.text()));
  return response.json();
}

function payload() {
  const sendLimitValue = fieldValue("sendLimitStep", "sendLimit");
  const sendLimit = sendLimitValue ? Number(sendLimitValue) : null;
  const manualEntries = manualRecipientEntries();
  const manualOnly = $("manualOnlyRecipients").checked && manualEntries.length > 0;
  const recipientAgeRange = $("recipientAgeFilter")?.value || "";
  let ageMin = nullableNumber(fieldValue("ageMinStep", "ageMin"));
  let ageMax = nullableNumber(fieldValue("ageMaxStep", "ageMax"));
  if (recipientAgeRange === "all") {
    ageMin = null;
    ageMax = null;
  } else if (recipientAgeRange === "custom") {
    ageMin = nullableNumber($("recipientAgeMin")?.value);
    ageMax = nullableNumber($("recipientAgeMax")?.value);
  } else if (recipientAgeRange.includes("-")) {
    const [min, max] = recipientAgeRange.split("-").map((value) => Number(value));
    ageMin = min;
    ageMax = max;
  }
  return {
    campaign_name: fieldValue("campaignNameStep", "campaignName") || "Untitled Campaign",
    attachment_ids: state.attachments.map((file) => file.id),
    csv_file: manualOnly ? null : ($("csvFile").value || null),
    manual_recipients: manualEntries,
    manual_only: manualOnly,
    subject: fieldValue("subjectStep", "subject"),
    body: fieldValue("bodyStep", "body"),
    template_ids: rotationActive() ? [...state.rotationTemplateIds] : [],
    content_type: "Text",
    override_contacted: $("overrideContacted").checked || fieldChecked("overrideContactedStep", "overrideContacted"),
    exclude_company_emails: fieldChecked("excludeCompanyEmailsStep", "excludeCompanyEmails"),
    gender_filter: $("genderFilter").value,
    age_min: ageMin,
    age_max: ageMax,
    selected_row_indexes: Array.from(state.selectedRows),
    send_limit: sendLimit,
    interval_minutes: Number(fieldValue("intervalStep", "interval") || 10),
    interval_jitter_minutes: Number(fieldValue("intervalJitterStep", "intervalJitter") || 0),
    daily_send_limit: Number(fieldValue("dailySendLimitStep", "dailySendLimit") || 25),
    max_failures: Number(fieldValue("maxFailuresStep", "maxFailures") || 3),
    auto_pause_on_failure: fieldChecked("autoPauseOnFailureStep", "autoPauseOnFailure"),
    business_start: fieldValue("businessStartStep", "businessStart"),
    business_end: fieldValue("businessEndStep", "businessEnd"),
    timezone: fieldValue("timezoneStep", "timezone"),
  };
}

function manualRecipientEntries() {
  return ($("manualRecipients")?.value || "")
    .split(/\r?\n|;/)
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function isManualOnlyMode() {
  return $("manualOnlyRecipients")?.checked && manualRecipientEntries().length > 0;
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function readableMessage(value) {
  const text = String(value?.message || value || "").trim();
  if (!text) return "Something went wrong.";
  try {
    const parsed = JSON.parse(text);
    if (parsed.detail) return typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail);
    if (parsed.message) return parsed.message;
  } catch {
    // Plain text errors are already readable.
  }
  return text;
}

function showToast(message, tone = "info", title = null) {
  const region = $("toastRegion");
  const toast = document.createElement("div");
  const normalizedTone = ["success", "error", "warning", "info"].includes(tone) ? tone : "info";
  const icon = normalizedTone === "success" ? "check" : normalizedTone === "error" ? "triangleAlert" : normalizedTone === "warning" ? "triangleAlert" : "message";
  const heading = title || (normalizedTone === "success" ? "Success" : normalizedTone === "error" ? "Action needed" : normalizedTone === "warning" ? "Check this" : "Notice");
  const timeoutMs = normalizedTone === "error" ? 7000 : 4200;
  toast.className = `toast ${normalizedTone}`;
  toast.style.setProperty("--toast-duration", `${timeoutMs}ms`);
  toast.innerHTML = `
    <div class="toast-icon" data-icon="${icon}"></div>
    <div><strong>${escapeHtml(heading)}</strong><span>${escapeHtml(readableMessage(message))}</span></div>
    <button type="button" aria-label="Dismiss notification">×</button>
    <div class="toast-progress" aria-hidden="true"><span></span></div>
  `;
  region.appendChild(toast);
  initIcons(toast);
  const close = () => toast.remove();
  toast.querySelector("button").addEventListener("click", close);
  window.setTimeout(close, timeoutMs);
}

function applyTheme(theme = state.theme) {
  state.theme = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = state.theme;
  document.body.dataset.theme = state.theme;
  localStorage.setItem("theme", state.theme);
  const icon = $("themeToggleIcon");
  if (icon) {
    icon.dataset.icon = state.theme === "dark" ? "moon" : "sun";
    initIcons(icon.parentElement);
  }
  if ($("themeToggleBtn")) {
    $("themeToggleBtn").setAttribute("aria-pressed", String(state.theme === "dark"));
    $("themeToggleBtn").setAttribute(
      "title",
      state.theme === "dark" ? "Switch to daylight theme" : "Switch to dark theme",
    );
  }
  document.querySelectorAll('input[name="themePreference"]').forEach((input) => {
    input.checked = input.value === state.theme;
  });
}

function notificationItems() {
  const queued = state.jobs.reduce((sum, job) => sum + (job.counts?.pending || 0) + (job.counts?.sending || 0), 0);
  const failed = state.jobs.reduce((sum, job) => sum + (job.counts?.failed || 0), 0);
  const running = state.jobs.filter((job) => job.status === "running").length;
  const replies = state.replies.length;
  const sendable = state.preview?.summary?.sendable || 0;
  const items = [];
  if (!state.auth?.configured) {
    items.push({ tone: "warn", title: "Gmail is not configured", detail: "Set SMTP/Gmail credentials before sending.", target: "settings" });
  }
  if (state.auth?.configured && state.auth?.deliverability && !state.auth.deliverability.public_unsubscribe_links) {
    items.push({ tone: "warn", title: "Unsubscribe links are local", detail: "Set APP_BASE_URL to a public HTTPS URL before real campaigns.", target: "settings" });
  }
  if (failed) {
    items.push({ tone: "bad", title: `${failed} failed email${failed === 1 ? "" : "s"}`, detail: "Review campaign activity for delivery errors.", target: "campaigns" });
  }
  if (queued) {
    items.push({ tone: "info", title: `${queued} email${queued === 1 ? "" : "s"} pending`, detail: "Scheduled queue is waiting inside campaign rules.", target: "campaigns" });
  }
  if (running) {
    items.push({ tone: "ok", title: `${running} campaign${running === 1 ? "" : "s"} running`, detail: "Campaign scheduler is active.", target: "campaigns" });
  }
  if (replies) {
    items.push({ tone: "info", title: `${replies} synced repl${replies === 1 ? "y" : "ies"}`, detail: "Open Replies to review and respond.", target: "replies" });
  }
  if (!sendable) {
    items.push({ tone: "warn", title: "No ready recipients", detail: "Import CSV contacts or add manual recipients.", target: "campaigns" });
  }
  return items.length ? items : [{ tone: "ok", title: "All clear", detail: "No campaign issues need attention right now.", target: "dashboard" }];
}

function renderNotifications() {
  if (!$("notificationList")) return;
  const items = notificationItems();
  const actionableCount = items.filter((item) => item.tone !== "ok" || item.target !== "dashboard").length;
  $("notificationBadge").textContent = Math.min(actionableCount, 99);
  $("notificationBadge").classList.toggle("hidden", actionableCount === 0);
  $("notificationList").innerHTML = items.map((item) => `<button type="button" class="notification-item ${escapeHtml(item.tone)}" data-notify-target="${escapeHtml(item.target)}">
    <span data-icon="${item.tone === "bad" ? "triangleAlert" : item.tone === "warn" ? "triangleAlert" : item.tone === "ok" ? "check" : "bell"}"></span>
    <span><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.detail)}</small></span>
  </button>`).join("");
  initIcons($("notificationList"));
}

function setNotificationPanel(open) {
  $("notificationPanel").hidden = !open;
  $("notificationBtn").setAttribute("aria-expanded", String(open));
  if (open) renderNotifications();
}

function fieldValue(campaignId, fallbackId) {
  return $(campaignId)?.value ?? $(fallbackId).value;
}

function fieldChecked(campaignId, fallbackId) {
  return $(campaignId)?.checked ?? $(fallbackId).checked;
}

function nullableNumber(value) {
  return value === null || value === undefined || String(value).trim() === "" ? null : Number(value);
}

function renderTemplate(text, rowData = {}) {
  return String(text || "").replace(/\{\{\s*([A-Za-z0-9_]+)\s*\}\}/g, (_, key) => rowData[key] || `{{${key}}}`);
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}

function formatRelativeTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  const seconds = Math.max(0, Math.round((Date.now() - date.valueOf()) / 1000));
  if (seconds < 60) return "now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? "Yesterday" : `${days}d ago`;
}

function formatBytes(size) {
  if (!size) return "0 B";
  const units = ["B", "KB", "MB"];
  let value = Number(size);
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function previewText(value, maxLength = 96) {
  const compact = String(value || "").replace(/\s+/g, " ").trim();
  return compact.length > maxLength ? `${compact.slice(0, maxLength - 1)}...` : compact;
}

function errorLabel(error) {
  const labels = {
    invalid_email: "invalid email",
    under_18: "under 18",
    missing_template_value: "missing template value",
    duplicate_in_csv: "duplicate",
    already_contacted: "already contacted",
    outside_age_range: "outside age range",
    company_email: "company email",
    gender_filtered: "gender filtered",
  };
  return labels[error] || String(error || "").replaceAll("_", " ");
}

function sendableRows() {
  return state.preview ? state.preview.rows.filter((row) => row.sendable) : [];
}

function sortedPreviewRows() {
  const rows = [...(state.preview?.rows || [])];
  const sortOrder = $("contactSortOrder")?.value || state.contactSortOrder || "fresh_first";
  const byRow = (a, b) => a.row_index - b.row_index;
  const ageValue = (row) => {
    const age = Number(row.row_data?.age ?? row.age ?? NaN);
    return Number.isFinite(age) ? age : null;
  };
  const byAge = (direction) => (a, b) => {
    const ageA = ageValue(a);
    const ageB = ageValue(b);
    if (ageA === null && ageB === null) return byRow(a, b);
    if (ageA === null) return 1;
    if (ageB === null) return -1;
    return direction * (ageA - ageB) || byRow(a, b);
  };
  if (sortOrder === "row_order") return rows.sort(byRow);
  if (sortOrder === "age_low_first") return rows.sort(byAge(1));
  if (sortOrder === "age_high_first") return rows.sort(byAge(-1));
  if (sortOrder === "contacted_first") {
    return rows.sort((a, b) => Number(b.already_contacted) - Number(a.already_contacted) || byRow(a, b));
  }
  if (sortOrder === "sendable_first") {
    return rows.sort((a, b) => Number(b.sendable) - Number(a.sendable) || Number(a.already_contacted) - Number(b.already_contacted) || byRow(a, b));
  }
  return rows.sort((a, b) => Number(a.already_contacted) - Number(b.already_contacted) || Number(b.sendable) - Number(a.sendable) || byRow(a, b));
}

function showPage(pageId) {
  const validPage = document.getElementById(pageId) ? pageId : "dashboard";
  document.querySelectorAll(".page").forEach((page) => page.classList.toggle("active", page.id === validPage));
  document.body.classList.toggle("login-mode", validPage === "login");
  document.querySelectorAll("[data-page-link]").forEach((link) => {
    link.classList.toggle("active", link.dataset.pageLink === validPage);
  });
  document.querySelector(".template-nav-group")?.classList.toggle("open", validPage === "templates");
  window.location.hash = validPage;
  if (validPage === "campaigns") {
    state.campaignPanelTouched = false;
    showDefaultCampaignPanel();
  }
}

function showCardPanel(group, target) {
  if (group === "campaigns" && target === "campaigns-review") {
    document.querySelectorAll(`[data-card-panel="campaigns"]`).forEach((panel) => {
      panel.classList.toggle("active-card", panel.dataset.cardId === "campaigns-create");
    });
    document.querySelectorAll(`[data-card-tab="campaigns"]`).forEach((button) => {
      button.classList.toggle("active", button.dataset.cardTarget === "campaigns-review");
    });
    showWorkflowStep(4);
    if (state.preview?.rows?.length) {
      renderPreviewTable();
      renderRecipientPreview();
    }
    refreshPreview().catch((error) => showToast(error, "error", "Preview failed"));
    return;
  }
  document.querySelectorAll(`[data-card-panel="${group}"]`).forEach((panel) => {
    panel.classList.toggle("active-card", panel.dataset.cardId === target);
  });
  document.querySelectorAll(`[data-card-tab="${group}"]`).forEach((button) => {
    button.classList.toggle("active", button.dataset.cardTarget === target);
  });
  if (group === "campaigns" && target === "campaigns-create") showWorkflowStep(1);
}

function hasRunningCampaign() {
  return state.jobs.some((job) => job.status === "running");
}

function showDefaultCampaignPanel() {
  showCardPanel("campaigns", "campaigns-activity");
}

function showWorkflowStep(step) {
  state.campaignStep = Math.min(4, Math.max(1, Number(step) || 1));
  document.querySelectorAll("[data-workflow-panel]").forEach((panel) => {
    panel.classList.toggle("active", Number(panel.dataset.workflowPanel) === state.campaignStep);
  });
  document.querySelectorAll("[data-workflow-step]").forEach((button) => {
    const buttonStep = Number(button.dataset.workflowStep);
    button.classList.toggle("active", buttonStep === state.campaignStep);
    button.classList.toggle("complete", buttonStep < state.campaignStep);
  });
  $("campaignBackBtn").disabled = state.campaignStep === 1;
  const hints = {
    1: "Upload or select a CSV file to start the campaign.",
    2: "Compose the campaign template and preview the personalized email.",
    3: "Set safe sending rules before reviewing recipients.",
    4: "Review selected recipients and launch when ready.",
  };
  $("workflowHint").textContent = hints[state.campaignStep];
  renderCampaignLiveEmail();
  renderSchedulePreview();
  updateCampaignFooter();
}

async function loadAuth() {
  state.auth = await api("/api/auth/status");
  $("loginBtn").innerHTML = state.auth.configured
    ? `<strong>${escapeHtml(state.auth.account)}</strong><span>Gmail connected</span>`
    : "<strong>Gmail not configured</strong><span>Set .env credentials</span>";
  $("metricHealth").textContent = state.auth.configured ? "Safe" : "Setup";
  $("metricHealthDetail").textContent = state.auth.configured
    ? `${$("dailySendLimit").value || 25}/day configured`
    : "Gmail credentials needed";
  document.querySelectorAll(".settings-gmail").forEach((button) => {
    button.innerHTML = $("loginBtn").innerHTML;
  });
  renderNotifications();
}

async function loadCsvFiles() {
  const { files } = await api("/api/csv-files");
  $("csvFile").innerHTML = files
    .map((file) => `<option value="${escapeHtml(file.name)}" ${file.default ? "selected" : ""}>${escapeHtml(file.display_name || file.name)}</option>`)
    .join("");
  if (!files.length) {
    $("csvMeta").textContent = "No CSV contact files found";
    resetCsvDependentUi("No CSV contact files found");
    $("csvFile").innerHTML = "";
    return;
  }
  if (state.selectedCsv && files.some((file) => file.name === state.selectedCsv)) {
    $("csvFile").value = state.selectedCsv;
  } else {
    state.selectedCsv = $("csvFile").value;
    localStorage.setItem("selectedCsv", state.selectedCsv);
  }
  // A preview failure must not block loading replies.
  try {
    await refreshPreview();
  } catch (error) {
    showToast(error, "error", "Preview failed");
  }
  await loadReplies();
}

function showPendingCsvSelection(file) {
  state.pendingCsvFileName = file.name;
  resetPreview();
  $("csvFile").innerHTML = `<option value="__pending_upload__" selected>${escapeHtml(file.name)}</option>${$("csvFile").innerHTML}`;
  $("csvFile").value = "__pending_upload__";
  $("csvUploadLabel").textContent = file.name;
  $("csvMeta").textContent = `Selected ${file.name}. Click Replace File to import it.`;
  $("csvStatus").textContent = "CSV selected";
  $("uploadStatus").textContent = "Ready to import";
  $("validReady").textContent = "Import this CSV to preview contacts";
  $("queueBtn").disabled = true;
}

function updateManualRecipientsStatus() {
  const count = manualRecipientEntries().length;
  $("manualRecipientsMeta").textContent = count
    ? `${count} manual recipient${count === 1 ? "" : "s"} ready to preview.`
    : "Type email addresses without importing CSV.";
  $("manualRecipientsStatus").textContent = count
    ? `${count} manual recipient${count === 1 ? "" : "s"} entered`
    : "";
  updateCampaignFooter();
}

function renderMetrics() {
  const summary = state.preview?.summary || {};
  const queued = state.jobs.reduce((sum, job) => sum + (job.counts?.pending || 0) + (job.counts?.sending || 0), 0);
  const failed = state.jobs.reduce((sum, job) => sum + (job.counts?.failed || 0), 0);
  const sent = state.jobs.reduce((sum, job) => sum + (job.counts?.sent || 0), 0);
  const dailyLimit = Number(fieldValue("dailySendLimitStep", "dailySendLimit") || 25);
  const dailyPercent = Math.min(100, Math.round((sent / Math.max(1, dailyLimit)) * 100));
  $("metricTotal").textContent = summary.total || 0;
  $("metricValid").textContent = summary.sendable || 0;
  $("metricQueued").textContent = queued;
  $("metricSentToday").textContent = sent;
  $("metricFailed").textContent = failed;
  $("summaryTotal").textContent = summary.total || 0;
  $("summaryDuplicates").textContent = summary.duplicates || 0;
  $("summaryInvalid").textContent = summary.invalid || 0;
  $("summarySuppressed").textContent = summary.suppressed || 0;
  $("summaryCompanyFiltered").textContent = summary.company_filtered || 0;
  $("summaryGenderFiltered").textContent = summary.gender_filtered || 0;
  $("summaryTotalMirror").textContent = summary.total || 0;
  $("summaryValidMirror").textContent = summary.sendable || 0;
  $("summaryInvalidMirror").textContent = summary.invalid || 0;
  $("summarySuppressedMirror").textContent = summary.suppressed || 0;
  $("summaryCompanyFilteredMirror").textContent = summary.company_filtered || 0;
  $("summaryGenderFilteredMirror").textContent = summary.gender_filtered || 0;
  $("dashboardContactDelta").textContent = `${summary.sendable || 0} ready`;
  $("metricSentTodayMirror").textContent = sent;
  $("dailyLimitBar").style.width = `${dailyPercent}%`;
  $("metricHealthDetail").textContent = `${fieldValue("dailySendLimitStep", "dailySendLimit") || dailyLimit}/day configured`;
  $("validReady").textContent = `${summary.sendable || 0} valid emails ready for campaign`;
  $("launchStatus").textContent = `Ready to send to ${state.selectedRows.size} recipients`;
  renderNotifications();
}

function renderAttachments() {
  $("attachmentList").innerHTML = state.attachments.length ? state.attachments.map((file) => `
    <div class="attachment-item">
      <span>${escapeHtml(file.name)}</span>
      <small>${formatBytes(file.size)}</small>
      <button type="button" data-action="remove-attachment" data-id="${escapeHtml(file.id)}" aria-label="Remove attachment">×</button>
    </div>
  `).join("") : '<p>No files attached.</p>';
  $("attachmentStatus").textContent = state.attachments.length
    ? `${state.attachments.length} file${state.attachments.length === 1 ? "" : "s"} will be attached`
    : "";
}

function renderTemplateList() {
  renderSidebarTemplateList();
}

function renderSidebarTemplateList() {
  if (!$("sideTemplateList")) return;
  const query = ($("sideTemplateSearch")?.value || "").toLowerCase().trim();
  const templates = state.templates.filter((template) => !query || template.name.toLowerCase().includes(query));
  $("sideTemplateList").innerHTML = templates.length ? templates.map((template) => `
    <button class="template-item ${template.id === state.selectedTemplateId ? "active" : ""}" type="button" data-template-id="${escapeHtml(template.id)}">
      <strong>${escapeHtml(template.name)}</strong>
      <span>${escapeHtml(formatDate(template.updated_at))}</span>
    </button>
  `).join("") : '<p class="empty-state">No saved templates yet.</p>';
}

function applyTemplate(template) {
  state.selectedTemplateId = template?.id || null;
  $("campaignName").value = template?.name || "Untitled Template";
  $("subject").value = template?.subject || "Hi {{first_name}}, let's collaborate!";
  $("body").value = template?.body || "";
  if ($("deleteTemplateBtn")) {
    $("deleteTemplateBtn").hidden = !state.selectedTemplateId;
  }
  renderLiveEmail();
  renderTemplateList();
}

async function deleteCurrentTemplate() {
  if (!state.selectedTemplateId) return;
  const template = state.templates.find((entry) => entry.id === state.selectedTemplateId);
  const confirmed = await confirmAction({
    title: "Delete template?",
    message: `"${template?.name || "This template"}" will be permanently removed. This cannot be undone.`,
    confirmLabel: "Delete Template",
  });
  if (!confirmed) return;
  await api(`/api/templates/${encodeURIComponent(state.selectedTemplateId)}`, { method: "DELETE" });
  state.selectedTemplateId = null;
  await loadTemplates();
  if (!state.templates.length) {
    applyTemplate({ id: null, name: "Untitled Template", subject: "Hi {{first_name}},", body: "Hi {{first_name}},\n\n" });
  }
  $("toastRegion").innerHTML = "";
  showToast("Template deleted.", "success", "Template deleted");
}

async function loadTemplates() {
  const { templates } = await api("/api/templates");
  state.templates = templates;
  const validIds = new Set(templates.map((template) => template.id));
  state.rotationTemplateIds = new Set([...state.rotationTemplateIds].filter((id) => validIds.has(id)));
  renderRotationTemplateList();
  if (state.selectedTemplateId) {
    const selected = state.templates.find((template) => template.id === state.selectedTemplateId);
    if (selected) applyTemplate(selected);
    else renderTemplateList();
  } else if (state.templates.length) {
    applyTemplate(state.templates[0]);
  } else {
    renderTemplateList();
  }
}

function rotationActive() {
  return state.rotationTemplateIds.size >= 2;
}

function rotationTemplates() {
  return state.templates.filter((template) => state.rotationTemplateIds.has(template.id));
}

function renderRotationTemplateList() {
  const container = $("rotationTemplateList");
  if (!container) return;
  container.innerHTML = state.templates.length ? state.templates.map((template) => `
    <label class="rotation-item">
      <input type="checkbox" data-rotation-id="${escapeHtml(template.id)}" ${state.rotationTemplateIds.has(template.id) ? "checked" : ""}>
      <span><strong>${escapeHtml(template.name)}</strong><small>${escapeHtml(template.subject)}</small></span>
    </label>
  `).join("") : '<p class="empty-state">No saved templates yet. Save templates from the Templates page first.</p>';
  updateRotationStatus();
}

function updateRotationStatus() {
  const status = $("rotationStatus");
  if (status) {
    status.textContent = rotationActive()
      ? `${state.rotationTemplateIds.size} templates rotating`
      : state.rotationTemplateIds.size === 1
        ? "Select at least 2 templates"
        : "Off";
  }
  renderCampaignLiveEmail();
}

async function saveCurrentTemplate() {
  const name = $("campaignName").value.trim();
  const subject = $("subject").value.trim();
  const body = $("body").value.trim();
  if (!name || !subject || !body) {
    showToast("Template name, subject, and message are required.", "warning");
    return;
  }
  const result = await api("/api/templates", {
    method: "POST",
    body: JSON.stringify({ id: state.selectedTemplateId, name, subject, body }),
  });
  state.selectedTemplateId = result.template.id;
  await loadTemplates();
  showToast(`${result.template.name} saved.`, "success", "Template saved");
}

function replyDisplayName(email) {
  const name = String(email || "").split("@")[0].replace(/[._-]+/g, " ").trim();
  return name ? name.replace(/\b\w/g, (letter) => letter.toUpperCase()) : "Unknown sender";
}

function replyMessageFor(contact) {
  if (contact?.body) return readableReplyBody(contact.body);
  const reason = contact?.reason || "reply";
  if (reason === "interested" || reason === "positive") {
    return `Hi Sujanesh,\n\nThanks for reaching out. I'm interested in learning more about the collaboration.\n\nRegards,\n${replyDisplayName(contact.email).split(" ")[0]}`;
  }
  if (reason === "follow_up") {
    return `Hi Sujanesh,\n\nI'm currently exploring new opportunities. Please send a few more details and we can find a time to talk.\n\nThanks,\n${replyDisplayName(contact.email).split(" ")[0]}`;
  }
  if (reason === "later") {
    return `Hi Sujanesh,\n\nThis sounds interesting, but the timing is not ideal right now. Please follow up later.\n\nBest,\n${replyDisplayName(contact.email).split(" ")[0]}`;
  }
  return `Hi Sujanesh,\n\nThanks for reaching out. I had a question about the opportunity and the expected collaboration details.\n\nRegards,\n${replyDisplayName(contact.email).split(" ")[0]}`;
}

function readableReplyBody(value) {
  const text = String(value || "");
  if (!/<!doctype|<html[\s>]|<body[\s>]|<style[\s>]|<p[\s>]|<br[\s/>]/i.test(text)) return text;
  const documentText = new DOMParser().parseFromString(text, "text/html").body?.textContent || text;
  return documentText
    .replace(/\u00a0/g, " ")
    .replace(/[ \t]+/g, " ")
    .replace(/\n\s+/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function replyKey(reply) {
  return String(reply?.id || reply?.message_id || reply?.from_email || "");
}

function replyFlag(reply, flag) {
  return Boolean(state.replyFlags[replyKey(reply)]?.[flag]);
}

function setReplyFlag(reply, flag, value) {
  const key = replyKey(reply);
  if (!key) return;
  state.replyFlags[key] = { ...(state.replyFlags[key] || {}), [flag]: value };
  localStorage.setItem("replyFlags", JSON.stringify(state.replyFlags));
}

function filteredReplies() {
  if (state.replyFilter === "unread") return state.replies.filter((reply) => !reply.responded_at && !replyFlag(reply, "archived"));
  if (state.replyFilter === "replied") return state.replies.filter((reply) => Boolean(reply.responded_at));
  if (state.replyFilter === "starred") return state.replies.filter((reply) => replyFlag(reply, "starred"));
  if (state.replyFilter === "archived") return state.replies.filter((reply) => replyFlag(reply, "archived"));
  return state.replies.filter((reply) => !replyFlag(reply, "archived"));
}

function renderReplyFilters() {
  const counts = {
    all: state.replies.filter((reply) => !replyFlag(reply, "archived")).length,
    unread: state.replies.filter((reply) => !reply.responded_at && !replyFlag(reply, "archived")).length,
    replied: state.replies.filter((reply) => Boolean(reply.responded_at)).length,
    starred: state.replies.filter((reply) => replyFlag(reply, "starred")).length,
    archived: state.replies.filter((reply) => replyFlag(reply, "archived")).length,
  };
  document.querySelectorAll("[data-reply-filter]").forEach((button) => {
    const filter = button.dataset.replyFilter;
    button.classList.toggle("active", filter === state.replyFilter);
    button.querySelector("span").textContent = counts[filter] || 0;
  });
}

function renderSelectedReply(replies = filteredReplies()) {
  const contact = replies[state.selectedReplyIndex];
  if (!contact) {
    $("replySender").textContent = "Gmail reply sync";
    $("replyMeta").textContent = "No Gmail inbox polling is connected yet.";
    $("replyMessage").textContent = "Connect Gmail reply polling to load actual inbound replies here. Until then, suppressions and unsubscribe events remain tracked locally.";
    $("replyDraft").value = "";
    $("starReplyBtn").classList.remove("active");
    $("archiveReplyBtn").classList.remove("active");
    return;
  }
  $("replySender").textContent = replyDisplayName(contact.email);
  $("replyMeta").textContent = `${contact.email} · ${contact.campaign_name || contact.reason || "reply"} · ${formatRelativeTime(contact.received_at || contact.updated_at)}`;
  $("replyMessage").innerHTML = escapeHtml(replyMessageFor(contact)).replaceAll("\n", "<br>");
  $("replyDraft").value = contact.responded_at
    ? contact.response_body || ""
    : `Hi ${replyDisplayName(contact.email).split(" ")[0]},\n\n`;
  $("starReplyBtn").classList.toggle("active", replyFlag(contact, "starred"));
  $("archiveReplyBtn").classList.toggle("active", replyFlag(contact, "archived"));
}

function renderStatusInsights() {
  const summary = state.statusSummary || { total: 0, statuses: [] };
  const maxCount = Math.max(1, ...summary.statuses.map((item) => item.count));
  const replied = summary.statuses.find((item) => item.key === "replied")?.count || 0;
  $("metricReplies").textContent = replied;
  $("sidebarReplyCount").textContent = replied;
  $("statusInsightTotal").textContent = summary.total || 0;
  $("statusInsightChart").innerHTML = summary.statuses.map((item) => {
    const percent = Math.round((item.count / maxCount) * 100);
    return `<div class="status-bar-row ${escapeHtml(item.key)}">
      <div class="status-bar-label"><span>${escapeHtml(item.label)}</span><strong>${item.count}</strong></div>
      <div class="status-bar-track"><span style="width: ${percent}%"></span></div>
    </div>`;
  }).join("");
}

function renderInsights() {
  const rows = state.preview?.rows || [];
  const counts = {};
  const ages = { "18-24": 0, "25-34": 0, "35-44": 0 };
  rows.forEach((row) => {
    const stateName = row.row_data?.state || "Unknown";
    counts[stateName] = (counts[stateName] || 0) + 1;
    const age = Number(row.row_data?.age);
    if (!Number.isFinite(age) || age <= 0) return;
    if (age >= 18 && age <= 24) ages["18-24"] += 1;
    else if (age >= 25 && age <= 34) ages["25-34"] += 1;
    else if (age >= 35) ages["35-44"] += 1;
  });
  const top = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 4);
  $("topStates").innerHTML = top.map(([name, count]) => `<div class="insight-line"><span>${escapeHtml(name)}</span><strong>${count}</strong></div>`).join("");
  $("topStatesMirror").innerHTML = $("topStates").innerHTML;
  const total = Math.max(1, Object.values(ages).reduce((a, b) => a + b, 0));
  $("ageDonut").style.background = `conic-gradient(#14b8a6 0 ${ages["18-24"] / total * 100}%, #2563eb ${ages["18-24"] / total * 100}% ${(ages["18-24"] + ages["25-34"]) / total * 100}%, #1d4ed8 0)`;
  $("ageLegend").innerHTML = Object.entries(ages).map(([label, count]) => `<div class="legend-line"><span>${label}</span><strong>${count}</strong></div>`).join("");
}

function renderRecipientPreview() {
  const valid = sendableRows();
  const contactedNote = $("overrideContacted")?.checked ? " (including contacted)" : "";
  $("recipientsMeta").textContent = `Showing ${Math.min(5, valid.length)} of ${valid.length} valid emails${contactedNote}`;
  $("recipientPreviewRows").innerHTML = valid.slice(0, 5).map((row) => `<tr>
    <td>${escapeHtml(`${row.first_name} ${row.last_name}`)}</td>
    <td>${escapeHtml(row.email)}</td>
    <td>${escapeHtml(row.row_data?.city || "")}</td>
    <td>${escapeHtml(row.row_data?.state || "")}</td>
  </tr>`).join("");
}

function renderPreviewTable() {
  const rows = sortedPreviewRows();
  $("previewStatus").textContent = `${state.preview?.summary?.sendable || 0} sendable contacts`;
  const pageSize = state.contactsPageSize;
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  state.contactsPage = Math.min(Math.max(1, state.contactsPage), pageCount);
  const start = (state.contactsPage - 1) * pageSize;
  const visibleRows = rows.slice(start, start + pageSize);
  $("previewRows").innerHTML = visibleRows.map((row) => `<tr>
    <td><input class="row-select" type="checkbox" data-row-index="${row.row_index}" ${state.selectedRows.has(row.row_index) ? "checked" : ""} ${row.sendable ? "" : "disabled"}></td>
    <td>${row.row_index}</td>
    <td>${escapeHtml(`${row.first_name} ${row.last_name}`)}<br>${escapeHtml(row.email)}</td>
    <td>${row.sendable ? '<span class="badge ok">sendable</span>' : row.errors.map((error) => `<span class="badge bad">${escapeHtml(errorLabel(error))}</span>`).join("")}</td>
    <td>${escapeHtml(row.subject)}</td>
    <td class="body-cell" title="${escapeHtml(row.body)}">${escapeHtml(previewText(row.body))}</td>
  </tr>`).join("");
  $("contactsPageInfo").textContent = rows.length
    ? `Showing ${start + 1}-${Math.min(start + pageSize, rows.length)} of ${rows.length} contacts`
    : "No contacts";
  $("contactsPageLabel").textContent = `${state.contactsPage} / ${pageCount}`;
  $("contactsPrevPage").disabled = state.contactsPage <= 1;
  $("contactsNextPage").disabled = state.contactsPage >= pageCount;
  updateSelectionStatus();
}

function renderLiveEmail() {
  const sample = sendableRows()[0] || state.preview?.rows?.[0] || { row_data: {}, email: "{{first_name}}" };
  $("previewTo").textContent = sample.email || "{{first_name}}";
  $("liveSubject").textContent = renderTemplate($("subject").value, sample.row_data);
  $("liveBody").innerHTML = escapeHtml(renderTemplate($("body").value, sample.row_data)).replaceAll("\n", "<br>");
  const chars = $("body").value.length;
  const words = $("body").value.trim() ? $("body").value.trim().split(/\s+/).length : 0;
  $("wordCount").textContent = `${chars} characters · ${words} words`;
  renderCampaignLiveEmail(sample);
}

function renderCampaignLiveEmail(sampleRow = null) {
  const sample = sampleRow || sendableRows()[0] || state.preview?.rows?.[0] || { row_data: {}, email: "{{first_name}}" };
  if (!$("campaignLiveSubject")) return;
  let subject = fieldValue("subjectStep", "subject");
  let body = fieldValue("bodyStep", "body");
  const note = $("rotationPreviewNote");
  if (rotationActive()) {
    const rotation = rotationTemplates();
    subject = rotation[0].subject;
    body = rotation[0].body;
    if (note) {
      note.hidden = false;
      note.textContent = `Rotation active - showing "${rotation[0].name}" (1 of ${rotation.length}). Recipients are split across: ${rotation.map((template) => template.name).join(", ")}.`;
    }
  } else if (note) {
    note.hidden = true;
  }
  $("campaignPreviewTo").textContent = sample.email || "{{first_name}}";
  $("campaignLiveSubject").textContent = renderTemplate(subject, sample.row_data);
  $("campaignLiveBody").innerHTML = escapeHtml(renderTemplate(body, sample.row_data)).replaceAll("\n", "<br>");
  const chars = body.length;
  const words = body.trim() ? body.trim().split(/\s+/).length : 0;
  $("campaignWordCount").textContent = `${chars} characters · ${words} words`;
}

const DEFAULT_TEMPLATE_VARIABLES = ["first_name", "last_name", "city", "state", "company", "role"];

function availableTemplateVariables() {
  const names = [...DEFAULT_TEMPLATE_VARIABLES];
  const rowData = state.preview?.rows?.[0]?.row_data || {};
  Object.keys(rowData).forEach((key) => {
    const name = key.trim();
    if (name && !names.includes(name)) names.push(name);
  });
  return names;
}

function renderVariableChips() {
  const chips = availableTemplateVariables()
    .map((name) => `<button type="button" class="variable-chip" data-insert="{{${escapeHtml(name)}}}" title="Insert {{${escapeHtml(name)}}} at the cursor">{{${escapeHtml(name)}}}</button>`)
    .join("");
  document.querySelectorAll(".variables").forEach((container) => {
    container.innerHTML = chips;
  });
}

function insertAtCursor(field, text) {
  const start = field.selectionStart ?? field.value.length;
  const end = field.selectionEnd ?? start;
  field.value = `${field.value.slice(0, start)}${text}${field.value.slice(end)}`;
  const cursor = start + text.length;
  field.focus();
  field.setSelectionRange(cursor, cursor);
  field.dispatchEvent(new Event("input", { bubbles: true }));
}

document.querySelectorAll(".variables").forEach((container) => {
  const subjectField = $(container.dataset.subjectField);
  const bodyField = $(container.dataset.bodyField);
  let targetField = bodyField;
  [subjectField, bodyField].forEach((field) => {
    field.addEventListener("focus", () => { targetField = field; });
  });
  // Keep the input focused (and its cursor position) while clicking a chip.
  container.addEventListener("mousedown", (event) => event.preventDefault());
  container.addEventListener("click", (event) => {
    const chip = event.target.closest("button[data-insert]");
    if (!chip) return;
    insertAtCursor(targetField, chip.dataset.insert);
  });
});

function renderSchedulePreview() {
  const interval = Number(fieldValue("intervalStep", "interval") || 10);
  const jitter = Number(fieldValue("intervalJitterStep", "intervalJitter") || 0);
  const limit = Math.min(Number(fieldValue("dailySendLimitStep", "dailySendLimit") || 25), state.selectedRows.size || sendableRows().length);
  const start = new Date();
  const times = [];
  for (let i = 0; i < Math.min(limit, 5); i += 1) {
    start.setMinutes(start.getMinutes() + interval + (i % 2 === 0 ? jitter : -jitter));
    times.push(`<span>${start.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>`);
  }
  $("schedulePreview").innerHTML = times.join("") + (limit > 5 ? "<span>...</span>" : "");
  $("scheduleSummary").textContent = `${limit} emails will be sent today`;
}

function updateSelectionStatus() {
  const valid = sendableRows();
  const percent = valid.length ? Math.round((state.selectedRows.size / valid.length) * 100) : 0;
  $("queueBtn").disabled = state.selectedRows.size === 0;
  $("selectionStatus").textContent = `${state.selectedRows.size} of ${valid.length} selected`;
  $("selectedRecipientCount").textContent = state.selectedRows.size;
  $("validRecipientCount").textContent = valid.length;
  $("selectedRecipientPercent").textContent = `${percent}% of valid emails`;
  $("recipientTableCount").textContent = valid.length;
  $("selectAllRows").checked = valid.length > 0 && state.selectedRows.size === valid.length;
  $("selectAllRows").indeterminate = state.selectedRows.size > 0 && state.selectedRows.size < valid.length;
  renderMetrics();
  renderSchedulePreview();
  updateCampaignFooter();
}

function updateCampaignFooter() {
  if (!$("campaignContinueBtn") || !$("queueBtn")) return;
  const manual = isManualOnlyMode();
  const showLaunch = manual || state.campaignStep === 4;
  $("campaignContinueBtn").hidden = showLaunch;
  $("queueBtn").closest(".launch-bar").hidden = !showLaunch;
  $("campaignBackBtn").disabled = state.campaignStep === 1;
}

let previewRefreshChain = Promise.resolve();

function setPreviewControlsBusy(busy) {
  ["selectAllRows", "overrideContacted", "excludeCompanyEmails", "genderFilter", "recipientAgeFilter", "contactSortOrder"].forEach((id) => {
    const control = $(id);
    if (control) control.disabled = busy;
  });
}

async function refreshPreviewNow() {
  setPreviewControlsBusy(true);
  try {
    const manualEntries = manualRecipientEntries();
    const manualOnly = $("manualOnlyRecipients").checked && manualEntries.length > 0;
    if ($("csvFile").value === "__pending_upload__" && !manualOnly) {
      throw new Error("Import the selected CSV before previewing or launching.");
    }
    state.preview = await api("/api/preview", { method: "POST", body: JSON.stringify(payload()) });
    state.selectedRows = new Set(sendableRows().map((row) => row.row_index));
    state.contactsPage = 1;
    $("csvMeta").textContent = manualOnly
      ? "CSV skipped while manual-only mode is on"
      : `${state.preview.summary.total} contacts from ${$("csvFile").selectedOptions[0]?.textContent || "CSV"}`;
    $("csvStatus").textContent = manualOnly ? "Manual recipients" : "CSV imported";
    updateManualRecipientsStatus();
    renderMetrics();
    renderInsights();
    renderRecipientPreview();
    renderPreviewTable();
    renderLiveEmail();
    renderSchedulePreview();
    renderVariableChips();
  } finally {
    setPreviewControlsBusy(false);
  }
}

function refreshPreview() {
  const next = previewRefreshChain.then(() => refreshPreviewNow());
  previewRefreshChain = next.catch(() => {});
  return next;
}

async function loadJobs() {
  const { jobs } = await api("/api/jobs");
  state.jobs = jobs;
  renderJobsTable();
  renderRecentActivity();
  renderMetrics();
  if ((window.location.hash || "#dashboard").slice(1) === "campaigns" && !state.campaignPanelTouched) {
    showDefaultCampaignPanel();
  }
}

function renderJobsTable() {
  const totalJobs = state.jobs.length;
  const pageSize = state.jobsPageSize;
  const pageCount = Math.max(1, Math.ceil(totalJobs / pageSize));
  state.jobsPage = Math.min(Math.max(1, state.jobsPage), pageCount);
  const start = (state.jobsPage - 1) * pageSize;
  const visibleJobs = state.jobs.slice(start, start + pageSize);
  $("jobs").innerHTML = visibleJobs.length ? visibleJobs.map((job) => {
    const counts = job.counts || {};
    const total = Object.values(counts).reduce((a, b) => a + b, 0);
    return `<tr>
      <td>${escapeHtml(job.campaign_name || job.id)}</td>
      <td>${total}</td>
      <td>${counts.sent || 0}</td>
      <td>0</td>
      <td><span class="status ${escapeHtml(job.status)}">${escapeHtml(job.status)}</span></td>
      <td>${counts.pending ? "Scheduled" : "—"}</td>
      <td class="table-actions">
        <button data-action="details" data-id="${job.id}" title="Details"><span data-icon="eye"></span></button>
        <button data-action="pause" data-id="${job.id}" title="Pause"><span data-icon="pause"></span></button>
        <button data-action="resume" data-id="${job.id}" title="Resume"><span data-icon="play"></span></button>
        <button data-action="cancel" data-id="${job.id}" title="Cancel sending"><span data-icon="ban"></span></button>
        <button data-action="delete" data-id="${job.id}" data-name="${escapeHtml(job.campaign_name || job.id)}" title="Delete"><span data-icon="trash"></span></button>
      </td>
    </tr>`;
  }).join("") : '<tr><td colspan="7">No campaigns yet.</td></tr>';
  initIcons($("jobs"));
  $("jobsPageInfo").textContent = totalJobs
    ? `Showing ${start + 1}-${Math.min(start + pageSize, totalJobs)} of ${totalJobs} campaigns`
    : "No campaigns";
  $("jobsPageLabel").textContent = `${state.jobsPage} / ${pageCount}`;
  $("jobsPrevPage").disabled = state.jobsPage <= 1;
  $("jobsNextPage").disabled = state.jobsPage >= pageCount;
}

function renderRecentActivity() {
  const latest = state.jobs.slice(0, 4);
  $("recentActivity").innerHTML = latest.length ? latest.map((job) => {
    const counts = job.counts || {};
    const sent = counts.sent || 0;
    const failed = counts.failed || 0;
    const label = failed ? "Email delivery failed" : sent ? "Email sent" : `Campaign "${job.campaign_name || "Untitled"}" updated`;
    const tone = failed ? "bad" : sent ? "ok" : "warn";
    const icon = tone === "bad" ? "triangleAlert" : tone === "ok" ? "check" : "send";
    return `<div class="activity-item ${tone}"><span data-icon="${icon}"></span><div><strong>${escapeHtml(label)}</strong><small>${escapeHtml(job.campaign_name || job.id)} · ${formatDate(job.updated_at || job.created_at)}</small></div></div>`;
  }).join("") : '<p>No campaign activity yet.</p>';
  initIcons($("recentActivity"));
}

async function loadStatusSummary() {
  state.statusSummary = await api("/api/email-status-summary");
  renderStatusInsights();
  renderNotifications();
}

async function loadQueueDetails(jobId) {
  const { items } = await api(`/api/jobs/${jobId}/queue`);
  $("queueDetails").innerHTML = `<div class="queue-details"><table class="mini-table">
    <thead><tr><th>Row</th><th>Email</th><th>Template</th><th>Status</th><th>Detail</th></tr></thead>
    <tbody>${items.map((item) => `<tr><td>${item.row_index}</td><td>${escapeHtml(item.email)}</td><td>${escapeHtml(item.template_name || "Inline")}</td><td>${escapeHtml(item.status)}</td><td>${escapeHtml(item.verification_detail || item.error || "")}</td></tr>`).join("")}</tbody>
  </table></div>`;
}

async function loadSuppressions() {
  const { contacts } = await api("/api/suppressions");
  $("suppressions").innerHTML = contacts.length ? `<table class="mini-table">
    <thead><tr><th>Email</th><th>Reason</th><th>Source</th><th>Action</th></tr></thead>
    <tbody>${contacts.map((contact) => `<tr><td>${escapeHtml(contact.email)}</td><td>${escapeHtml(contact.reason)}</td><td>${escapeHtml(contact.source)}</td><td><button data-action="unsuppress" data-email="${escapeHtml(contact.email_norm)}">Unsuppress</button></td></tr>`).join("")}</tbody>
  </table>` : "<p>No suppressed contacts yet.</p>";
}

async function loadReplies() {
  const params = new URLSearchParams();
  if ($("csvFile")?.value) params.set("csv_file", $("csvFile").value);
  const { replies } = await api(`/api/replies${params.toString() ? `?${params}` : ""}`);
  state.replies = replies.map((reply) => ({
    ...reply,
    email: reply.from_email,
    updated_at: reply.updated_at || reply.received_at,
  }));
  const visibleReplies = filteredReplies();
  state.selectedReplyIndex = Math.min(state.selectedReplyIndex, Math.max(0, visibleReplies.length - 1));
  renderReplyFilters();
  $("replyThreads").innerHTML = visibleReplies.length ? visibleReplies.map((contact, index) => `<button class="reply-thread ${index === state.selectedReplyIndex ? "active" : ""}" type="button" data-reply-index="${index}">
    <span class="avatar small">${escapeHtml((contact.email || "?").slice(0, 1).toUpperCase())}</span>
    <div><strong>${escapeHtml(contact.email)}</strong><small>${replyFlag(contact, "starred") ? "Starred · " : ""}${escapeHtml(contact.subject || "No subject")} · ${escapeHtml(contact.campaign_name || "unmatched")}</small></div>
    <time title="${escapeHtml(formatDate(contact.received_at))}">${escapeHtml(formatRelativeTime(contact.received_at))}</time>
  </button>`).join("") : '<p class="empty-state">No Gmail replies synced yet.</p>';
  initIcons($("replyThreads"));
  renderSelectedReply(visibleReplies);
  renderNotifications();
}

async function uploadAttachments() {
  const files = Array.from($("attachmentUpload").files || []);
  if (!files.length) return showToast("Choose one or more files first.", "warning");
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  const response = await fetch("/api/attachments", { method: "POST", body: formData });
  if (!response.ok) return showToast(await response.text(), "error", "Upload failed");
  const result = await response.json();
  state.attachments = [...state.attachments, ...result.files];
  $("attachmentUpload").value = "";
  renderAttachments();
  showToast(`${result.files.length} attachment${result.files.length === 1 ? "" : "s"} uploaded.`, "success");
}

function resetPreview() {
  state.preview = null;
  state.selectedRows = new Set();
  $("previewRows").innerHTML = "";
  updateSelectionStatus();
}

function resetCsvDependentUi(message = "Loading contacts...") {
  state.preview = null;
  state.selectedRows = new Set();
  state.contactsPage = 1;
  $("csvMeta").textContent = message;
  $("csvStatus").textContent = "Loading CSV";
  $("uploadStatus").textContent = "";
  $("recipientsMeta").textContent = "Showing 0 valid emails";
  $("recipientPreviewRows").innerHTML = "";
  $("previewStatus").textContent = "0 sendable contacts";
  $("previewRows").innerHTML = "";
  $("topStates").innerHTML = "";
  $("topStatesMirror").innerHTML = "";
  $("ageLegend").innerHTML = "";
  $("contactsPageInfo").textContent = "No contacts";
  $("contactsPageLabel").textContent = "1 / 1";
  $("contactsPrevPage").disabled = true;
  $("contactsNextPage").disabled = true;
  renderMetrics();
  renderInsights();
  renderLiveEmail();
  renderSchedulePreview();
  updateSelectionStatus();
}

function openLaunchConfirmModal() {
  if (!state.preview || state.selectedRows.size === 0) {
    showToast("Preview and select at least one sendable row first.", "warning");
    return;
  }
  $("confirmCampaignName").textContent = fieldValue("campaignNameStep", "campaignName") || "Untitled Campaign";
  $("confirmRecipientCount").textContent = `${state.selectedRows.size} selected`;
  $("confirmTemplates").textContent = rotationActive()
    ? `${state.rotationTemplateIds.size} rotating (${rotationTemplates().map((template) => template.name).join(", ")})`
    : "Inline template";
  $("confirmSendRule").textContent = `${fieldValue("intervalStep", "interval") || 10} minutes ± ${fieldValue("intervalJitterStep", "intervalJitter") || 0}`;
  $("confirmDailyLimit").textContent = `${fieldValue("dailySendLimitStep", "dailySendLimit") || 25} emails`;
  $("launchConfirmModal").hidden = false;
  $("confirmLaunchBtn").focus();
}

function closeLaunchConfirmModal() {
  $("launchConfirmModal").hidden = true;
  $("queueBtn").focus();
}

async function launchCampaign() {
  if (!state.preview || state.selectedRows.size === 0) {
    showToast("Preview and select at least one sendable row first.", "warning");
    return;
  }
  $("confirmLaunchBtn").disabled = true;
  const result = await api("/api/jobs", { method: "POST", body: JSON.stringify(payload()) });
  showToast(`Launched ${result.queued} recipients.`, "success", "Campaign launched");
  $("confirmLaunchBtn").disabled = false;
  $("launchConfirmModal").hidden = true;
  await loadJobs();
  await loadStatusSummary();
  showPage("campaigns");
  state.campaignPanelTouched = true;
  showCardPanel("campaigns", "campaigns-activity");
  const jobId = result.job_id || result.id;
  if (jobId) await loadQueueDetails(jobId).catch(() => {});
}

function setDefaultStartTime() {
  const endValue = $("businessEnd")?.value || "17:00";
  const now = new Date();
  const nowValue = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
  const value = nowValue < endValue ? nowValue : "09:00";
  $("businessStart").value = value;
  $("businessStartStep").value = value;
}

let confirmModalResolve = null;

function confirmAction({ title, message, confirmLabel = "Delete" }) {
  $("confirmModalTitle").textContent = title;
  $("confirmModalMessage").textContent = message;
  $("confirmModalConfirmBtn").innerHTML = `<span data-icon="trash"></span> ${escapeHtml(confirmLabel)}`;
  initIcons($("confirmModal"));
  $("confirmModal").hidden = false;
  $("confirmModalConfirmBtn").focus();
  return new Promise((resolve) => { confirmModalResolve = resolve; });
}

function closeConfirmModal(result) {
  $("confirmModal").hidden = true;
  if (confirmModalResolve) {
    confirmModalResolve(result);
    confirmModalResolve = null;
  }
}

$("confirmModalCancelBtn").addEventListener("click", () => closeConfirmModal(false));
$("confirmModalConfirmBtn").addEventListener("click", () => closeConfirmModal(true));
$("confirmModal").addEventListener("click", (event) => {
  if (event.target.id === "confirmModal") closeConfirmModal(false);
});
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("confirmModal").hidden) closeConfirmModal(false);
});

$("previewBtn").addEventListener("click", () => {
  renderLiveEmail();
  showCardPanel("templates", "templates-preview");
});
$("queueBtn").addEventListener("click", openLaunchConfirmModal);
$("cancelLaunchBtn").addEventListener("click", closeLaunchConfirmModal);
$("launchConfirmModal").addEventListener("click", (event) => {
  if (event.target.id === "launchConfirmModal") closeLaunchConfirmModal();
});
$("confirmLaunchBtn").addEventListener("click", () => {
  launchCampaign().catch((error) => {
    $("confirmLaunchBtn").disabled = false;
    showToast(error, "error", "Launch failed");
  });
});
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("launchConfirmModal").hidden) closeLaunchConfirmModal();
});
$("csvFile").addEventListener("change", async () => {
  state.selectedCsv = $("csvFile").value;
  localStorage.setItem("selectedCsv", state.selectedCsv);
  state.pendingCsvFileName = "";
  $("csvUploadLabel").textContent = "Choose File";
  resetCsvDependentUi("Loading contacts...");
  await refreshPreview().catch((error) => {
    resetCsvDependentUi("Could not load this CSV");
    showToast(error, "error", "Preview failed");
  });
  await loadReplies().catch((error) => showToast(error, "error", "Replies refresh failed"));
});
$("csvUpload").addEventListener("change", () => {
  const file = $("csvUpload").files[0];
  if (!file) {
    $("csvUploadLabel").textContent = "Choose File";
    state.pendingCsvFileName = "";
    return;
  }
  showPendingCsvSelection(file);
});
$("uploadCsvBtn").addEventListener("click", async () => {
  const file = $("csvUpload").files[0];
  if (!file) return showToast("Choose a CSV file first.", "warning");
  const formData = new FormData();
  formData.append("file", file);
  $("uploadCsvBtn").disabled = true;
  resetCsvDependentUi(`Importing ${file.name}...`);
  try {
    const response = await fetch("/api/csv-files", { method: "POST", body: formData });
    if (!response.ok) throw new Error(readableMessage(await response.text()));
    const result = await response.json();
    state.selectedCsv = result.file.name;
    localStorage.setItem("selectedCsv", state.selectedCsv);
    state.pendingCsvFileName = "";
    $("uploadStatus").textContent = `${result.count} contacts imported`;
    $("csvUpload").value = "";
    $("csvUploadLabel").textContent = "Choose File";
    await loadCsvFiles();
    showToast(`${result.count} contacts imported from ${result.file.display_name || result.file.name}.`, "success", "CSV imported");
  } catch (error) {
    resetCsvDependentUi("CSV import failed");
    showToast(error, "error", "CSV import failed");
  } finally {
    $("uploadCsvBtn").disabled = false;
  }
});
$("uploadAttachmentBtn").addEventListener("click", () => uploadAttachments().catch((error) => showToast(error, "error", "Upload failed")));
$("attachmentList").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action='remove-attachment']");
  if (!button) return;
  state.attachments = state.attachments.filter((file) => file.id !== button.dataset.id);
  renderAttachments();
});
$("manualRecipients").addEventListener("input", () => {
  updateManualRecipientsStatus();
  if (manualRecipientEntries().length) $("manualOnlyRecipients").checked = true;
});
$("manualOnlyRecipients").addEventListener("change", updateCampaignFooter);
$("manualPreviewBtn").addEventListener("click", async () => {
  updateManualRecipientsStatus();
  await refreshPreview()
    .then(() => showToast("Manual recipients applied to preview.", "success", "Recipients updated"))
    .catch((error) => showToast(error, "error", "Preview failed"));
});

["subject", "body", "subjectStep", "bodyStep", "interval", "intervalJitter", "dailySendLimit", "intervalStep", "intervalJitterStep", "dailySendLimitStep", "sendLimitStep", "businessStartStep", "businessEndStep", "timezoneStep", "ageMin", "ageMax", "ageMinStep", "ageMaxStep"].forEach((id) => {
  $(id).addEventListener("input", () => { renderLiveEmail(); renderSchedulePreview(); renderMetrics(); });
});

["ageMin", "ageMax", "ageMinStep", "ageMaxStep"].forEach((id) => {
  $(id).addEventListener("change", () => refreshPreview().catch((error) => showToast(error, "error", "Preview failed")));
});

function syncAgeInputsFromRecipientFilter() {
  const value = $("recipientAgeFilter").value;
  const inputs = ["ageMin", "ageMinStep", "ageMax", "ageMaxStep"].map((id) => $(id));
  if (value === "all") {
    inputs.forEach((input) => { input.value = ""; });
    $("recipientAgeMin").value = "";
    $("recipientAgeMax").value = "";
    return;
  }
  if (value === "custom") {
    $("ageMin").value = $("recipientAgeMin").value;
    $("ageMinStep").value = $("recipientAgeMin").value;
    $("ageMax").value = $("recipientAgeMax").value;
    $("ageMaxStep").value = $("recipientAgeMax").value;
    return;
  }
  const [min, max] = value.split("-");
  $("recipientAgeMin").value = min;
  $("recipientAgeMax").value = max;
  $("ageMin").value = min;
  $("ageMinStep").value = min;
  $("ageMax").value = max;
  $("ageMaxStep").value = max;
}

$("selectAllRows").addEventListener("change", () => {
  state.selectedRows = $("selectAllRows").checked ? new Set(sendableRows().map((row) => row.row_index)) : new Set();
  document.querySelectorAll(".row-select").forEach((checkbox) => { if (!checkbox.disabled) checkbox.checked = $("selectAllRows").checked; });
  updateSelectionStatus();
});
$("overrideContacted").addEventListener("change", () => {
  renderRecipientPreview();
  refreshPreview().catch((error) => showToast(error, "error", "Preview failed"));
});
$("overrideContactedStep").addEventListener("change", async () => {
  $("overrideContacted").checked = $("overrideContactedStep").checked;
  await refreshPreview().catch((error) => showToast(error, "error", "Preview failed"));
});
["excludeCompanyEmails", "excludeCompanyEmailsStep", "excludeCompanyEmailsSetting"].forEach((id) => {
  $(id).addEventListener("change", async () => {
    const checked = $(id).checked;
    $("excludeCompanyEmails").checked = checked;
    $("excludeCompanyEmailsStep").checked = checked;
    $("excludeCompanyEmailsSetting").checked = checked;
    await refreshPreview().catch((error) => showToast(error, "error", "Preview failed"));
  });
});

$("previewRows").addEventListener("change", (event) => {
  const checkbox = event.target.closest(".row-select");
  if (!checkbox) return;
  const rowIndex = Number(checkbox.dataset.rowIndex);
  checkbox.checked ? state.selectedRows.add(rowIndex) : state.selectedRows.delete(rowIndex);
  updateSelectionStatus();
});

$("replyThreads").addEventListener("click", (event) => {
  const thread = event.target.closest(".reply-thread");
  if (!thread) return;
  state.selectedReplyIndex = Number(thread.dataset.replyIndex || 0);
  document.querySelectorAll(".reply-thread").forEach((button) => {
    button.classList.toggle("active", button === thread);
  });
  renderSelectedReply();
});
$("replyFilters").addEventListener("click", (event) => {
  const button = event.target.closest("[data-reply-filter]");
  if (!button) return;
  state.replyFilter = button.dataset.replyFilter;
  state.selectedReplyIndex = 0;
  loadReplies().catch((error) => showToast(error, "error", "Replies refresh failed"));
});
$("starReplyBtn").addEventListener("click", () => {
  const reply = filteredReplies()[state.selectedReplyIndex];
  if (!reply) return showToast("Select a reply first.", "warning");
  setReplyFlag(reply, "starred", !replyFlag(reply, "starred"));
  renderReplyFilters();
  loadReplies().catch((error) => showToast(error, "error", "Replies refresh failed"));
});
$("archiveReplyBtn").addEventListener("click", () => {
  const reply = filteredReplies()[state.selectedReplyIndex];
  if (!reply) return showToast("Select a reply first.", "warning");
  setReplyFlag(reply, "archived", !replyFlag(reply, "archived"));
  state.replyFilter = replyFlag(reply, "archived") ? "archived" : "all";
  state.selectedReplyIndex = 0;
  loadReplies().catch((error) => showToast(error, "error", "Replies refresh failed"));
});
$("syncRepliesBtn").addEventListener("click", async () => {
  const button = $("syncRepliesBtn");
  const originalHtml = button.innerHTML;
  button.disabled = true;
  button.innerHTML = '<span data-icon="inbox"></span> Syncing...';
  initIcons(button);
  showToast("Connecting to Gmail and preparing to fetch recent inbound replies.", "info", "Gmail sync starting");
  let pendingTimer = window.setTimeout(() => {
    showToast("Gmail reply sync is still running. You can keep using the app while it finishes.", "info", "Gmail sync pending");
  }, 900);
  try {
    const result = await api("/api/replies/sync", {
      method: "POST",
      body: JSON.stringify({ csv_file: $("csvFile")?.value || null, limit: 15 }),
    });
    window.clearTimeout(pendingTimer);
    pendingTimer = null;
    await loadReplies();
    await loadStatusSummary();
    showToast(
      `${result.synced} Gmail replies synced. ${result.skipped || 0} unrelated inbox messages skipped.`,
      "success",
      "Gmail sync finished"
    );
  } catch (error) {
    if (pendingTimer) window.clearTimeout(pendingTimer);
    showToast(error, "error", "Gmail sync failed");
  } finally {
    button.disabled = false;
    button.innerHTML = originalHtml;
    initIcons(button);
  }
});
$("sendReplyBtn").addEventListener("click", async () => {
  const reply = state.replies[state.selectedReplyIndex];
  if (!reply?.id) return showToast("Select a synced reply first.", "warning");
  const body = $("replyDraft").value.trim();
  if (!body) return showToast("Write a reply before sending.", "warning");
  $("sendReplyBtn").disabled = true;
  try {
    await api(`/api/replies/${reply.id}/respond`, { method: "POST", body: JSON.stringify({ body }) });
    await loadReplies();
    showToast("Your response was sent and recorded.", "success", "Reply sent");
  } catch (error) {
    showToast(error, "error", "Reply send failed");
  } finally {
    $("sendReplyBtn").disabled = false;
  }
});

$("jobs").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  if (button.dataset.action === "details") return loadQueueDetails(button.dataset.id);
  if (button.dataset.action === "delete") {
    const confirmed = await confirmAction({
      title: "Delete campaign?",
      message: `"${button.dataset.name}" and its sending queue will be permanently removed. This cannot be undone.`,
      confirmLabel: "Delete Campaign",
    });
    if (!confirmed) return;
    await api(`/api/jobs/${button.dataset.id}`, { method: "DELETE" });
    await loadJobs();
    showToast("Campaign deleted.", "success", "Campaign removed");
    return;
  }
  await api(`/api/jobs/${button.dataset.id}/${button.dataset.action}`, { method: "POST", body: "{}" });
  await loadJobs();
  await loadStatusSummary();
});

$("suppressBtn").addEventListener("click", async () => {
  const email = $("suppressEmail").value.trim();
  if (!email) return showToast("Enter an email address to suppress.", "warning");
  await api("/api/suppressions", { method: "POST", body: JSON.stringify({ email, reason: $("suppressReason").value, note: $("suppressNote").value.trim() || null }) });
  $("suppressEmail").value = "";
  $("suppressNote").value = "";
  await loadSuppressions();
  if (state.preview) await refreshPreview();
  showToast(`${email} has been suppressed.`, "success", "Contact suppressed");
});

$("suppressions").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action='unsuppress']");
  if (!button) return;
  await api(`/api/suppressions/${encodeURIComponent(button.dataset.email)}`, { method: "DELETE" });
  await loadSuppressions();
  if (state.preview) await refreshPreview();
});

$("refreshJobsBtn").addEventListener("click", async () => { await loadJobs(); await loadStatusSummary(); });
$("jobsPageSize").addEventListener("change", () => {
  state.jobsPageSize = Number($("jobsPageSize").value || 5);
  state.jobsPage = 1;
  renderJobsTable();
});
$("jobsPrevPage").addEventListener("click", () => {
  state.jobsPage -= 1;
  renderJobsTable();
});
$("jobsNextPage").addEventListener("click", () => {
  state.jobsPage += 1;
  renderJobsTable();
});
$("contactsPageSize").addEventListener("change", () => {
  state.contactsPageSize = Number($("contactsPageSize").value || 5);
  state.contactsPage = 1;
  renderPreviewTable();
});
$("contactSortOrder").addEventListener("change", () => {
  state.contactSortOrder = $("contactSortOrder").value;
  state.contactsPage = 1;
  renderPreviewTable();
});
$("genderFilter").addEventListener("change", async () => {
  state.contactsPage = 1;
  await refreshPreview().catch((error) => showToast(error, "error", "Preview failed"));
});
$("recipientAgeFilter").addEventListener("change", async () => {
  syncAgeInputsFromRecipientFilter();
  state.contactsPage = 1;
  await refreshPreview().catch((error) => showToast(error, "error", "Preview failed"));
});
["recipientAgeMin", "recipientAgeMax"].forEach((id) => {
  $(id).addEventListener("change", async () => {
    $("recipientAgeFilter").value = "custom";
    syncAgeInputsFromRecipientFilter();
    state.contactsPage = 1;
    await refreshPreview().catch((error) => showToast(error, "error", "Preview failed"));
  });
});
$("viewRecipientFiltersBtn").addEventListener("click", () => {
  $("genderFilter").focus();
});
$("resetRecipientFiltersBtn").addEventListener("click", async () => {
  $("selectAllRows").checked = true;
  $("excludeCompanyEmails").checked = true;
  $("excludeCompanyEmailsStep").checked = true;
  $("excludeCompanyEmailsSetting").checked = true;
  $("overrideContacted").checked = false;
  $("overrideContactedStep").checked = false;
  $("genderFilter").value = "male";
  $("recipientAgeFilter").value = "18-44";
  $("recipientAgeMin").value = "18";
  $("recipientAgeMax").value = "44";
  syncAgeInputsFromRecipientFilter();
  $("contactSortOrder").value = "fresh_first";
  state.contactSortOrder = "fresh_first";
  state.contactsPage = 1;
  await refreshPreview().catch((error) => showToast(error, "error", "Preview failed"));
});
$("contactsPrevPage").addEventListener("click", () => {
  state.contactsPage -= 1;
  renderPreviewTable();
});
$("contactsNextPage").addEventListener("click", () => {
  state.contactsPage += 1;
  renderPreviewTable();
});
$("refreshSuppressionsBtn").addEventListener("click", loadSuppressions);
$("testRecipient").value = localStorage.getItem("testRecipient") || "";
$("sendTestBtn").addEventListener("click", async () => {
  const toEmail = $("testRecipient").value.trim();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(toEmail)) {
    showToast("Enter a valid recipient email address first.", "warning", "Test email");
    $("testRecipient").focus();
    return;
  }
  localStorage.setItem("testRecipient", toEmail);
  const sample = sendableRows()[0] || state.preview?.rows?.[0] || { row_data: {} };
  const button = $("sendTestBtn");
  const originalHtml = button.innerHTML;
  button.disabled = true;
  button.textContent = "Sending...";
  try {
    const result = await api("/api/send-test", {
      method: "POST",
      body: JSON.stringify({
        to_email: toEmail,
        subject: renderTemplate($("subject").value, sample.row_data),
        body: renderTemplate($("body").value, sample.row_data),
      }),
    });
    const verified = result.result?.verification?.status === "sent_mail_found";
    showToast(
      verified
        ? `Sent to ${toEmail} and verified in Gmail Sent Mail.`
        : `Sent to ${toEmail}. ${result.result?.verification?.detail || ""}`,
      "success",
      "Test email sent",
    );
  } catch (error) {
    showToast(error, "error", "Test send failed");
  } finally {
    button.disabled = false;
    button.innerHTML = originalHtml;
    initIcons(button);
  }
});
$("newTemplateBtn").addEventListener("click", () => {
  applyTemplate({ id: null, name: "Untitled Template", subject: "Hi {{first_name}},", body: "Hi {{first_name}},\n\n" });
  showCardPanel("templates", "templates-editor");
});
$("saveTemplateBtn").addEventListener("click", () => saveCurrentTemplate().catch((error) => showToast(error, "error", "Template save failed")));
$("deleteTemplateBtn")?.addEventListener("click", () => deleteCurrentTemplate().catch((error) => showToast(error, "error", "Delete failed")));
$("rotationTemplateList")?.addEventListener("change", (event) => {
  const checkbox = event.target.closest("input[data-rotation-id]");
  if (!checkbox) return;
  if (checkbox.checked) state.rotationTemplateIds.add(checkbox.dataset.rotationId);
  else state.rotationTemplateIds.delete(checkbox.dataset.rotationId);
  updateRotationStatus();
});
$("sideTemplateSearch").addEventListener("input", renderSidebarTemplateList);
$("sideTemplateList").addEventListener("click", (event) => {
  const item = event.target.closest("[data-template-id]");
  if (!item) return;
  const template = state.templates.find((entry) => entry.id === item.dataset.templateId);
  if (!template) return;
  applyTemplate(template);
  showPage("templates");
  showCardPanel("templates", "templates-editor");
});
$("loginBtn").addEventListener("click", () => showPage("login"));
$("newCampaignBtn").addEventListener("click", () => {
  showPage("campaigns");
  state.campaignPanelTouched = true;
  showCardPanel("campaigns", "campaigns-create");
});
$("newCampaignBtnCampaigns").addEventListener("click", () => {
  state.campaignPanelTouched = true;
  showCardPanel("campaigns", "campaigns-create");
});
$("notificationBtn").addEventListener("click", () => setNotificationPanel($("notificationPanel").hidden));
$("notificationCloseBtn").addEventListener("click", () => setNotificationPanel(false));
$("notificationList").addEventListener("click", (event) => {
  const item = event.target.closest("[data-notify-target]");
  if (!item) return;
  setNotificationPanel(false);
  showPage(item.dataset.notifyTarget);
});
$("themeToggleBtn").addEventListener("click", () => {
  applyTheme(state.theme === "dark" ? "light" : "dark");
  showToast(`Theme switched to ${state.theme === "dark" ? "dark" : "daylight"} mode.`, "success", "Theme updated");
});

document.querySelectorAll('input[name="themePreference"]').forEach((input) => {
  input.addEventListener("change", () => {
    if (!input.checked) return;
    applyTheme(input.value);
    showToast(`Theme switched to ${state.theme === "dark" ? "dark" : "daylight"} mode.`, "success", "Theme updated");
  });
});
$("campaignBackBtn").addEventListener("click", () => showWorkflowStep(state.campaignStep - 1));
$("campaignContinueBtn").addEventListener("click", async () => {
  try {
    await refreshPreview();
    state.campaignPanelTouched = true;
    showWorkflowStep(state.campaignStep + 1);
  } catch (error) {
    showToast(error, "error", "Preview failed");
  }
});
$("campaignPreviewBtn").addEventListener("click", () => {
  renderCampaignLiveEmail();
  showToast("Email preview updated with sample contact data.", "success", "Preview updated");
});
document.querySelectorAll("[data-workflow-step]").forEach((button) => {
  button.addEventListener("click", async () => {
    const targetStep = Number(button.dataset.workflowStep);
    state.campaignPanelTouched = true;
    showWorkflowStep(targetStep);
    if (targetStep > 1) {
      try {
        await refreshPreview();
      } catch (error) {
        showToast(error, "error", "Preview failed");
      }
    }
  });
});
document.querySelectorAll("[data-card-tab]").forEach((button) => {
  button.addEventListener("click", () => {
    if (button.dataset.cardTab === "campaigns") state.campaignPanelTouched = true;
    showCardPanel(button.dataset.cardTab, button.dataset.cardTarget);
  });
});
document.querySelectorAll("[data-page-link], [data-page-target]").forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    showPage(link.dataset.pageLink || link.dataset.pageTarget);
  });
});
window.addEventListener("hashchange", () => showPage((window.location.hash || "#dashboard").slice(1)));
document.addEventListener("click", (event) => {
  if ($("notificationPanel").hidden) return;
  if (event.target.closest(".notification-wrap")) return;
  setNotificationPanel(false);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("notificationPanel").hidden) setNotificationPanel(false);
});

applyTheme(state.theme);
loadAuth();
setDefaultStartTime();
initIcons();
showPage((window.location.hash || "#dashboard").slice(1));
loadCsvFiles().catch((error) => showToast(error, "error", "Startup data load failed"));
loadJobs();
loadStatusSummary();
loadSuppressions();
loadTemplates();
renderAttachments();
renderVariableChips();
setInterval(async () => { await loadJobs(); await loadStatusSummary(); }, 15000);
