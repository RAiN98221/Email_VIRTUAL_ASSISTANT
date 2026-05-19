const state = { preview: null, selectedRows: new Set() };

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
  const sendLimit = $("sendLimit").value ? Number($("sendLimit").value) : null;
  return {
    csv_file: $("csvFile").value,
    subject: $("subject").value,
    body: $("body").value,
    content_type: $("contentType").value,
    override_contacted: $("overrideContacted").checked,
    selected_row_indexes: Array.from(state.selectedRows),
    send_limit: sendLimit,
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
  state.selectedRows = new Set(data.rows.filter((row) => row.sendable).map((row) => row.row_index));
  renderSummary(data.summary);
  updateSelectionStatus();
  $("previewStatus").textContent = `${data.summary.sendable} sendable contacts`;
  $("previewRows").innerHTML = data.rows
    .map(
      (row) => `<tr>
        <td>
          <input class="row-select" type="checkbox" data-row-index="${row.row_index}" ${row.sendable ? "checked" : "disabled"}>
        </td>
        <td>${row.row_index}</td>
        <td>${row.first_name} ${row.last_name}<br>${row.email}</td>
        <td>${badges(row)}</td>
        <td>${escapeHtml(row.subject)}</td>
        <td class="body-cell">${escapeHtml(row.body)}</td>
      </tr>`
    )
    .join("");
}

function updateSelectionStatus() {
  const sendableRows = state.preview ? state.preview.rows.filter((row) => row.sendable) : [];
  $("queueBtn").disabled = state.selectedRows.size === 0;
  $("selectionStatus").textContent = `${state.selectedRows.size} of ${sendableRows.length} selected`;
  $("selectAllRows").checked = sendableRows.length > 0 && state.selectedRows.size === sendableRows.length;
  $("selectAllRows").indeterminate = state.selectedRows.size > 0 && state.selectedRows.size < sendableRows.length;
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
  $("loginBtn").textContent = status.configured
    ? `Gmail: ${status.account}`
    : "Set Gmail .env";
  $("loginBtn").disabled = true;
}

async function loadContacts() {
  const params = new URLSearchParams({ csv_file: $("csvFile").value });
  const contacts = await api(`/api/contacts?${params}`);
  $("csvMeta").textContent = `${contacts.count} contacts from ${contacts.csv_file}`;
}

async function loadCsvFiles() {
  const { files } = await api("/api/csv-files");
  $("csvFile").innerHTML = files
    .map(
      (file) =>
        `<option value="${escapeHtml(file.name)}" ${file.default ? "selected" : ""}>${escapeHtml(file.name)}</option>`
    )
    .join("");
  $("previewBtn").disabled = files.length === 0;
  $("queueBtn").disabled = true;
  if (files.length === 0) {
    $("csvMeta").textContent = "No CSV contact files found";
    return;
  }
  await loadContacts();
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
            <div class="queue-details" id="queue-${job.id}"></div>
            <div class="job-actions">
              <button data-action="details" data-id="${job.id}">Details</button>
              <button data-action="pause" data-id="${job.id}">Pause</button>
              <button data-action="resume" data-id="${job.id}">Resume</button>
              <button data-action="cancel" data-id="${job.id}">Cancel</button>
            </div>
          </article>`
        )
        .join("")
    : "<p>No jobs yet.</p>";
}

function setDefaultStartTime() {
  const now = new Date();
  const hours = String(now.getHours()).padStart(2, "0");
  const minutes = String(now.getMinutes()).padStart(2, "0");
  $("businessStart").value = `${hours}:${minutes}`;
}

$("previewBtn").addEventListener("click", async () => {
  try {
    renderPreview(await api("/api/preview", { method: "POST", body: JSON.stringify(payload()) }));
  } catch (error) {
    alert(error.message);
  }
});

$("csvFile").addEventListener("change", async () => {
  state.preview = null;
  state.selectedRows = new Set();
  $("queueBtn").disabled = true;
  $("previewRows").innerHTML = "";
  $("summary").innerHTML = "";
  $("previewStatus").textContent = "";
  $("selectionStatus").textContent = "";
  $("selectAllRows").checked = false;
  $("selectAllRows").indeterminate = false;
  await loadContacts();
});

$("selectAllRows").addEventListener("change", () => {
  if (!state.preview) return;
  const sendableRows = state.preview.rows.filter((row) => row.sendable);
  state.selectedRows = $("selectAllRows").checked
    ? new Set(sendableRows.map((row) => row.row_index))
    : new Set();
  document.querySelectorAll(".row-select").forEach((checkbox) => {
    if (!checkbox.disabled) checkbox.checked = $("selectAllRows").checked;
  });
  updateSelectionStatus();
});

$("previewRows").addEventListener("change", (event) => {
  const checkbox = event.target.closest(".row-select");
  if (!checkbox) return;
  const rowIndex = Number(checkbox.dataset.rowIndex);
  if (checkbox.checked) {
    state.selectedRows.add(rowIndex);
  } else {
    state.selectedRows.delete(rowIndex);
  }
  updateSelectionStatus();
});

$("queueBtn").addEventListener("click", async () => {
  if (!state.preview) return;
  if (state.selectedRows.size === 0) {
    alert("Select at least one sendable row first.");
    return;
  }
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
  if (button.dataset.action === "details") {
    await loadQueueDetails(button.dataset.id);
    return;
  }
  await api(`/api/jobs/${button.dataset.id}/${button.dataset.action}`, { method: "POST", body: "{}" });
  await loadJobs();
});

async function loadQueueDetails(jobId) {
  const { items } = await api(`/api/jobs/${jobId}/queue`);
  const target = $(`queue-${jobId}`);
  target.innerHTML = items.length
    ? `<table class="queue-table">
        <thead><tr><th>Row</th><th>Email</th><th>Status</th><th>Error</th></tr></thead>
        <tbody>${items
          .map(
            (item) => `<tr>
              <td>${item.row_index}</td>
              <td>${escapeHtml(item.email)}</td>
              <td>${escapeHtml(item.status)}</td>
              <td>${escapeHtml(item.error || "")}</td>
            </tr>`
          )
          .join("")}</tbody>
      </table>`
    : "<p>No queue items found.</p>";
}

loadAuth();
setDefaultStartTime();
loadCsvFiles();
loadJobs();
setInterval(loadJobs, 15000);
