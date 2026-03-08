let cameras = [];
let editingCameraId = null;
let idTouched = false;
let outputSubdirTouched = false;

const listNode = document.querySelector("#camera-list");
const listEmptyNode = document.querySelector("#camera-list-empty");
const form = document.querySelector("#camera-form");
const formTitle = document.querySelector("#camera-form-title");
const formError = document.querySelector("#camera-form-error");
const probeError = document.querySelector("#probe-error");
const probeSummary = document.querySelector(".probe-result__summary");
const probeStatus = document.querySelector("#probe-status");
const previewNode = document.querySelector("#editor-preview");
const resolvedPreviewNode = document.querySelector("#resolved-preview-url");
const resolvedRecordNode = document.querySelector("#resolved-record-url");
const recordUrlWarning = document.querySelector("#record-url-warning");
const probeDetailsWrap = document.querySelector("#probe-details-wrap");
const probeDetails = document.querySelector("#probe-details");
const probeCommand = document.querySelector("#probe-command");
const probeDetail1Label = document.querySelector("#probe-detail-1-label");
const probeDetail1Value = document.querySelector("#probe-detail-1-value");
const probeDetail2Label = document.querySelector("#probe-detail-2-label");
const probeDetail2Value = document.querySelector("#probe-detail-2-value");
const probeDetail3Label = document.querySelector("#probe-detail-3-label");
const probeDetail3Value = document.querySelector("#probe-detail-3-value");
const probeButton = document.querySelector("#probe-camera-button");
const goproPreviewUrlWrap = document.querySelector("#camera-preview-url-wrap");

const fields = {
  editingCameraId: document.querySelector("#editing-camera-id"),
  name: document.querySelector("#camera-name"),
  id: document.querySelector("#camera-id"),
  enabled: document.querySelector("#camera-enabled"),
  outputSubdir: document.querySelector("#camera-output-subdir"),
  description: document.querySelector("#camera-description"),
  mode: document.querySelector("#camera-mode"),
  go2rtcBaseUrl: document.querySelector("#camera-go2rtc-base-url"),
  streamName: document.querySelector("#camera-stream-name"),
  previewUrl: document.querySelector("#camera-preview-url"),
  recordUrl: document.querySelector("#camera-record-url"),
  goproHost: document.querySelector("#camera-gopro-host"),
  previewMode: document.querySelector("#camera-preview-mode"),
  goproPreviewUrl: document.querySelector("#camera-gopro-preview-url"),
  autoDownload: document.querySelector("#camera-auto-download"),
  downloadTimeoutSeconds: document.querySelector("#camera-download-timeout"),
  fileWaitSeconds: document.querySelector("#camera-file-wait"),
};

function slugifyCameraId(value) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "") || "camera";
}

function normalizeGo2RtcBaseUrl(value) {
  if (!value) {
    return "";
  }
  if (value.includes("://")) {
    return value.trim();
  }
  return `http://${value.trim()}`;
}

function resolveUrls(draft) {
  if (draft.mode === "gopro") {
    return {
      preview_url: draft.preview_mode === "external_link" ? (draft.preview_url || "").trim() : "",
      record_url: "GoPro API-controlled recording",
    };
  }

  const previewUrlManual = (draft.preview_url || "").trim();
  const recordUrlManual = (draft.record_url || "").trim();
  let generatedPreview = "";
  let generatedRecord = "";

  if (draft.go2rtc_base_url) {
    try {
      const base = new URL(normalizeGo2RtcBaseUrl(draft.go2rtc_base_url));
      const streamName = (draft.stream_name || "cam").trim() || "cam";
      const basePath = base.pathname && base.pathname !== "/" ? base.pathname.replace(/\/$/, "") : "";
      generatedPreview = `${base.protocol}//${base.host}${basePath}/stream.html?src=${encodeURIComponent(streamName)}`;
      generatedRecord = `rtsp://${base.hostname}:8554/${streamName}`;
    } catch (_error) {
      generatedPreview = "";
      generatedRecord = "";
    }
  }

  return {
    preview_url: previewUrlManual || generatedPreview || "",
    record_url: recordUrlManual || generatedRecord || "",
  };
}

function looksLikePreviewStream(url) {
  if (!url) {
    return false;
  }

  const normalized = url.toLowerCase();
  return [
    "stream.html",
    "mjpeg",
    "snapshot",
    "?src=",
    "&src=",
  ].some((pattern) => normalized.includes(pattern));
}

