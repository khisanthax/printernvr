const POLL_INTERVAL_MS = 4000;
const TIMELAPSE_POLL_INTERVAL_MS = 5000;
const timelapseStates = new Map();
const localTimelapseErrors = new Map();

function bySelector(selector) {
  return document.querySelector(selector);
}

function bySelectorAll(selector) {
  return Array.from(document.querySelectorAll(selector));
}

function formatTimestamp(value) {
  if (!value) {
    return "--";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}

function humanFileName(value) {
  if (!value) {
    return "--";
  }

  const parts = String(value).split(/[\\/]/);
  return parts[parts.length - 1] || value;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch (_error) {
    payload = null;
  }

  if (!response.ok) {
    const detail = payload && payload.detail ? payload.detail : "Request failed";
    throw new Error(detail);
  }

  return payload;
}

function setBadge(cameraId, status) {
  const badge = bySelector(`[data-camera-status="${cameraId}"]`);
  if (!badge) {
    return;
  }

  const normalized = (status || "idle").toLowerCase();
  const label = normalized.charAt(0).toUpperCase() + normalized.slice(1);
  badge.textContent = `Recording: ${label}`;
  badge.classList.remove(
    "status-idle",
    "status-starting",
    "status-recording",
    "status-stopping",
    "status-downloading",
    "status-error",
  );
  badge.classList.add(`status-${normalized}`);
}

function updateControlStates(cameraId, state) {
  const card = bySelector(`[data-camera-card="${cameraId}"]`);
  if (!card) {
    return;
  }

  const enabled = card.dataset.cameraEnabled === "true";
  const status = (state.status || "idle").toLowerCase();
  const busy = ["starting", "recording", "stopping", "downloading"].includes(status);
  const buttons = bySelectorAll(`[data-camera-card="${cameraId}"] .camera-controls .control-button`);
  const input = bySelector(`[data-custom-duration="${cameraId}"]`);

  buttons.forEach((button) => {
    const action = button.dataset.action;
    if (!enabled) {
      button.disabled = true;
      return;
    }

    if (action === "stop") {
      button.disabled = !["starting", "recording"].includes(status);
      return;
    }

    button.disabled = state.recording || status === "starting";
  });

  if (input) {
    input.disabled = !enabled || busy;
  }
}

function updateCameraState(state) {
  const cameraId = state.camera_id;
  setBadge(cameraId, state.status);
  updateControlStates(cameraId, state);

  const startedAt = bySelector(`[data-started-at="${cameraId}"]`);
  const expectedEnd = bySelector(`[data-expected-end="${cameraId}"]`);
  const outputFile = bySelector(`[data-output-file="${cameraId}"]`);
  const lastOutput = bySelector(`[data-last-output="${cameraId}"]`);
  const errorMessage = bySelector(`[data-error-message="${cameraId}"]`);
  const errorDetailsWrap = bySelector(`[data-error-details-wrap="${cameraId}"]`);
  const errorDetails = bySelector(`[data-error-details="${cameraId}"]`);
  const errorCommandMeta = bySelector(`[data-error-command-meta="${cameraId}"]`);
  const actionMessage = bySelector(`[data-action-message="${cameraId}"]`);
  const downloadStatus = bySelector(`[data-download-status="${cameraId}"]`);

  if (startedAt) {
    startedAt.textContent = formatTimestamp(state.started_at);
  }
  if (expectedEnd) {
    expectedEnd.textContent = formatTimestamp(state.expected_end_at);
  }
  if (outputFile) {
    outputFile.textContent = humanFileName(state.output_file || state.last_downloaded_filename);
  }
  if (lastOutput) {
    lastOutput.textContent = humanFileName(
      state.last_completed_output || state.last_downloaded_filename,
    );
  }
  if (actionMessage) {
    actionMessage.textContent = state.last_action_message || "--";
  }
  if (downloadStatus) {
    downloadStatus.textContent = state.last_download_status || "--";
  }
  if (errorMessage) {
    if (state.last_error) {
      errorMessage.hidden = false;
      errorMessage.textContent = state.last_error;
    } else {
      errorMessage.hidden = true;
      errorMessage.textContent = "";
    }
  }
  if (errorDetailsWrap && errorDetails && errorCommandMeta) {
    const metaParts = [];
    if (state.backend_type) {
      metaParts.push(`Backend: ${state.backend_type}`);
    }
    if (state.last_ffmpeg_exit_code !== null && state.last_ffmpeg_exit_code !== undefined) {
      metaParts.push(`Exit code: ${state.last_ffmpeg_exit_code}`);
    }
    if (state.last_ffmpeg_command) {
      metaParts.push(`Command: ${state.last_ffmpeg_command}`);
    }

    const hasDetails = Boolean(state.last_error_details || metaParts.length);
    errorDetailsWrap.hidden = !hasDetails;
    if (hasDetails) {
      errorCommandMeta.textContent = metaParts.join(" | ");
      errorDetails.textContent = state.last_error_details || "";
    } else {
      errorCommandMeta.textContent = "";
      errorDetails.textContent = "";
      errorDetailsWrap.open = false;
    }
  }
}

function updateStorageStatus(status) {
  const used = bySelector("#storage-used");
  const free = bySelector("#storage-free");
  const mode = bySelector("#storage-mode");
  const warning = bySelector("#storage-warning");
  const summary = bySelector("#storage-cleanup-summary");
  const cleanupButton = bySelector("#manual-cleanup-button");

  if (used) {
    used.textContent = `${status.total_recordings_gb.toFixed(3)} GB`;
  }
  if (free) {
    free.textContent = `${status.free_disk_gb.toFixed(3)} GB`;
  }
  if (mode) {
    mode.textContent = status.cleanup_mode;
  }
  if (warning) {
    if (status.warning_state) {
      warning.hidden = false;
      warning.textContent = status.warnings.join(" ");
    } else {
      warning.hidden = true;
      warning.textContent = "";
    }
  }
  if (summary) {
    if (status.last_cleanup_summary) {
      if (status.last_cleanup_summary.deleted_files > 0) {
        summary.textContent =
          `Last cleanup removed ${status.last_cleanup_summary.deleted_files} file(s) and freed ` +
          `${status.last_cleanup_summary.deleted_gb.toFixed(3)} GB.`;
      } else {
        summary.textContent = "Last cleanup found no eligible completed recordings to remove.";
      }
    } else {
      summary.textContent = "";
    }
  }
  if (cleanupButton) {
    cleanupButton.hidden = !status.retention_enabled || status.cleanup_mode === "disabled";
  }
}

async function refreshRecordings() {
  const payload = await fetchJson("/api/record/status");
  (payload.cameras || []).forEach(updateCameraState);
}

function getTimelapseStatusTone(status) {
  const normalized = String(status || "idle").toLowerCase();
  return ["starting", "running", "stopping", "rendering", "complete", "error"].includes(normalized)
    ? normalized
    : "idle";
}

function getTimelapseStatusLabel(status) {
  const tone = getTimelapseStatusTone(status);
  return `Timelapse: ${tone.charAt(0).toUpperCase() + tone.slice(1)}`;
}

function isActiveTimelapseTone(tone) {
  return ["starting", "running", "stopping", "rendering"].includes(tone);
}

function getDashboardTimelapseInterval(cameraId) {
  const select = bySelector(`[data-dashboard-timelapse-interval="${cameraId}"]`);
  if (!(select instanceof HTMLSelectElement)) {
    return 10;
  }
  const interval = Number(select.value);
  return Number.isInteger(interval) && interval >= 1 && interval <= 300 ? interval : 10;
}

function setDashboardTimelapseError(cameraId, message) {
  const errorNode = bySelector(`[data-dashboard-timelapse-error="${cameraId}"]`);
  if (!errorNode) {
    return;
  }

  if (message) {
    errorNode.hidden = false;
    errorNode.textContent = message;
    return;
  }

  errorNode.hidden = true;
  errorNode.textContent = "";
}

function updateText(selector, value) {
  const node = bySelector(selector);
  if (node) {
    node.textContent = value;
  }
}

function describeDashboardTimelapse(card, state) {
  const cameraId = card.dataset.dashboardTimelapseCamera;
  const cameraName = card.dataset.dashboardTimelapseCameraName || card.dataset.dashboardTimelapseCamera || "camera";
  const backend = card.dataset.dashboardTimelapseBackend || "";
  if (backend !== "ffmpeg") {
    return "Timelapse requires an RTSP/ffmpeg camera.";
  }

  if (!state || !state.status || state.status === "idle") {
    return `Timelapse idle. Capture camera: ${cameraName}`;
  }

  const activeCamera = state.camera_name || state.camera_id || cameraName;
  const frames = Number(state.frame_count || 0);
  const interval = state.interval_seconds ? `${state.interval_seconds}s` : "--";
  const tone = getTimelapseStatusTone(state.status);
  const ownsSession = Boolean(state.camera_id && state.camera_id === cameraId);
  if (isActiveTimelapseTone(tone) && !ownsSession) {
    return `Printer timelapse is active on ${activeCamera}.`;
  }
  if (!ownsSession) {
    return `Timelapse idle. Capture camera: ${cameraName}`;
  }
  if (tone === "starting") {
    return `Starting timelapse from ${activeCamera}...`;
  }
  if (tone === "running") {
    return `Capturing ${activeCamera} every ${interval}. ${frames} frame${frames === 1 ? "" : "s"} captured.`;
  }
  if (tone === "stopping") {
    return `Stopping timelapse from ${activeCamera}...`;
  }
  if (tone === "rendering") {
    return `Rendering MP4 from ${frames} frame${frames === 1 ? "" : "s"}...`;
  }
  if (tone === "complete") {
    return state.output_file ? `Timelapse complete: ${state.output_file}` : "Timelapse complete.";
  }
  if (tone === "error") {
    return state.render_error || state.last_error || "Timelapse error";
  }
  return `Timelapse idle. Capture camera: ${cameraName}`;
}

function updateDashboardTimelapseCard(card) {
  const cameraId = card.dataset.dashboardTimelapseCamera;
  const printerId = card.dataset.dashboardTimelapsePrinter;
  if (!cameraId || !printerId) {
    return;
  }

  const state = timelapseStates.get(printerId) || null;
  const tone = getTimelapseStatusTone(state && state.status);
  const busy = isActiveTimelapseTone(tone);
  const ownsSession = Boolean(state && state.camera_id && state.camera_id === cameraId);
  const displayTone = ownsSession ? tone : "idle";
  const enabled = card.dataset.dashboardTimelapseEnabled === "true";
  const backend = card.dataset.dashboardTimelapseBackend || "";
  const canStart = enabled && backend === "ffmpeg";

  const badge = bySelector(`[data-dashboard-timelapse-badge="${cameraId}"]`);
  if (badge) {
    badge.textContent = getTimelapseStatusLabel(displayTone);
    badge.classList.remove(
      "recording-state-pill--idle",
      "recording-state-pill--starting",
      "recording-state-pill--recording",
      "recording-state-pill--stopping",
      "recording-state-pill--downloading",
      "recording-state-pill--error",
    );
    const badgeTone = {
      idle: "idle",
      starting: "starting",
      running: "recording",
      stopping: "stopping",
      rendering: "downloading",
      complete: "recording",
      error: "error",
    }[displayTone] || "idle";
    badge.classList.add(`recording-state-pill--${badgeTone}`);
  }

  updateText(`[data-dashboard-timelapse-message="${cameraId}"]`, describeDashboardTimelapse(card, state));
  updateText(`[data-dashboard-timelapse-frames="${cameraId}"]`, ownsSession && state ? String(state.frame_count || 0) : "0");
  updateText(
    `[data-dashboard-timelapse-camera-label="${cameraId}"]`,
    ownsSession && state && state.camera_name ? state.camera_name : (card.dataset.dashboardTimelapseCameraName || "--"),
  );
  updateText(`[data-dashboard-timelapse-stop-reason="${cameraId}"]`, ownsSession && state && state.stop_reason ? state.stop_reason : "--");
  updateText(`[data-dashboard-timelapse-render="${cameraId}"]`, ownsSession && state && state.render_status ? state.render_status : "idle");

  const outputLink = bySelector(`[data-dashboard-timelapse-output="${cameraId}"]`);
  if (outputLink instanceof HTMLAnchorElement) {
    if (ownsSession && state && state.output_url && tone === "complete") {
      outputLink.href = state.output_url;
      outputLink.removeAttribute("aria-disabled");
      outputLink.textContent = state.output_file || "Latest Timelapse";
    } else {
      outputLink.href = "#";
      outputLink.setAttribute("aria-disabled", "true");
      outputLink.textContent = "Latest Timelapse";
    }
  }

  const localError = localTimelapseErrors.get(`${printerId}::${cameraId}`);
  setDashboardTimelapseError(
    cameraId,
    localError || (ownsSession && state && (state.last_error || state.render_error) ? `Error: ${state.last_error || state.render_error}` : ""),
  );

  bySelectorAll(`[data-dashboard-timelapse-camera="${cameraId}"][data-dashboard-timelapse-action]`).forEach((button) => {
    if (!(button instanceof HTMLButtonElement)) {
      return;
    }
    const action = button.dataset.dashboardTimelapseAction;
    if (action === "stop") {
      button.disabled = !(ownsSession && ["starting", "running"].includes(tone));
      return;
    }
    button.disabled = busy || !canStart;
  });

  const intervalSelect = bySelector(`[data-dashboard-timelapse-interval="${cameraId}"]`);
  if (intervalSelect instanceof HTMLSelectElement) {
    intervalSelect.disabled = busy || !canStart;
  }
}

function updateAllDashboardTimelapseCards() {
  bySelectorAll("[data-dashboard-timelapse-card]").forEach(updateDashboardTimelapseCard);
}

async function refreshTimelapses() {
  const payload = await fetchJson("/api/timelapse/status");
  Object.entries(payload.printers || {}).forEach(([printerId, state]) => {
    timelapseStates.set(printerId, state);
  });
  updateAllDashboardTimelapseCards();
}

async function refreshStorage() {
  const payload = await fetchJson("/api/storage/status");
  updateStorageStatus(payload);
}

async function refreshAll() {
  try {
    await Promise.all([refreshRecordings(), refreshStorage(), refreshTimelapses()]);
  } catch (error) {
    console.error(error);
  }
}

async function startRecording(cameraId, duration) {
  const options = {
    method: "POST",
  };

  if (duration !== undefined && duration !== null) {
    options.body = JSON.stringify({ duration });
  }

  await fetchJson(`/api/record/start/${cameraId}`, options);
  await refreshAll();
}

async function stopRecording(cameraId) {
  await fetchJson(`/api/record/stop/${cameraId}`, {
    method: "POST",
  });
  await refreshAll();
}

async function startTimelapse(printerId, cameraId, intervalSeconds) {
  const payload = await fetchJson(`/api/timelapse/start/${encodeURIComponent(printerId)}`, {
    method: "POST",
    body: JSON.stringify({
      camera_id: cameraId,
      interval_seconds: intervalSeconds,
    }),
  });
  if (payload.timelapse) {
    timelapseStates.set(printerId, payload.timelapse);
  }
  updateAllDashboardTimelapseCards();
}

async function stopTimelapse(printerId) {
  const payload = await fetchJson(`/api/timelapse/stop/${encodeURIComponent(printerId)}`, {
    method: "POST",
  });
  if (payload.timelapse) {
    timelapseStates.set(printerId, payload.timelapse);
  }
  updateAllDashboardTimelapseCards();
}

async function manualCleanup() {
  try {
    const payload = await fetchJson("/api/storage/cleanup", { method: "POST" });
    if (payload.status) {
      updateStorageStatus(payload.status);
    }
    await refreshRecordings();
  } catch (error) {
    console.error(error);
    const warning = bySelector("#storage-warning");
    if (warning) {
      warning.hidden = false;
      warning.textContent = error.message;
    }
  }
}

function bindCameraControls() {
  bySelectorAll(".camera-controls").forEach((controls) => {
    const cameraId = controls.dataset.cameraId;
    if (!cameraId) {
      return;
    }

    controls.addEventListener("click", async (event) => {
      const target = event.target;
      if (!(target instanceof HTMLButtonElement)) {
        return;
      }

      const action = target.dataset.action;
      if (!action) {
        return;
      }

      try {
        if (action === "start") {
          await startRecording(cameraId);
        } else if (action === "stop") {
          await stopRecording(cameraId);
        } else if (action === "timed") {
          await startRecording(cameraId, Number(target.dataset.duration));
        } else if (action === "custom") {
          const input = bySelector(`[data-custom-duration="${cameraId}"]`);
          const duration = input ? Number(input.value) : NaN;
          if (!duration || duration < 1) {
            throw new Error("Custom duration must be greater than zero");
          }
          await startRecording(cameraId, duration);
        }
      } catch (error) {
        console.error(error);
        const errorNode = bySelector(`[data-error-message="${cameraId}"]`);
        if (errorNode) {
          errorNode.hidden = false;
          errorNode.textContent = error.message;
        }
      }
    });
  });
}

function bindTimelapseControls() {
  bySelectorAll("[data-dashboard-timelapse-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const printerId = button.dataset.dashboardTimelapsePrinter;
      const cameraId = button.dataset.dashboardTimelapseCamera;
      const action = button.dataset.dashboardTimelapseAction;
      if (!printerId || !cameraId || !action) {
        return;
      }

      const localErrorKey = `${printerId}::${cameraId}`;
      localTimelapseErrors.delete(localErrorKey);
      setDashboardTimelapseError(cameraId, "");

      try {
        if (action === "start") {
          updateText(`[data-dashboard-timelapse-message="${cameraId}"]`, "Starting timelapse...");
          await startTimelapse(printerId, cameraId, getDashboardTimelapseInterval(cameraId));
        } else if (action === "stop") {
          updateText(`[data-dashboard-timelapse-message="${cameraId}"]`, "Stopping timelapse...");
          await stopTimelapse(printerId);
        }
        await refreshTimelapses();
      } catch (error) {
        console.error(error);
        localTimelapseErrors.set(localErrorKey, `Error: ${error.message}`);
        updateAllDashboardTimelapseCards();
        await refreshTimelapses().catch((refreshError) => console.error(refreshError));
      }
    });
  });

  bySelectorAll("[data-dashboard-timelapse-output]").forEach((link) => {
    link.addEventListener("click", (event) => {
      if (link.getAttribute("aria-disabled") === "true") {
        event.preventDefault();
      }
    });
  });
}

function bindCleanupControl() {
  const cleanupButton = bySelector("#manual-cleanup-button");
  if (!cleanupButton) {
    return;
  }

  cleanupButton.addEventListener("click", async () => {
    cleanupButton.disabled = true;
    try {
      await manualCleanup();
    } finally {
      cleanupButton.disabled = false;
    }
  });
}

bindCameraControls();
bindTimelapseControls();
bindCleanupControl();
refreshAll();
setInterval(refreshAll, POLL_INTERVAL_MS);
setInterval(() => {
  refreshTimelapses().catch((error) => console.error(error));
}, TIMELAPSE_POLL_INTERVAL_MS);
