import { api, clearMessage, escapeHtml, formatDate, showMessage, statusBadge } from "./api.js";

const form = document.querySelector("#source-form");
const sourceIdInput = document.querySelector("#source-id");
const typeInput = document.querySelector("#source-type");
const messageBox = document.querySelector("#settings-message");
const cancelEditButton = document.querySelector("#cancel-edit");
const sourceList = document.querySelector("#source-list");
const syncAllButton = document.querySelector("#sync-all");
const saveSyncSettingsButton = document.querySelector("#save-sync-settings");
const syncTimeoutInput = document.querySelector("#sync-timeout-minutes");
const saveLibrarySettingsButton = document.querySelector("#save-library-settings");
const libraryResultsPerPageInput = document.querySelector("#library-results-per-page");
const saveThemeSettingsButton = document.querySelector("#save-theme-settings");
const defaultThemeInput = document.querySelector("#default-theme");
const queueStatus = document.querySelector("#queue-status");
const saveSourceButton = document.querySelector("#save-source");
const sourceCreateLockMessage = document.querySelector("#source-create-lock-message");

let pollHandle = null;
let hasActiveSync = false;

const SOURCE_CREATE_BLOCKED_MESSAGE = "New sources cannot be added while a sync is in progress. Please wait until the current sync has finished.";

typeInput.addEventListener("change", updateFieldVisibility);
cancelEditButton.addEventListener("click", resetForm);
syncAllButton.addEventListener("click", syncAllSources);
saveSyncSettingsButton.addEventListener("click", saveSyncSettings);
saveLibrarySettingsButton.addEventListener("click", saveLibrarySettings);
saveThemeSettingsButton.addEventListener("click", saveThemeSettings);

document.addEventListener("app-theme-loaded", (event) => {
  defaultThemeInput.value = event.detail?.theme || "dark";
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearMessage(messageBox);

  if (!sourceIdInput.value && hasActiveSync) {
    updateSourceCreationAvailability();
    showMessage(messageBox, SOURCE_CREATE_BLOCKED_MESSAGE, "warning");
    return;
  }

  if (!form.checkValidity()) {
    form.classList.add("was-validated");
    return;
  }

  const payload = collectPayload();
  const sourceId = sourceIdInput.value;

  try {
    if (sourceId) {
      await api.patch(`/sources/${sourceId}`, payload);
      showMessage(messageBox, "Source updated.", "success");
    } else {
      await api.post("/sources", payload);
      showMessage(messageBox, "Source created.", "success");
    }

    resetForm();
    await refreshDashboard();
  } catch (error) {
    showMessage(messageBox, error.message, "danger");
  }
});

sourceList.addEventListener("click", async (event) => {
  const actionButton = event.target.closest("[data-action]");
  if (!actionButton) {
    return;
  }

  const { action, sourceId } = actionButton.dataset;

  try {
    if (action === "edit") {
      const payload = await api.get(`/sources/${sourceId}`);
      populateForm(payload.item);
      return;
    }

    if (action === "delete") {
      await api.delete(`/sources/${sourceId}`);
      showMessage(messageBox, "Source deleted.", "success");
      if (sourceIdInput.value === sourceId) {
        resetForm();
      }
      await refreshDashboard();
      return;
    }

    if (action === "sync") {
      const payload = await api.post(`/sources/${sourceId}/sync`, {});
      showMessage(messageBox, buildSyncMessage(payload), payload.queued ? "info" : "warning");
      await refreshDashboard();
      return;
    }

    if (action === "force-restart") {
      const payload = await api.post(`/sources/${sourceId}/sync/force-restart`, {});
      showMessage(
        messageBox,
        `Force restart queued for ${payload.item?.name || "the source"}. Any older unfinished job for this source will now be ignored.`,
        "warning",
      );
      await refreshDashboard();
    }
  } catch (error) {
    showMessage(messageBox, error.message, "danger");
  }
});

