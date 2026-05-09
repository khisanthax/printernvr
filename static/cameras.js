let printers = [];
let editingPrinterId = null;
let editingCameraId = null;
let idTouched = false;
let outputSubdirTouched = false;

const $ = (selector) => document.querySelector(selector);
const printerList = $("#printer-list");
const printerEmpty = $("#printer-list-empty");
const configError = $("#config-error");
const printerEditor = $("#printer-editor");
const cameraEditor = $("#camera-editor");
const printerError = $("#printer-form-error");
const cameraError = $("#camera-form-error");
const recordUrlWarning = $("#record-url-warning");
const previewNode = $("#editor-preview");
const resolvedPreviewNode = $("#resolved-preview-url");
const resolvedRecordNode = $("#resolved-record-url");

const probe = {
  summary: $(".probe-result__summary"),
  status: $("#probe-status"),
  reachable: $("#probe-reachable"),
  error: $("#probe-error"),
  detailsWrap: $("#probe-details-wrap"),
  details: $("#probe-details"),
  command: $("#probe-command"),
  label1: $("#probe-detail-1-label"),
  value1: $("#probe-detail-1-value"),
  label2: $("#probe-detail-2-label"),
  value2: $("#probe-detail-2-value"),
  label3: $("#probe-detail-3-label"),
  value3: $("#probe-detail-3-value"),
};

const printerFields = {
  editingId: $("#editing-printer-id"),
  name: $("#printer-name"),
  id: $("#printer-id"),
  enabled: $("#printer-enabled"),
  moonrakerUrl: $("#printer-moonraker-url"),
  displayOrder: $("#printer-display-order"),
  defaultCamera: $("#printer-default-camera"),
};

const cameraFields = {
  editingId: $("#editing-camera-id"),
  editingPrinterId: $("#editing-camera-printer-id"),
  printerId: $("#camera-printer-id"),
  mode: $("#camera-mode"),
  name: $("#camera-name"),
  id: $("#camera-id"),
  enabled: $("#camera-enabled"),
  displayOrder: $("#camera-display-order"),
  outputSubdir: $("#camera-output-subdir"),
  description: $("#camera-description"),
  go2rtcBaseUrl: $("#camera-go2rtc-base-url"),
  streamName: $("#camera-stream-name"),
  previewUrl: $("#camera-preview-url"),
  recordUrl: $("#camera-record-url"),
  goproHost: $("#camera-gopro-host"),
  previewMode: $("#camera-preview-mode"),
  goproPreviewUrl: $("#camera-gopro-preview-url"),
  autoDownload: $("#camera-auto-download"),
  downloadTimeoutSeconds: $("#camera-download-timeout"),
  fileWaitSeconds: $("#camera-file-wait"),
};

function slugifyId(value, fallback = "item") {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/_+/g, "_").replace(/^_+|_+$/g, "") || fallback;
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function safeNumber(value) {
  return value === "" || value === null || value === undefined ? null : Number(value);
}