function cameraPayload() {
  const payload = {
    name: fields.name.value.trim(),
    id: fields.id.value.trim(),
    enabled: fields.enabled.checked,
    output_subdir: fields.outputSubdir.value.trim(),
    description: fields.description.value.trim(),
    mode: fields.mode.value,
    go2rtc_base_url: fields.go2rtcBaseUrl.value.trim(),
    stream_name: fields.streamName.value.trim(),
    preview_url: fields.previewUrl.value.trim(),
    record_url: fields.recordUrl.value.trim(),
    gopro_host: fields.goproHost.value.trim(),
    preview_mode: fields.previewMode.value,
    auto_download_after_stop: fields.autoDownload.checked,
    download_timeout_seconds: Number(fields.downloadTimeoutSeconds.value || 120),
    file_stabilization_wait_seconds: Number(fields.fileWaitSeconds.value || 5),
  };

  if (payload.mode === "go2rtc_helper") {
    payload.preview_url = "";
    payload.record_url = "";
    payload.gopro_host = "";
    payload.preview_mode = "none";
  } else if (payload.mode === "manual_urls") {
    payload.go2rtc_base_url = "";
    payload.stream_name = "";
    payload.gopro_host = "";
    payload.preview_mode = "none";
  } else if (payload.mode === "gopro") {
    payload.go2rtc_base_url = "";
    payload.stream_name = "";
    payload.record_url = "";
    payload.preview_url = fields.goproPreviewUrl.value.trim();
  }

  return payload;
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
    throw new Error(payload && payload.detail ? payload.detail : "Request failed");
  }

  return payload;
}

function setModeVisibility() {
  const go2rtcFields = document.querySelector("#go2rtc-fields");
  const manualFields = document.querySelector("#manual-fields");
  const goproFields = document.querySelector("#gopro-fields");
  const mode = fields.mode.value;

  go2rtcFields.hidden = mode !== "go2rtc_helper";
  manualFields.hidden = mode !== "manual_urls";
  goproFields.hidden = mode !== "gopro";
  goproPreviewUrlWrap.hidden = mode !== "gopro" || fields.previewMode.value !== "external_link";
  updateProbeButtonLabel();
}

function updateProbeButtonLabel() {
  probeButton.textContent = fields.mode.value === "gopro" ? "Test GoPro" : "Test Stream";
}

function updatePreviewPanel() {
  const draft = cameraPayload();
  const resolved = resolveUrls(draft);
  resolvedPreviewNode.textContent = resolved.preview_url || "Preview unavailable";
  resolvedRecordNode.textContent = resolved.record_url || "--";
  updateRecordUrlWarning(resolved.record_url);

  if (draft.mode === "gopro") {
    if (draft.preview_mode === "external_link" && resolved.preview_url) {
      previewNode.innerHTML = `
        <div class="preview-link-state">
          <p>GoPro preview opens externally for this configuration.</p>
          <a class="control-button control-button--secondary table-link" href="${resolved.preview_url}" target="_blank" rel="noopener noreferrer">
            Open Preview
          </a>
        </div>
      `;
    } else {
      previewNode.innerHTML = '<div class="no-preview">Preview unavailable in-app for this GoPro configuration</div>';
    }
    return;
  }

  if (resolved.preview_url) {
    previewNode.innerHTML = `<iframe title="Camera preview" src="${resolved.preview_url}" loading="lazy" allowfullscreen></iframe>`;
  } else {
    previewNode.innerHTML = '<div class="no-preview">Preview unavailable</div>';
  }
}

function updateRecordUrlWarning(recordUrl) {
  if (!recordUrlWarning) {
    return false;
  }
  if (fields.mode.value !== "manual_urls") {
    recordUrlWarning.hidden = true;
    return false;
  }

  const showWarning = looksLikePreviewStream(recordUrl);
  recordUrlWarning.hidden = !showWarning;
  return showWarning;
}

function resetProbeResult() {
  probeSummary.textContent = "Use Test Stream to verify recording compatibility.";
  probeStatus.textContent = "--";
  probeError.hidden = true;
  probeError.textContent = "";
  probeDetail1Label.textContent = "Codec";
  probeDetail1Value.textContent = "--";
  probeDetail2Label.textContent = "Resolution";
  probeDetail2Value.textContent = "--";
  probeDetail3Label.textContent = "Stream Type";
  probeDetail3Value.textContent = "--";
  document.querySelector("#probe-reachable").textContent = "--";
  probeDetailsWrap.hidden = true;
  probeDetailsWrap.open = false;
  probeDetails.textContent = "";
  probeCommand.textContent = "";
}