function updateFieldVisibility() {
  const sourceType = typeInput.value;
  document.querySelectorAll("[data-source-field='m3u']").forEach((element) => {
    element.classList.toggle("d-none", sourceType !== "m3u");
  });
  document.querySelectorAll("[data-source-field='xtream']").forEach((element) => {
    element.classList.toggle("d-none", sourceType !== "xtream");
  });
}

function collectPayload() {
  return {
    name: document.querySelector("#source-name").value,
    source_type: typeInput.value,
    enabled: document.querySelector("#source-enabled").checked,
    m3u_url: document.querySelector("#m3u-url").value,
    xtream_base_url: document.querySelector("#xtream-base-url").value,
    username: document.querySelector("#xtream-username").value,
    password: document.querySelector("#xtream-password").value,
    user_agent: document.querySelector("#user-agent").value,
  };
}

function populateForm(source) {
  sourceIdInput.value = source.id;
  document.querySelector("#source-name").value = source.name || "";
  typeInput.value = source.source_type;
  document.querySelector("#m3u-url").value = source.m3u_url || "";
  document.querySelector("#xtream-base-url").value = source.xtream_base_url || "";
  document.querySelector("#xtream-username").value = source.username || "";
  document.querySelector("#xtream-password").value = source.password || "";
  document.querySelector("#user-agent").value = source.user_agent || "";
  document.querySelector("#source-enabled").checked = Boolean(source.enabled);
  cancelEditButton.classList.remove("d-none");
  updateFieldVisibility();
  updateSourceCreationAvailability();
}

function resetForm() {
  form.reset();
  form.classList.remove("was-validated");
  sourceIdInput.value = "";
  document.querySelector("#source-enabled").checked = true;
  typeInput.value = "m3u";
  cancelEditButton.classList.add("d-none");
  updateFieldVisibility();
  updateSourceCreationAvailability();
}

async function saveSyncSettings() {
  clearMessage(messageBox);
  saveSyncSettingsButton.disabled = true;

  try {
    const payload = await api.patch("/settings", {
      sync_timeout_minutes: Number(syncTimeoutInput.value),
    });
    syncTimeoutInput.value = payload.sync_timeout_minutes;
    libraryResultsPerPageInput.value = payload.library_results_per_page;
    defaultThemeInput.value = payload.default_theme;
    showMessage(messageBox, `Sync timeout saved as ${payload.sync_timeout_minutes} minute(s). New jobs will use this timeout.`, "success");
  } catch (error) {
    showMessage(messageBox, error.message, "danger");
  } finally {
    saveSyncSettingsButton.disabled = false;
  }
}

async function saveLibrarySettings() {
  clearMessage(messageBox);
  saveLibrarySettingsButton.disabled = true;

  try {
    const payload = await api.patch("/settings", {
      library_results_per_page: Number(libraryResultsPerPageInput.value),
    });
    syncTimeoutInput.value = payload.sync_timeout_minutes;
    libraryResultsPerPageInput.value = payload.library_results_per_page;
    defaultThemeInput.value = payload.default_theme;
    showMessage(
      messageBox,
      `Library page size saved as ${payload.library_results_per_page} result${payload.library_results_per_page === 1 ? "" : "s"} per page.`,
      "success",
    );
  } catch (error) {
    showMessage(messageBox, error.message, "danger");
  } finally {
    saveLibrarySettingsButton.disabled = false;
  }
}

async function saveThemeSettings() {
  clearMessage(messageBox);
  saveThemeSettingsButton.disabled = true;

  try {
    const payload = await api.patch("/settings", {
      default_theme: defaultThemeInput.value,
    });
    syncTimeoutInput.value = payload.sync_timeout_minutes;
    libraryResultsPerPageInput.value = payload.library_results_per_page;
    defaultThemeInput.value = payload.default_theme;
    document.dispatchEvent(new CustomEvent("app-theme-changed", {
      detail: { theme: payload.default_theme },
    }));
    showMessage(messageBox, `Default theme saved as ${payload.default_theme}.`, "success");
  } catch (error) {
    showMessage(messageBox, error.message, "danger");
  } finally {
    saveThemeSettingsButton.disabled = false;
  }
}