function sortByOrderNameId(items) {
  return [...items].sort((a, b) => {
    const orderDiff = (a.display_order ?? 9999) - (b.display_order ?? 9999);
    if (orderDiff !== 0) return orderDiff;
    const nameDiff = String(a.name || "").localeCompare(String(b.name || ""));
    return nameDiff || String(a.id || "").localeCompare(String(b.id || ""));
  });
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
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

function showError(node, message) {
  node.hidden = false;
  node.textContent = message;
}

function clearError(node) {
  node.hidden = true;
  node.textContent = "";
}

function findPrinter(printerId) {
  return printers.find((printer) => printer.id === printerId) || null;
}

function findCamera(cameraId) {
  for (const printer of printers) {
    const camera = (printer.cameras || []).find((item) => item.id === cameraId);
    if (camera) return { printer, camera };
  }
  return null;
}

function allCameraIds(exceptCameraId = null) {
  return new Set(
    printers.flatMap((printer) => printer.cameras || [])
      .filter((camera) => camera.id !== exceptCameraId)
      .map((camera) => camera.id),
  );
}

function normalizeGo2RtcBaseUrl(value) {
  if (!value) return "";
  return value.includes("://") ? value.trim() : `http://${value.trim()}`;
}

function resolveUrls(camera) {
  if (!camera) return { preview_url: "", record_url: "" };
  if (camera.mode === "gopro") {
    return {
      preview_url: camera.preview_mode === "external_link" ? (camera.preview_url || "") : "",
      record_url: "GoPro API-controlled recording",
    };
  }

  let generatedPreview = "";
  let generatedRecord = "";
  if (camera.go2rtc_base_url) {
    try {
      const base = new URL(normalizeGo2RtcBaseUrl(camera.go2rtc_base_url));
      const streamName = (camera.stream_name || "cam").trim() || "cam";
      const basePath = base.pathname && base.pathname !== "/" ? base.pathname.replace(/\/$/, "") : "";
      generatedPreview = `${base.protocol}//${base.host}${basePath}/stream.html?src=${encodeURIComponent(streamName)}`;
      generatedRecord = `rtsp://${base.hostname}:8554/${streamName}`;
    } catch (_error) {
      generatedPreview = "";
      generatedRecord = "";
    }
  }

  return {
    preview_url: (camera.preview_url || "").trim() || generatedPreview,
    record_url: (camera.record_url || "").trim() || generatedRecord,
  };
}

function looksLikePreviewStream(url) {
  const normalized = String(url || "").toLowerCase();
  return ["stream.html", "mjpeg", "snapshot", "?src=", "&src="].some((pattern) => normalized.includes(pattern));
}

function cameraFromForm() {
  const mode = cameraFields.mode.value;
  const camera = {
    id: cameraFields.id.value.trim(),
    name: cameraFields.name.value.trim(),
    enabled: cameraFields.enabled.checked,
    description: cameraFields.description.value.trim() || null,
    mode,
    display_order: safeNumber(cameraFields.displayOrder.value),
    output_subdir: cameraFields.outputSubdir.value.trim() || cameraFields.id.value.trim(),
    go2rtc_base_url: cameraFields.go2rtcBaseUrl.value.trim() || null,
    stream_name: cameraFields.streamName.value.trim() || null,
    preview_url: cameraFields.previewUrl.value.trim() || null,
    record_url: cameraFields.recordUrl.value.trim() || null,
    gopro_host: cameraFields.goproHost.value.trim() || null,
    preview_mode: cameraFields.previewMode.value || "none",
    auto_download_after_stop: cameraFields.autoDownload.checked,
    download_timeout_seconds: Number(cameraFields.downloadTimeoutSeconds.value || 120),
    file_stabilization_wait_seconds: Number(cameraFields.fileWaitSeconds.value || 5),
  };

  if (mode === "go2rtc_helper") {
    camera.preview_url = null;
    camera.record_url = null;
    camera.gopro_host = null;
    camera.preview_mode = null;
  } else if (mode === "manual_urls") {
    camera.go2rtc_base_url = null;
    camera.stream_name = null;
    camera.gopro_host = null;
    camera.preview_mode = null;
  } else if (mode === "gopro") {
    camera.go2rtc_base_url = null;
    camera.stream_name = null;
    camera.record_url = null;
    camera.preview_url = cameraFields.goproPreviewUrl.value.trim() || null;
  }
  return camera;
}

function probePayloadFromCamera(printer, camera) {
  return {
    name: camera.name,
    id: camera.id,
    enabled: camera.enabled !== false,
    output_subdir: camera.output_subdir || camera.id,
    description: camera.description || "",
    mode: camera.mode || "manual_urls",
    printer_name: printer.name,
    printer_id: printer.id,
    default_live_view: printer.default_camera_id === camera.id,
    moonraker_url: printer.moonraker_url || "",
    display_order: camera.display_order ?? null,
    go2rtc_base_url: camera.go2rtc_base_url || "",
    stream_name: camera.stream_name || "",
    preview_url: camera.preview_url || "",
    record_url: camera.record_url || "",
    gopro_host: camera.gopro_host || "",
    preview_mode: camera.preview_mode || "none",
    auto_download_after_stop: camera.auto_download_after_stop !== false,
    download_timeout_seconds: camera.download_timeout_seconds || 120,
    file_stabilization_wait_seconds: camera.file_stabilization_wait_seconds || 5,
  };
}

function setModeVisibility() {
  const mode = cameraFields.mode.value;
  $("#go2rtc-fields").hidden = mode !== "go2rtc_helper";
  $("#manual-fields").hidden = mode !== "manual_urls";
  $("#gopro-fields").hidden = mode !== "gopro";
  $("#camera-preview-url-wrap").hidden = mode !== "gopro" || cameraFields.previewMode.value !== "external_link";
  $("#probe-camera-button").textContent = mode === "gopro" ? "Test GoPro" : "Test Stream";
}

function updateRecordUrlWarning(recordUrl) {
  if (recordUrlWarning) {
    recordUrlWarning.hidden = cameraFields.mode.value !== "manual_urls" || !looksLikePreviewStream(recordUrl);
  }
}

function updatePreviewPanel(camera = cameraFromForm()) {
  const resolved = resolveUrls(camera);
  resolvedPreviewNode.textContent = resolved.preview_url || "Preview unavailable";
  resolvedRecordNode.textContent = resolved.record_url || "--";
  updateRecordUrlWarning(resolved.record_url);

  if (camera.mode === "gopro") {
    if (camera.preview_mode === "external_link" && resolved.preview_url) {
      previewNode.innerHTML = `<div class="preview-link-state"><p>Deprecated GoPro preview opens externally.</p><a class="control-button control-button--secondary table-link" href="${escapeHtml(resolved.preview_url)}" target="_blank" rel="noopener noreferrer">Open Preview</a></div>`;
    } else {
      previewNode.innerHTML = '<div class="no-preview">Preview unavailable for this deprecated GoPro configuration</div>';
    }
    return;
  }

  previewNode.innerHTML = resolved.preview_url
    ? `<iframe title="Camera preview" src="${escapeHtml(resolved.preview_url)}" loading="lazy" allowfullscreen></iframe>`
    : '<div class="no-preview">Preview unavailable</div>';
}

function resetProbeResult() {
  probe.summary.textContent = "Use Test Stream to verify recording compatibility.";
  probe.status.textContent = "--";
  probe.reachable.textContent = "--";
  probe.error.hidden = true;
  probe.error.textContent = "";
  probe.label1.textContent = "Codec";
  probe.value1.textContent = "--";
  probe.label2.textContent = "Resolution";
  probe.value2.textContent = "--";
  probe.label3.textContent = "Stream Type";
  probe.value3.textContent = "--";
  probe.detailsWrap.hidden = true;
  probe.detailsWrap.open = false;
  probe.details.textContent = "";
  probe.command.textContent = "";
}

function updateProbeResult(result, mode) {
  if (mode === "gopro") {
    probe.summary.textContent = result.message || (result.reachable ? "GoPro reachable." : "GoPro unreachable.");
    probe.status.textContent = result.reachable ? "ok" : "error";
    probe.reachable.textContent = result.reachable ? "yes" : "no";
    probe.label1.textContent = "HTTP Status";
    probe.value1.textContent = result.http_status || "--";
    probe.label2.textContent = "Battery";
    probe.value2.textContent = result.battery !== null && result.battery !== undefined ? String(result.battery) : "--";
    probe.label3.textContent = "Recording";
    probe.value3.textContent = result.recording === null || result.recording === undefined ? "--" : (result.recording ? "yes" : "no");
  } else {
    probe.summary.textContent = result.message || (result.reachable ? "ffprobe reached the stream." : "ffprobe could not verify the stream.");
    probe.status.textContent = result.diagnostic_status || "--";
    probe.reachable.textContent = result.reachable ? "yes" : "no";
    probe.label1.textContent = "Codec";
    probe.value1.textContent = result.codec || "--";
    probe.label2.textContent = "Resolution";
    probe.value2.textContent = result.width && result.height ? `${result.width}x${result.height}` : "--";
    probe.label3.textContent = "Stream Type";
    probe.value3.textContent = result.stream_type || "--";
  }

  if (result.error && (mode === "gopro" || result.diagnostic_status !== "ok")) {
    showError(probe.error, result.error);
  }

  const rawStatusDetails = result.raw_status && Object.keys(result.raw_status).length ? JSON.stringify(result.raw_status, null, 2) : "";
  const detailText = result.details || rawStatusDetails || "";
  probe.detailsWrap.hidden = !(detailText || result.command);
  probe.command.textContent = result.command ? `Command: ${result.command}` : "";
  probe.details.textContent = detailText;
}

function renderPrinterOptions(selectedPrinterId = "") {
  cameraFields.printerId.innerHTML = "";
  sortByOrderNameId(printers).forEach((printer) => {
    const option = document.createElement("option");
    option.value = printer.id;
    option.textContent = `${printer.name} (${printer.id})`;
    option.selected = printer.id === selectedPrinterId;
    cameraFields.printerId.appendChild(option);
  });
}

function renderDefaultCameraOptions(printer, selectedCameraId = "") {
  printerFields.defaultCamera.innerHTML = "";
  const none = document.createElement("option");
  none.value = "";
  none.textContent = printer && printer.cameras && printer.cameras.length ? "Auto fallback" : "No cameras yet";
  printerFields.defaultCamera.appendChild(none);

  if (!printer || !printer.cameras || !printer.cameras.length) {
    printerFields.defaultCamera.disabled = true;
    return;
  }
  printerFields.defaultCamera.disabled = false;
  sortByOrderNameId(printer.cameras).forEach((camera) => {
    const option = document.createElement("option");
    option.value = camera.id;
    option.textContent = `${camera.name} (${camera.id})`;
    option.selected = camera.id === selectedCameraId;
    printerFields.defaultCamera.appendChild(option);
  });
}

function ensurePrinterDefault(printer) {
  const cameras = sortByOrderNameId(printer.cameras || []);
  if (!cameras.length) {
    printer.default_camera_id = null;
    return;
  }
  if (printer.default_camera_id && cameras.some((camera) => camera.id === printer.default_camera_id)) return;
  printer.default_camera_id = (cameras.find((camera) => camera.enabled !== false) || cameras[0]).id;
}

function renderCameraRow(printer, camera) {
  const resolved = resolveUrls(camera);
  const isDefault = printer.default_camera_id === camera.id;
  return `
    <article class="nested-camera-row">
      <div>
        <h4>${escapeHtml(camera.name)}${isDefault ? ' <span class="status-pill">Default</span>' : ""}</h4>
        <p>${escapeHtml(camera.id)} · ${camera.enabled === false ? "disabled" : "enabled"} · ${escapeHtml(camera.mode || "manual_urls")}</p>
      </div>
      <dl class="camera-list__meta">
        <div><dt>Preview</dt><dd title="${escapeHtml(resolved.preview_url)}">${escapeHtml(resolved.preview_url || "--")}</dd></div>
        <div><dt>Record</dt><dd title="${escapeHtml(resolved.record_url)}">${escapeHtml(resolved.record_url || "--")}</dd></div>
        <div><dt>Order</dt><dd>${camera.display_order ?? "--"}</dd></div>
      </dl>
      <div class="camera-list__actions">
        <button type="button" class="control-button control-button--secondary" data-action="edit-camera" data-camera-id="${escapeHtml(camera.id)}">Edit</button>
        <button type="button" class="control-button control-button--secondary" data-action="test-camera" data-camera-id="${escapeHtml(camera.id)}">Test</button>
        <button type="button" class="control-button control-button--danger" data-action="delete-camera" data-camera-id="${escapeHtml(camera.id)}">Delete</button>
      </div>
    </article>
  `;
}

function renderPrinterList() {
  printerList.innerHTML = "";
  printerEmpty.hidden = printers.length > 0;
  sortByOrderNameId(printers).forEach((printer) => {
    ensurePrinterDefault(printer);
    const cameras = sortByOrderNameId(printer.cameras || []);
    const defaultCamera = cameras.find((camera) => camera.id === printer.default_camera_id);
    const card = document.createElement("article");
    card.className = "printer-config-card";
    card.innerHTML = `
      <header class="printer-config-card__header">
        <div>
          <h3>${escapeHtml(printer.name)}</h3>
          <p>${escapeHtml(printer.id)} · ${printer.enabled === false ? "disabled" : "enabled"}</p>
        </div>
        <div class="camera-list__actions">
          <button type="button" class="control-button control-button--secondary" data-action="edit-printer" data-printer-id="${escapeHtml(printer.id)}">Edit Printer</button>
          <button type="button" class="control-button" data-action="add-camera" data-printer-id="${escapeHtml(printer.id)}">Add Camera</button>
          <button type="button" class="control-button control-button--danger" data-action="delete-printer" data-printer-id="${escapeHtml(printer.id)}">Delete Printer</button>
        </div>
      </header>
      <dl class="camera-list__meta printer-config-card__meta">
        <div><dt>Moonraker</dt><dd>${escapeHtml(printer.moonraker_url || "--")}</dd></div>
        <div><dt>Order</dt><dd>${printer.display_order ?? "--"}</dd></div>
        <div><dt>Default</dt><dd>${defaultCamera ? escapeHtml(defaultCamera.name) : "--"}</dd></div>
        <div><dt>Views</dt><dd>${cameras.length}</dd></div>
      </dl>
      <div class="nested-camera-list">
        ${cameras.length ? cameras.map((camera) => renderCameraRow(printer, camera)).join("") : '<p class="form-helper">No cameras configured for this printer.</p>'}
      </div>
    `;
    printerList.appendChild(card);
  });
}

function beginNewPrinter() {
  editingPrinterId = null;
  idTouched = false;
  printerEditor.hidden = false;
  cameraEditor.hidden = true;
  $("#printer-form-title").textContent = "New Printer";
  printerFields.editingId.value = "";
  printerFields.name.value = "";
  printerFields.id.value = "";
  printerFields.enabled.checked = true;
  printerFields.moonrakerUrl.value = "";
  printerFields.displayOrder.value = "";
  renderDefaultCameraOptions(null);
  $("#delete-printer-button").hidden = true;
  clearError(printerError);
}

function beginEditPrinter(printerId) {
  const printer = findPrinter(printerId);
  if (!printer) return;
  editingPrinterId = printer.id;
  idTouched = true;
  printerEditor.hidden = false;
  cameraEditor.hidden = true;
  $("#printer-form-title").textContent = `Edit ${printer.name}`;
  printerFields.editingId.value = printer.id;
  printerFields.name.value = printer.name;
  printerFields.id.value = printer.id;
  printerFields.enabled.checked = printer.enabled !== false;
  printerFields.moonrakerUrl.value = printer.moonraker_url || "";
  printerFields.displayOrder.value = printer.display_order ?? "";
  renderDefaultCameraOptions(printer, printer.default_camera_id || "");
  $("#delete-printer-button").hidden = false;
  clearError(printerError);
}

function beginNewCamera(printerId) {
  if (!printers.length) {
    showError(configError, "Create a printer before adding cameras.");
    return;
  }
  editingCameraId = null;
  idTouched = false;
  outputSubdirTouched = false;
  printerEditor.hidden = true;
  cameraEditor.hidden = false;
  $("#camera-form-title").textContent = "New Camera View";
  renderPrinterOptions(printerId || printers[0].id);
  cameraFields.editingId.value = "";
  cameraFields.editingPrinterId.value = "";
  cameraFields.mode.value = "manual_urls";
  cameraFields.name.value = "";
  cameraFields.id.value = "";
  cameraFields.enabled.checked = true;
  cameraFields.displayOrder.value = "";
  cameraFields.outputSubdir.value = "";
  cameraFields.description.value = "";
  cameraFields.go2rtcBaseUrl.value = "";
  cameraFields.streamName.value = "cam";
  cameraFields.previewUrl.value = "";
  cameraFields.recordUrl.value = "";
  cameraFields.goproHost.value = "";
  cameraFields.previewMode.value = "none";
  cameraFields.goproPreviewUrl.value = "";
  cameraFields.autoDownload.checked = true;
  cameraFields.downloadTimeoutSeconds.value = "120";
  cameraFields.fileWaitSeconds.value = "5";
  $("#delete-camera-button").hidden = true;
  clearError(cameraError);
  setModeVisibility();
  updatePreviewPanel();
  resetProbeResult();
}

function beginEditCamera(cameraId) {
  const found = findCamera(cameraId);
  if (!found) return;
  const { printer, camera } = found;
  editingCameraId = camera.id;
  idTouched = true;
  outputSubdirTouched = true;
  printerEditor.hidden = true;
  cameraEditor.hidden = false;
  $("#camera-form-title").textContent = `Edit ${camera.name}`;
  renderPrinterOptions(printer.id);
  cameraFields.editingId.value = camera.id;
  cameraFields.editingPrinterId.value = printer.id;
  cameraFields.mode.value = camera.mode || "manual_urls";
  cameraFields.name.value = camera.name;
  cameraFields.id.value = camera.id;
  cameraFields.enabled.checked = camera.enabled !== false;
  cameraFields.displayOrder.value = camera.display_order ?? "";
  cameraFields.outputSubdir.value = camera.output_subdir || camera.id;
  cameraFields.description.value = camera.description || "";
  cameraFields.go2rtcBaseUrl.value = camera.go2rtc_base_url || "";
  cameraFields.streamName.value = camera.stream_name || "cam";
  cameraFields.previewUrl.value = camera.preview_url || "";
  cameraFields.recordUrl.value = camera.record_url || "";
  cameraFields.goproHost.value = camera.gopro_host || "";
  cameraFields.previewMode.value = camera.preview_mode || "none";
  cameraFields.goproPreviewUrl.value = camera.preview_url || "";
  cameraFields.autoDownload.checked = camera.auto_download_after_stop !== false;
  cameraFields.downloadTimeoutSeconds.value = String(camera.download_timeout_seconds || 120);
  cameraFields.fileWaitSeconds.value = String(camera.file_stabilization_wait_seconds || 5);
  $("#delete-camera-button").hidden = false;
  clearError(cameraError);
  setModeVisibility();
  updatePreviewPanel(camera);
  resetProbeResult();
}

function validateId(value, label) {
  if (!/^[A-Za-z0-9_-]+$/.test(value)) {
    throw new Error(`${label} must use only letters, numbers, underscores, and dashes.`);
  }
}

async function saveConfig() {
  const payload = { printers: printers.map((printer) => ({ ...printer, cameras: printer.cameras || [] })) };
  const response = await fetchJson("/api/cameras/config", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  printers = response.printers || [];
  renderPrinterList();
}

async function savePrinter(event) {
  event.preventDefault();
  clearError(printerError);
  clearError(configError);
  try {
    const printerId = printerFields.id.value.trim();
    const printerName = printerFields.name.value.trim();
    if (!printerId || !printerName) throw new Error("Printer id and name are required.");
    validateId(printerId, "Printer id");
    if (printers.some((printer) => printer.id === printerId && printer.id !== editingPrinterId)) {
      throw new Error(`Printer id '${printerId}' already exists.`);
    }

    let printer = editingPrinterId ? findPrinter(editingPrinterId) : null;
    if (!printer) {
      printer = { id: printerId, name: printerName, enabled: true, cameras: [] };
      printers.push(printer);
    }
    printer.id = printerId;
    printer.name = printerName;
    printer.enabled = printerFields.enabled.checked;
    printer.moonraker_url = printerFields.moonrakerUrl.value.trim() || null;
    printer.display_order = safeNumber(printerFields.displayOrder.value);
    printer.default_camera_id = printerFields.defaultCamera.value || null;
    printer.cameras = printer.cameras || [];
    ensurePrinterDefault(printer);
    await saveConfig();
    beginEditPrinter(printer.id);
  } catch (error) {
    showError(printerError, error.message);
  }
}

async function deletePrinter(printerId) {
  const printer = findPrinter(printerId);
  if (!printer) return;
  const cameraCount = (printer.cameras || []).length;
  const suffix = cameraCount ? ` This also removes ${cameraCount} nested camera config ${cameraCount === 1 ? "entry" : "entries"}.` : "";
  if (!window.confirm(`Delete printer '${printer.name}' from config?${suffix} Recordings are not deleted.`)) return;
  try {
    printers = printers.filter((item) => item.id !== printerId);
    await saveConfig();
    beginNewPrinter();
  } catch (error) {
    showError(configError, error.message);
  }
}

async function saveCamera(event) {
  event.preventDefault();
  clearError(cameraError);
  clearError(configError);
  const parentPrinterId = cameraFields.printerId.value;
  const newCamera = cameraFromForm();
  try {
    if (!parentPrinterId || !findPrinter(parentPrinterId)) throw new Error("Choose a parent printer.");
    if (!newCamera.id || !newCamera.name) throw new Error("Camera id and name are required.");
    validateId(newCamera.id, "Camera id");
    if (allCameraIds(editingCameraId).has(newCamera.id)) throw new Error(`Camera id '${newCamera.id}' already exists.`);
    if (newCamera.mode === "go2rtc_helper" && !newCamera.go2rtc_base_url) throw new Error("go2rtc Base URL is required.");
    if (newCamera.mode === "manual_urls" && !newCamera.preview_url && !newCamera.record_url) {
      throw new Error("Manual cameras need at least a preview URL or a record URL.");
    }
    if (newCamera.mode === "gopro" && !newCamera.gopro_host) throw new Error("GoPro host is required for deprecated GoPro compatibility cameras.");

    printers.forEach((printer) => {
      printer.cameras = (printer.cameras || []).filter((camera) => camera.id !== editingCameraId);
    });
    const parent = findPrinter(parentPrinterId);
    parent.cameras = parent.cameras || [];
    parent.cameras.push(newCamera);
    printers.forEach(ensurePrinterDefault);
    await saveConfig();
    beginEditCamera(newCamera.id);
  } catch (error) {
    showError(cameraError, error.message);
  }
}

async function deleteCamera(cameraId) {
  const found = findCamera(cameraId);
  if (!found) return;
  if (!window.confirm(`Delete camera '${found.camera.name}' from config? Recordings are not deleted.`)) return;
  try {
    found.printer.cameras = (found.printer.cameras || []).filter((camera) => camera.id !== cameraId);
    if (found.printer.default_camera_id === cameraId) found.printer.default_camera_id = null;
    ensurePrinterDefault(found.printer);
    await saveConfig();
    beginEditPrinter(found.printer.id);
  } catch (error) {
    showError(configError, error.message);
  }
}

async function probeCamera(cameraOverride = null, printerOverride = null) {
  resetProbeResult();
  const camera = cameraOverride || cameraFromForm();
  const printer = printerOverride || findPrinter(cameraFields.printerId.value) || { id: "printer", name: "Printer" };
  const resolved = resolveUrls(camera);
  updatePreviewPanel(camera);
  updateRecordUrlWarning(resolved.record_url);
  if (camera.mode !== "gopro" && !resolved.record_url) {
    showError(probe.error, "This camera has no recording URL to probe.");
    return;
  }

  try {
    const url = camera.mode === "gopro" ? "/api/gopro/test" : "/api/camera/probe";
    const result = await fetchJson(url, {
      method: "POST",
      body: JSON.stringify(probePayloadFromCamera(printer, camera)),
    });
    updateProbeResult(result, camera.mode || "manual_urls");
  } catch (error) {
    showError(probe.error, error.message);
  }
}

async function loadConfig() {
  try {
    clearError(configError);
    const payload = await fetchJson("/api/cameras/config");
    printers = payload.printers || [];
    printers.forEach((printer) => {
      printer.cameras = printer.cameras || [];
      ensurePrinterDefault(printer);
    });
    renderPrinterList();
    renderPrinterOptions(printers[0] ? printers[0].id : "");
    if (printers.length) beginEditPrinter(printers[0].id);
    else beginNewPrinter();
  } catch (error) {
    showError(configError, error.message);
  }
}

printerFields.name.addEventListener("input", () => {
  if (!idTouched) printerFields.id.value = slugifyId(printerFields.name.value, "printer");
});
printerFields.id.addEventListener("input", () => {
  idTouched = true;
});
cameraFields.name.addEventListener("input", () => {
  if (!idTouched) cameraFields.id.value = slugifyId(cameraFields.name.value, "camera");
  if (!outputSubdirTouched) cameraFields.outputSubdir.value = cameraFields.id.value;
  updatePreviewPanel();
});
cameraFields.id.addEventListener("input", () => {
  idTouched = true;
  if (!outputSubdirTouched) cameraFields.outputSubdir.value = cameraFields.id.value.trim();
});
cameraFields.outputSubdir.addEventListener("input", () => {
  outputSubdirTouched = true;
});
cameraFields.mode.addEventListener("change", () => {
  setModeVisibility();
  updatePreviewPanel();
  resetProbeResult();
});
cameraFields.previewMode.addEventListener("change", () => {
  setModeVisibility();
  updatePreviewPanel();
});
[
  cameraFields.go2rtcBaseUrl,
  cameraFields.streamName,
  cameraFields.previewUrl,
  cameraFields.recordUrl,
  cameraFields.goproHost,
  cameraFields.goproPreviewUrl,
].forEach((field) => field.addEventListener("input", () => updatePreviewPanel()));

$("#printer-form").addEventListener("submit", savePrinter);
$("#camera-form").addEventListener("submit", saveCamera);
$("#new-printer-button").addEventListener("click", beginNewPrinter);
$("#cancel-printer-edit-button").addEventListener("click", beginNewPrinter);
$("#cancel-camera-edit-button").addEventListener("click", () => {
  if (printers.length) beginEditPrinter(cameraFields.printerId.value || printers[0].id);
  else beginNewPrinter();
});
$("#delete-printer-button").addEventListener("click", () => editingPrinterId && deletePrinter(editingPrinterId));
$("#delete-camera-button").addEventListener("click", () => editingCameraId && deleteCamera(editingCameraId));
$("#probe-camera-button").addEventListener("click", () => probeCamera());

printerList.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLButtonElement)) return;
  const { action, printerId, cameraId } = target.dataset;
  if (action === "edit-printer" && printerId) beginEditPrinter(printerId);
  else if (action === "delete-printer" && printerId) deletePrinter(printerId);
  else if (action === "add-camera" && printerId) beginNewCamera(printerId);
  else if (action === "edit-camera" && cameraId) beginEditCamera(cameraId);
  else if (action === "delete-camera" && cameraId) deleteCamera(cameraId);
  else if (action === "test-camera" && cameraId) {
    const found = findCamera(cameraId);
    if (found) {
      beginEditCamera(cameraId);
      probeCamera(found.camera, found.printer);
    }
  }
});

beginNewPrinter();
resetProbeResult();
loadConfig();
