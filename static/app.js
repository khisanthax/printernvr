const POLL_INTERVAL_MS = 4000;

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

function setBadge(cameraId, status, recording) {
  const badge = bySelector(`[data-camera-status="${cameraId}"]`);
  if (!badge) {
    return;
  }

  const normalized = (status || "idle").toLowerCase();
  const label = normalized.charAt(0).toUpperCase() + normalized.slice(1);
  badge.textContent = label;
  badge.classList.remove(
    "status-idle",
    "status-starting",
    "status-recording",
    "status-stopping",
    "status-error",
  );
  badge.classList.add(`status-${normalized}`);

  const card = bySelector(`[data-camera-card="${cameraId}"]`);
  if (!card) {
    return;
  }

  const buttons = bySelectorAll(`[data-camera-card="${cameraId}"] .control-button`);
  const input = bySelector(`[data-custom-duration="${cameraId}"]`);
  const enabled = card.dataset.cameraEnabled === "true";
  buttons.forEach((button) => {
    const action = button.dataset.action;
    if (!enabled) {
      button.disabled = true;
      return;
    }
    if (action === "stop") {
      button.disabled = !recording;
      return;
    }
    button.disabled = recording;
  });
  if (input) {
    input.disabled = !enabled || recording;
  }
}

function updateCameraState(state) {
  const cameraId = state.camera_id;
  setBadge(cameraId, state.status, state.recording);

  const startedAt = bySelector(`[data-started-at="${cameraId}"]`);
  const expectedEnd = bySelector(`[data-expected-end="${cameraId}"]`);
  const outputFile = bySelector(`[data-output-file="${cameraId}"]`);
  const lastOutput = bySelector(`[data-last-output="${cameraId}"]`);
  const errorMessage = bySelector(`[data-error-message="${cameraId}"]`);

  if (startedAt) {
    startedAt.textContent = formatTimestamp(state.started_at);
  }
  if (expectedEnd) {
    expectedEnd.textContent = formatTimestamp(state.expected_end_at);
  }
  if (outputFile) {
    outputFile.textContent = humanFileName(state.output_file);
  }
  if (lastOutput) {
    lastOutput.textContent = humanFileName(state.last_completed_output);
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

async function refreshStorage() {
  const payload = await fetchJson("/api/storage/status");
  updateStorageStatus(payload);
}

async function refreshAll() {
  try {
    await Promise.all([refreshRecordings(), refreshStorage()]);
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
bindCleanupControl();
refreshAll();
setInterval(refreshAll, POLL_INTERVAL_MS);