async function syncAllSources() {
  clearMessage(messageBox);
  syncAllButton.disabled = true;
  syncAllButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Queueing sync jobs...';

  try {
    const payload = await api.post("/sync", {});
    const skipped = payload.skipped_sources.length;
    const skippedText = skipped ? ` ${skipped} source${skipped === 1 ? " was" : "s were"} already queued or running.` : "";
    showMessage(messageBox, `Queued ${payload.queued_count} source sync job${payload.queued_count === 1 ? "" : "s"}.${skippedText}`, "info");
    await refreshDashboard();
  } catch (error) {
    showMessage(messageBox, error.message, "danger");
  } finally {
    syncAllButton.disabled = false;
    syncAllButton.textContent = "Sync all enabled sources";
  }
}

async function refreshDashboard() {
  const [sourcesPayload, settingsPayload, queuePayload] = await Promise.all([
    api.get("/sources"),
    api.get("/settings"),
    api.get("/sync/status"),
  ]);

  hasActiveSync = queuePayload.has_activity;
  syncTimeoutInput.value = settingsPayload.sync_timeout_minutes;
  libraryResultsPerPageInput.value = settingsPayload.library_results_per_page;
  defaultThemeInput.value = settingsPayload.default_theme;
  renderQueueStatus(queuePayload);
  renderSources(sourcesPayload.items);
  updateSourceCreationAvailability();
  updatePolling(queuePayload.has_activity);
}

function updateSourceCreationAvailability() {
  const isCreateMode = !sourceIdInput.value;
  const shouldBlockCreation = isCreateMode && hasActiveSync;

  saveSourceButton.disabled = shouldBlockCreation;
  sourceCreateLockMessage.classList.toggle("d-none", !shouldBlockCreation);
}

function renderQueueStatus(queue) {
  if (!queue.has_activity) {
    queueStatus.textContent = "";
    queueStatus.classList.add("d-none");
    return;
  }

  const activeName = queue.active_job ? `Running job #${queue.active_job.id}` : "No active job";
  const queuedCount = queue.queue_length;
  queueStatus.textContent = `${activeName}. ${queuedCount} queued job${queuedCount === 1 ? "" : "s"} waiting. Fetch timeout: ${queue.sync_timeout_minutes} minute(s). Parsing, catalog clearing, and catalog replacement are not timed out.`;
  queueStatus.className = "alert alert-secondary";
}

function renderSources(sources) {
  if (!sources.length) {
    sourceList.innerHTML = `
      <div class="col-12">
        <div class="empty-state rounded-4 p-4 text-center">
          <h2 class="h5 mb-2">No sources saved yet.</h2>
          <p class="text-secondary mb-0">Use the form to add an M3U playlist or an Xtream Codes provider.</p>
        </div>
      </div>
    `;
    return;
  }

  sourceList.innerHTML = sources.map((source) => renderSourceCard(source)).join("");
}

function renderSourceCard(source) {
  const sync = source.sync;
  const isQueuedOrRunning = Boolean(sync && (sync.status === "queued" || sync.status === "running"));
  const liveStatus = sync?.status || source.last_sync_status;
  const statusDetails = renderStatusDetails(sync, source);

  return `
    <div class="col-md-6">
      <article class="card source-card border-0 shadow-sm h-100" data-source-card="${source.id}">
        <div class="card-body">
          <div class="d-flex justify-content-between gap-3 mb-3">
            <div>
              <span class="badge text-bg-light text-dark text-uppercase mb-2">${escapeHtml(source.source_type)}</span>
              <h2 class="h5 mb-1">${escapeHtml(source.name)}</h2>
              <div class="text-secondary small">${source.enabled ? "Enabled" : "Disabled"}</div>
            </div>
            ${statusBadge(liveStatus)}
          </div>
          <dl class="row small mb-3">
            <dt class="col-5 text-secondary">Last sync</dt>
            <dd class="col-7">${escapeHtml(formatDate(source.last_sync_at))}</dd>
            <dt class="col-5 text-secondary">Imported items</dt>
            <dd class="col-7">${escapeHtml(source.last_sync_count ?? 0)}</dd>
          </dl>
          ${statusDetails}
          <div class="d-flex flex-wrap gap-2">
            <button class="btn btn-sm btn-primary" data-action="sync" data-source-id="${source.id}" ${isQueuedOrRunning ? "disabled" : ""}>${sync?.status === "running" ? "Syncing..." : "Sync"}</button>
            <button class="btn btn-sm btn-outline-warning" data-action="force-restart" data-source-id="${source.id}">Force restart sync</button>
            <button class="btn btn-sm btn-outline-secondary" data-action="edit" data-source-id="${source.id}" ${isQueuedOrRunning ? "disabled" : ""}>Edit</button>
            <button class="btn btn-sm btn-outline-danger" data-action="delete" data-source-id="${source.id}" ${isQueuedOrRunning ? "disabled" : ""}>Delete</button>
          </div>
        </div>
      </article>
    </div>
  `;
}

