const state = { preview: null };

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text);
  }
  return response.json();
}

function payload() {
  return {
    subject: $("subject").value,
    body: $("body").value,
    content_type: $("contentType").value,
    override_contacted: $("overrideContacted").checked,
    interval_minutes: Number($("interval").value || 10),
    business_start: $("businessStart").value,
    business_end: $("businessEnd").value,
    timezone: $("timezone").value,
  };
}

function renderSummary(summary) {
  $("summary").innerHTML = Object.entries(summary)
    .map(([key, value]) => `<div class="metric"><strong>${value}</strong>${key.replaceAll("_", " ")}</div>`)
    .join("");
}

function badges(row) {
  if (row.sendable) return '<span class="badge ok">sendable</span>';
  return row.errors
    .map((error) => `<span class="badge ${error === "already_contacted" ? "warn" : "bad"}">${error}</span>`)
    .join("");
}

function renderPreview(data) {
  state.preview = data;
  renderSummary(data.summary);
  $("queueBtn").disabled = data.summary.sendable === 0;
  $("previewStatus").textContent = `${data.summary.sendable} contacts ready to queue`;
  $("previewRows").innerHTML = data.rows
    .map(
      (row) => `<tr>
        <td>${row.row_index}</td>
        <td>${row.first_name} ${row.last_name}<br>${row.email}</td>
        <td>${badges(row)}</td>
        <td>${escapeHtml(row.subject)}</td>
        <td class="body-cell">${escapeHtml(row.body)}</td>
      </tr>`
    )
    .join("");
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function loadAuth() {
  const status = await api("/api/auth/status");
  $("loginBtn").textContent = status.authenticated
    ? `Connected: ${status.account}`
    : status.configured
      ? "Connect Outlook"
      : "Set .env first";
  $("loginBtn").disabled = !status.configured;
}

async function loadContacts() {
  const contacts = await api("/api/contacts");
  $("csvMeta").textContent = `${contacts.count} contacts from ${contacts.csv_path}`;
}

async function loadJobs() {
  const { jobs } = await api("/api/jobs");
  $("jobs").innerHTML = jobs.length
    ? jobs
        .map(
          (job) => `<article class="job">
            <div><strong>${job.status}</strong> job ${job.id}</div>
            <div>${job.interval_minutes} min interval, ${job.business_start}-${job.business_end} ${job.timezone}</div>
            <div>${Object.entries(job.counts).map(([k, v]) => `<span class="badge">${k}: ${v}</span>`).join("")}</div>
            <div class="job-actions">
              <button data-action="pause" data-id="${job.id}">Pause</button>
              <button data-action="resume" data-id="${job.id}">Resume</button>
              <button data-action="cancel" data-id="${job.id}">Cancel</button>
            </div>
          </article>`
        )
        .join("")
    : "<p>No jobs yet.</p>";
}

$("loginBtn").addEventListener("click", () => {
  window.location.href = "/auth/login";
});

$("previewBtn").addEventListener("click", async () => {
  try {
    renderPreview(await api("/api/preview", { method: "POST", body: JSON.stringify(payload()) }));
  } catch (error) {
    alert(error.message);
  }
});

$("queueBtn").addEventListener("click", async () => {
  if (!state.preview) return;
  try {
    const result = await api("/api/jobs", { method: "POST", body: JSON.stringify(payload()) });
    alert(`Queued ${result.queued} contacts.`);
    await loadJobs();
  } catch (error) {
    alert(error.message);
  }
});

$("refreshJobsBtn").addEventListener("click", loadJobs);

$("jobs").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  await api(`/api/jobs/${button.dataset.id}/${button.dataset.action}`, { method: "POST", body: "{}" });
  await loadJobs();
});

loadAuth();
loadContacts();
loadJobs();
setInterval(loadJobs, 15000);