function updateProbeResult(result, mode) {
  if (mode === "gopro") {
    probeSummary.textContent = result.message || (result.reachable ? "GoPro reachable." : "GoPro unreachable.");
    probeStatus.textContent = result.reachable ? "ok" : "error";
    document.querySelector("#probe-reachable").textContent = result.reachable ? "yes" : "no";
    probeDetail1Label.textContent = "HTTP Status";
    probeDetail1Value.textContent = result.http_status || "--";
    probeDetail2Label.textContent = "Battery";
    probeDetail2Value.textContent = result.battery !== null && result.battery !== undefined ? String(result.battery) : "--";
    probeDetail3Label.textContent = "Recording";
    probeDetail3Value.textContent = result.recording === null || result.recording === undefined ? "--" : (result.recording ? "yes" : "no");
  } else {
    probeSummary.textContent = result.message || (
      result.reachable ? "ffprobe reached the stream." : "ffprobe could not verify the stream."
    );
    probeStatus.textContent = result.diagnostic_status || "--";
    document.querySelector("#probe-reachable").textContent = result.reachable ? "yes" : "no";
    probeDetail1Label.textContent = "Codec";
    probeDetail1Value.textContent = result.codec || "--";
    probeDetail2Label.textContent = "Resolution";
    probeDetail2Value.textContent =
      result.width && result.height ? `${result.width}x${result.height}` : "--";
    probeDetail3Label.textContent = "Stream Type";
    probeDetail3Value.textContent = result.stream_type || "--";
  }

  if (result.error && (!(mode === "gopro") ? result.diagnostic_status !== "ok" : true)) {
    probeError.hidden = false;
    probeError.textContent = result.error;
  } else {
    probeError.hidden = true;
    probeError.textContent = "";
  }

  const metaParts = [];
  if (result.command) {
    metaParts.push(`Command: ${result.command}`);
  }

  const rawStatusDetails = result.raw_status && Object.keys(result.raw_status).length
    ? JSON.stringify(result.raw_status, null, 2)
    : "";
  const detailText = result.details || rawStatusDetails || "";
  const hasDetails = Boolean(detailText || metaParts.length);
  probeDetailsWrap.hidden = !hasDetails;
  if (hasDetails) {
    probeCommand.textContent = metaParts.join(" | ");
    probeDetails.textContent = detailText;
  } else {
    probeDetailsWrap.open = false;
    probeCommand.textContent = "";
    probeDetails.textContent = "";
  }
}

function renderCameraList() {
  listNode.innerHTML = "";
  listEmptyNode.hidden = cameras.length > 0;

  cameras.forEach((camera) => {
    const detail = camera.mode === "gopro"
      ? `GoPro host: ${camera.gopro_host || "--"}`
      : `Output dir: ${camera.output_subdir}`;
    const row = document.createElement("article");
    row.className = "camera-list__item";
    row.innerHTML = `
      <div>
        <h3>${camera.name}</h3>
        <p>${camera.id}</p>
        <p>${detail}</p>
      </div>
      <dl class="camera-list__meta">
        <div><dt>Enabled</dt><dd>${camera.enabled ? "yes" : "no"}</dd></div>
        <div><dt>Mode</dt><dd>${camera.mode}</dd></div>
      </dl>
      <div class="camera-list__actions">
        <button type="button" class="control-button control-button--secondary" data-action="edit" data-camera-id="${camera.id}">Edit</button>
        <button type="button" class="control-button control-button--danger" data-action="delete" data-camera-id="${camera.id}">Delete</button>
      </div>
    `;
    listNode.appendChild(row);
  });
}

function beginNewCamera() {
  editingCameraId = null;
  idTouched = false;
  outputSubdirTouched = false;
  formTitle.textContent = "New Camera";
  fields.editingCameraId.value = "";
  fields.name.value = "";
  fields.id.value = "";
  fields.enabled.checked = true;
  fields.outputSubdir.value = "";
  fields.description.value = "";
  fields.mode.value = "go2rtc_helper";
  fields.go2rtcBaseUrl.value = "";
  fields.streamName.value = "cam";
  fields.previewUrl.value = "";
  fields.recordUrl.value = "";
  fields.goproHost.value = "";
  fields.previewMode.value = "none";
  fields.goproPreviewUrl.value = "";
  fields.autoDownload.checked = true;
  fields.downloadTimeoutSeconds.value = "120";
  fields.fileWaitSeconds.value = "5";
  document.querySelector("#delete-camera-button").hidden = true;
  formError.hidden = true;
  formError.textContent = "";
  updateRecordUrlWarning("");
  setModeVisibility();
  updatePreviewPanel();
  resetProbeResult();
}