function renderStatusDetails(sync, source) {
  if (sync) {
    const title = sync.status === "queued"
      ? `Queued for background sync${sync.queue_position ? ` (#${sync.queue_position})` : ""}.`
      : renderRunningTitle(sync);
    const counts = renderProgressCounts(sync);

    return `
      <div class="alert ${sync.status === "queued" ? "alert-info" : "alert-warning"} py-2 small">
        <div class="fw-semibold mb-1">${escapeHtml(title)}</div>
        <div>${escapeHtml(sync.message || "Waiting for the worker to report progress.")}</div>
        ${sync.stage ? `<div class="mt-1"><span class="text-secondary">Stage:</span> ${escapeHtml(sync.stage)}</div>` : ""}
        ${sync.timeout_applies && sync.lease_expires_at ? `<div class="mt-1"><span class="text-secondary">Fetch lease expires:</span> ${escapeHtml(formatDate(sync.lease_expires_at))}</div>` : ""}
        ${counts}
      </div>
    `;
  }

  if (source.last_error) {
    return `<div class="alert alert-danger py-2 small">${escapeHtml(source.last_error)}</div>`;
  }

  return '<div class="alert alert-light py-2 small">No background sync job is active for this source.</div>';
}

function renderRunningTitle(sync) {
  if (sync.stage === "fetching") {
    return `Background sync fetching provider data${sync.timeout_minutes ? ` with a ${sync.timeout_minutes}-minute fetch timeout` : ""}.`;
  }

  if (sync.stage === "clearing_catalog") {
    return "Background sync is clearing the existing local catalog.";
  }

  if (sync.stage === "replacing_catalog") {
    return "Background sync is replacing the local catalog.";
  }

  if (sync.stage === "parsing") {
    return "Background sync is parsing fetched provider data.";
  }

  return "Background sync is running.";
}

function renderProgressCounts(sync) {
  if (sync.stage === "replacing_catalog" && sync.total_items) {
    return `<div class="small text-secondary mt-2">Added ${escapeHtml(sync.items_count || 0)} of ${escapeHtml(sync.total_items)} items. ${escapeHtml(sync.remaining_items || 0)} left.</div>`;
  }

  if (sync.items_count || sync.categories_count) {
    return `<div class="small text-secondary mt-2">Imported ${escapeHtml(sync.items_count || 0)} items across ${escapeHtml(sync.categories_count || 0)} categories so far.</div>`;
  }

  return "";
}

function updatePolling(hasActivity) {
  if (hasActivity) {
    if (pollHandle !== null) {
      return;
    }

    pollHandle = window.setInterval(() => {
      refreshDashboard().catch((error) => {
        showMessage(messageBox, error.message, "danger");
      });
    }, 5000);
    return;
  }

  if (pollHandle !== null) {
    window.clearInterval(pollHandle);
    pollHandle = null;
  }
}

function buildSyncMessage(payload) {
  if (!payload.queued) {
    return `${payload.item?.name || "This source"} is already queued or running. Wait for the current sync to finish or use force restart.`;
  }

  return `${payload.item?.name || "The source"} was queued for background sync.`;
}

resetForm();
refreshDashboard().catch((error) => {
  showMessage(messageBox, error.message, "danger");
});
