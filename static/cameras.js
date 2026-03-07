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
const previewNode = document.querySelector("#editor-preview");
const resolvedPreviewNode = document.querySelector("#resolved-preview-url");
const resolvedRecordNode = document.querySelector("#resolved-record-url");

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
  };

  if (payload.mode === "go2rtc_helper") {
    payload.preview_url = "";
    payload.record_url = "";
  } else {
    payload.go2rtc_base_url = "";
    payload.stream_name = "";
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
  const usingGo2Rtc = fields.mode.value === "go2rtc_helper";

  go2rtcFields.hidden = !usingGo2Rtc;
  manualFields.hidden = usingGo2Rtc;
}

function updatePreviewPanel() {
  const draft = cameraPayload();
  const resolved = resolveUrls(draft);
  resolvedPreviewNode.textContent = resolved.preview_url || "Preview unavailable";
  resolvedRecordNode.textContent = resolved.record_url || "--";

  if (resolved.preview_url) {
    previewNode.innerHTML = `<iframe title="Camera preview" src="${resolved.preview_url}" loading="lazy" allowfullscreen></iframe>`;
  } else {
    previewNode.innerHTML = '<div class="no-preview">Preview unavailable</div>';
  }
}

function resetProbeResult() {
  probeSummary.textContent = "Use Test Stream to verify recording compatibility.";
  probeError.hidden = true;
  probeError.textContent = "";
  document.querySelector("#probe-reachable").textContent = "--";
  document.querySelector("#probe-codec").textContent = "--";
  document.querySelector("#probe-resolution").textContent = "--";
  document.querySelector("#probe-stream-type").textContent = "--";
}

function updateProbeResult(result) {
  probeSummary.textContent = result.reachable
    ? "ffprobe reached the stream."
    : "ffprobe could not verify the stream.";
  document.querySelector("#probe-reachable").textContent = result.reachable ? "yes" : "no";
  document.querySelector("#probe-codec").textContent = result.codec || "--";
  document.querySelector("#probe-resolution").textContent =
    result.width && result.height ? `${result.width}x${result.height}` : "--";
  document.querySelector("#probe-stream-type").textContent = result.stream_type || "--";
  if (result.error) {
    probeError.hidden = false;
    probeError.textContent = result.error;
  } else {
    probeError.hidden = true;
    probeError.textContent = "";
  }
}

function renderCameraList() {
  listNode.innerHTML = "";
  listEmptyNode.hidden = cameras.length > 0;

  cameras.forEach((camera) => {
    const row = document.createElement("article");
    row.className = "camera-list__item";
    row.innerHTML = `
      <div>
        <h3>${camera.name}</h3>
        <p>${camera.id}</p>
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
  document.querySelector("#delete-camera-button").hidden = true;
  formError.hidden = true;
  formError.textContent = "";
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
  try {
    const payload = await fetchJson("/api/camera/probe", {
      method: "POST",
      body: JSON.stringify(cameraPayload()),
    });
    updateProbeResult(payload);
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
});

[
  fields.go2rtcBaseUrl,
  fields.streamName,
  fields.previewUrl,
  fields.recordUrl,
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
document.querySelector("#probe-camera-button").addEventListener("click", probeCamera);

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
