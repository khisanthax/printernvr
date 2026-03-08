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

function setBadge(cameraId, status) {
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
  const mode = card.dataset.cameraMode;
  const status = (state.status || "idle").toLowerCase();
  const busy = ["starting", "recording", "stopping", "downloading"].includes(status);
  const buttons = bySelectorAll(`[data-camera-card="${cameraId}"] .control-button`);
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

    if (mode === "gopro") {
      button.disabled = busy;
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

async function downloadLatest(cameraId) {
  await fetchJson(`/api/gopro/${cameraId}/download_latest`, {
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
        } else if (action === "download-latest") {
          await downloadLatest(cameraId);
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