function beginEditCamera(camera) {
  editingCameraId = camera.id;
  idTouched = true;
  outputSubdirTouched = true;
  formTitle.textContent = `Edit ${camera.name}`;
  fields.editingCameraId.value = camera.id;
  fields.name.value = camera.name;
  fields.id.value = camera.id;
  fields.enabled.checked = camera.enabled;
  fields.outputSubdir.value = camera.output_subdir || camera.id;
  fields.description.value = camera.description || "";
  fields.mode.value = camera.mode;
  fields.go2rtcBaseUrl.value = camera.go2rtc_base_url || "";
  fields.streamName.value = camera.stream_name || "cam";
  fields.previewUrl.value = camera.preview_url || "";
  fields.recordUrl.value = camera.record_url || "";
  fields.goproHost.value = camera.gopro_host || "";
  fields.previewMode.value = camera.preview_mode || "none";
  fields.goproPreviewUrl.value = camera.preview_url || "";
  fields.autoDownload.checked = camera.auto_download_after_stop !== false;
  fields.downloadTimeoutSeconds.value = String(camera.download_timeout_seconds || 120);
  fields.fileWaitSeconds.value = String(camera.file_stabilization_wait_seconds || 5);
  document.querySelector("#delete-camera-button").hidden = false;
  formError.hidden = true;
  formError.textContent = "";
  setModeVisibility();
  updatePreviewPanel();
  resetProbeResult();
}

async function loadCameras() {
  const payload = await fetchJson("/api/cameras");
  cameras = payload.cameras || [];
  renderCameraList();

  if (editingCameraId) {
    const current = cameras.find((camera) => camera.id === editingCameraId);
    if (current) {
      beginEditCamera(current);
      return;
    }
    editingCameraId = null;
  }

  if (!editingCameraId && !fields.name.value) {
    beginNewCamera();
  }
}

async function saveCamera(event) {
  event.preventDefault();
  formError.hidden = true;
  formError.textContent = "";
  const payload = cameraPayload();
  const expectedId = payload.id || slugifyCameraId(payload.name);
  updateRecordUrlWarning(resolveUrls(payload).record_url);

  try {
    let response = null;
    if (editingCameraId) {
      response = await fetchJson(`/api/cameras/${editingCameraId}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    } else {
      response = await fetchJson("/api/cameras", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    }
    cameras = response.cameras || [];
    renderCameraList();
    const saved = cameras.find((camera) => camera.id === expectedId) ||
      cameras.find((camera) => camera.name === payload.name);
    if (saved) {
      beginEditCamera(saved);
    } else {
      beginNewCamera();
    }
  } catch (error) {
    formError.hidden = false;
    formError.textContent = error.message;
  }
}

async function deleteCamera(cameraId) {
  const confirmed = window.confirm(`Delete camera "${cameraId}" from config?`);
  if (!confirmed) {
    return;
  }

  try {
    await fetchJson(`/api/cameras/${cameraId}`, { method: "DELETE" });
    editingCameraId = null;
    await loadCameras();
    beginNewCamera();
  } catch (error) {
    formError.hidden = false;
    formError.textContent = error.message;
  }
}

async function probeCamera() {
  resetProbeResult();
  const payload = cameraPayload();
  updateRecordUrlWarning(resolveUrls(payload).record_url);
  try {
    const url = payload.mode === "gopro" ? "/api/gopro/test" : "/api/camera/probe";
    const result = await fetchJson(url, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    updateProbeResult(result, payload.mode);
  } catch (error) {
    probeError.hidden = false;
    probeError.textContent = error.message;
  }
}

fields.name.addEventListener("input", () => {
  if (!idTouched) {
    fields.id.value = slugifyCameraId(fields.name.value);
  }
  if (!outputSubdirTouched) {
    fields.outputSubdir.value = fields.id.value || slugifyCameraId(fields.name.value);
  }
  updatePreviewPanel();
});

fields.id.addEventListener("input", () => {
  idTouched = true;
  if (!outputSubdirTouched) {
    fields.outputSubdir.value = fields.id.value.trim();
  }
});

fields.outputSubdir.addEventListener("input", () => {
  outputSubdirTouched = true;
});

fields.mode.addEventListener("change", () => {
  setModeVisibility();
  updatePreviewPanel();
  resetProbeResult();
});

fields.previewMode.addEventListener("change", () => {
  setModeVisibility();
  updatePreviewPanel();
});

[
  fields.go2rtcBaseUrl,
  fields.streamName,
  fields.previewUrl,
  fields.recordUrl,
  fields.goproHost,
  fields.goproPreviewUrl,
].forEach((field) => {
  field.addEventListener("input", updatePreviewPanel);
});

form.addEventListener("submit", saveCamera);
document.querySelector("#new-camera-button").addEventListener("click", beginNewCamera);
document.querySelector("#cancel-edit-button").addEventListener("click", beginNewCamera);
document.querySelector("#delete-camera-button").addEventListener("click", () => {
  if (editingCameraId) {
    deleteCamera(editingCameraId);
  }
});
probeButton.addEventListener("click", probeCamera);

listNode.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLButtonElement)) {
    return;
  }

  const cameraId = target.dataset.cameraId;
  const action = target.dataset.action;
  const camera = cameras.find((item) => item.id === cameraId);
  if (!camera) {
    return;
  }

  if (action === "edit") {
    beginEditCamera(camera);
  } else if (action === "delete") {
    deleteCamera(camera.id);
  }
});

beginNewCamera();
loadCameras();
