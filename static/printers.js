const PRINTER_POLL_INTERVAL_MS = 7000;
const PRINTER_FRESHNESS_INTERVAL_MS = 5000;
const PRINTER_RECORDING_POLL_INTERVAL_MS = 4000;
const PRINTER_TIMELAPSE_POLL_INTERVAL_MS = 5000;
const PRINTER_VISIBILITY_KEY = "printernvr-visible-printers";
const PRINTER_VIEW_SELECTION_KEY = "printernvr-printer-view-selections";

let refreshInFlight = false;
const recordingStates = new Map();
const localRecordingErrors = new Map();
const timelapseStates = new Map();
const localTimelapseErrors = new Map();
const latestClipStates = new Map();
const CUSTOM_DURATION_MIN_SECONDS = 1;
const CUSTOM_DURATION_MAX_SECONDS = 600;

function query(selector) {
  return document.querySelector(selector);
}

function queryAll(selector) {
  return Array.from(document.querySelectorAll(selector));
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

function readStorageObject(key) {
  const raw = window.localStorage.getItem(key);
  if (!raw) {
    return {};
  }

  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch (_error) {
    return {};
  }
}

function writeStorageObject(key, value) {
  window.localStorage.setItem(key, JSON.stringify(value));
}

function parseIsoDate(value) {
  if (!value) {
    return null;
  }

  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatProgress(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }
  return `${Number(value).toFixed(1)}%`;
}

function formatTemp(current, target) {
  if (current === null || current === undefined || Number.isNaN(Number(current))) {
    return "--";
  }

  const currentText = Number(current).toFixed(1);
  const targetText = target === null || target === undefined || Number.isNaN(Number(target))
    ? "--"
    : Number(target).toFixed(1);
  return `${currentText} / ${targetText} C`;
}

function humanFileName(value) {
  if (!value) {
    return "";
  }

  const parts = String(value).split(/[\\/]/);
  return parts[parts.length - 1] || String(value);
}

function clipAgeText(value) {
  const createdAt = parseIsoDate(value);
  if (!createdAt) {
    return "";
  }

  const ageSeconds = Math.max(0, Math.round((Date.now() - createdAt.getTime()) / 1000));
  if (ageSeconds < 60) {
    return "just now";
  }
  const ageMinutes = Math.floor(ageSeconds / 60);
  if (ageMinutes < 60) {
    return `${ageMinutes}m ago`;
  }
  const ageHours = Math.floor(ageMinutes / 60);
  if (ageHours < 24) {
    return `${ageHours}h ago`;
  }
  const ageDays = Math.floor(ageHours / 24);
  return `${ageDays}d ago`;
}

function normalizeVisiblePrinterIds() {
  return queryAll("[data-printer-toggle]")
    .filter((input) => input instanceof HTMLInputElement && input.checked)
    .map((input) => input.dataset.printerToggle)
    .filter(Boolean);
}

function persistVisiblePrinters() {
  const visible = normalizeVisiblePrinterIds();
  const known = queryAll("[data-printer-toggle]")
    .map((input) => input.dataset.printerToggle)
    .filter(Boolean);
  writeStorageObject(PRINTER_VISIBILITY_KEY, { selected: visible, known });
}

function updateVisiblePrinterCards() {
  const visible = new Set(normalizeVisiblePrinterIds());
  queryAll("[data-printer-card]").forEach((card) => {
    const printerId = card.dataset.printerCard;
    card.hidden = !visible.has(printerId);
  });

  const empty = query("#printers-empty-filtered");
  const visibleCount = queryAll("[data-printer-card]").filter((card) => !card.hidden).length;
  if (empty) {
    empty.hidden = visibleCount !== 0;
  }
}

function applySavedVisibility() {
  const raw = window.localStorage.getItem(PRINTER_VISIBILITY_KEY);
  let saved = [];
  let known = [];
  if (raw) {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        saved = parsed;
      } else {
        saved = Array.isArray(parsed.selected) ? parsed.selected : [];
        known = Array.isArray(parsed.known) ? parsed.known : [];
      }
    } catch (_error) {
      saved = [];
      known = [];
    }
  }

  const savedSet = new Set(saved);
  const knownSet = new Set(known);

  queryAll("[data-printer-toggle]").forEach((input) => {
    if (!(input instanceof HTMLInputElement)) {
      return;
    }
    const printerId = input.dataset.printerToggle;
    input.checked = savedSet.has(printerId) || !knownSet.has(printerId);
  });
  updateVisiblePrinterCards();
}

function setAllPrintersVisible(visible) {
  queryAll("[data-printer-toggle]").forEach((input) => {
    if (input instanceof HTMLInputElement) {
      input.checked = visible;
    }
  });
  persistVisiblePrinters();
  updateVisiblePrinterCards();
}

function readViewSelections() {
  return readStorageObject(PRINTER_VIEW_SELECTION_KEY);
}

function persistViewSelection(printerId, cameraId) {
  const selections = readViewSelections();
  selections[printerId] = cameraId;
  writeStorageObject(PRINTER_VIEW_SELECTION_KEY, selections);
}

function clearViewSelection(printerId) {
  const selections = readViewSelections();
  if (!(printerId in selections)) {
    return;
  }
  delete selections[printerId];
  writeStorageObject(PRINTER_VIEW_SELECTION_KEY, selections);
}

function getPrinterCard(printerId) {
  return query(`[data-printer-card="${printerId}"]`);
}

function getViewSelect(printerId) {
  return query(`[data-printer-view-select="${printerId}"]`);
}

function getCurrentViewLabel(printerId) {
  return query(`[data-printer-current-view-label="${printerId}"]`);
}

function getPreviewContainer(printerId) {
  return query(`[data-printer-preview="${printerId}"]`);
}

function getCurrentView(printerId) {
  const select = getViewSelect(printerId);
  if (select instanceof HTMLSelectElement && select.selectedOptions[0]) {
    return getViewFromOption(select.selectedOptions[0]);
  }

  const card = getPrinterCard(printerId);
  const defaultCameraId = card ? card.dataset.defaultCameraId || "" : "";
  if (defaultCameraId) {
    return {
      camera_id: defaultCameraId,
      camera_name: getCurrentViewLabel(printerId)?.textContent || defaultCameraId,
      preview_url: getPreviewContainer(printerId)?.dataset.previewUrl || "",
      preview_mode: getPreviewContainer(printerId)?.dataset.previewMode || "none",
      preview_available: getPreviewContainer(printerId)?.dataset.previewAvailable === "true",
      enabled: card.dataset.defaultCameraEnabled !== "false",
    };
  }

  return null;
}

function getViewFromOption(option) {
  if (!option) {
    return null;
  }

  return {
    camera_id: option.value,
    camera_name: option.dataset.cameraName || option.textContent || option.value,
    preview_url: option.dataset.previewUrl || "",
    preview_mode: option.dataset.previewMode || "none",
    preview_available: option.dataset.previewAvailable === "true",
    enabled: option.dataset.enabled !== "false",
  };
}

function findOptionByCameraId(select, cameraId) {
  if (!select || !cameraId) {
    return null;
  }

  return Array.from(select.options).find((option) => option.value === cameraId) || null;
}

function getPreviewFallbackMessage(view) {
  if (!view || !view.preview_url || view.preview_mode === "none") {
    return "Preview unavailable for this view.";
  }
  return "Preview unavailable for this view.";
}

function createPreviewNode(printerName, view, modal = false) {
  if (view && view.preview_mode === "embedded" && view.preview_url) {
    const frame = document.createElement("iframe");
    frame.title = `${printerName} live view`;
    frame.src = view.preview_url;
    frame.loading = "lazy";
    frame.allowFullscreen = true;
    if (modal) {
      frame.className = "printer-preview-modal__frame";
    }
    return frame;
  }

  if (view && view.preview_mode === "external_link" && view.preview_url) {
    const state = document.createElement("div");
    state.className = "preview-link-state";

    const description = document.createElement("p");
    description.textContent = "Preview opens externally for this printer view.";

    const link = document.createElement("a");
    link.className = "control-button control-button--secondary table-link";
    link.href = view.preview_url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = modal ? "Open Preview in New Tab" : "Open Preview";

    state.append(description, link);
    return state;
  }

  const empty = document.createElement("div");
  empty.className = "no-preview";
  empty.textContent = getPreviewFallbackMessage(view);
  return empty;
}

function renderPreview(printerId, view) {
  const container = getPreviewContainer(printerId);
  const card = getPrinterCard(printerId);
  if (!container || !card) {
    return;
  }

  const printerName = card.dataset.printerName || "Printer";
  const label = getCurrentViewLabel(printerId);
  if (label) {
    label.textContent = view && view.camera_name ? view.camera_name : "No default camera";
  }

  container.dataset.currentCameraId = view && view.camera_id ? view.camera_id : "";
  container.dataset.previewUrl = view && view.preview_url ? view.preview_url : "";
  container.dataset.previewMode = view && view.preview_mode ? view.preview_mode : "none";
  container.dataset.previewAvailable = view && view.preview_available ? "true" : "false";
  container.dataset.viewEnabled = view && view.enabled === false ? "false" : "true";
  container.replaceChildren(createPreviewNode(printerName, view));
  updatePrinterRecordingState(printerId);
  updatePrinterTimelapseState(printerId);
  refreshLatestClipForPrinter(printerId).catch((error) => console.error(error));
}

function restoreStoredViewForPrinter(printerId) {
  const select = getViewSelect(printerId);
  if (!(select instanceof HTMLSelectElement)) {
    clearViewSelection(printerId);
    return;
  }

  const card = getPrinterCard(printerId);
  const storedSelections = readViewSelections();
  const defaultCameraId = card ? card.dataset.defaultCameraId || "" : "";
  const storedCameraId = storedSelections[printerId];

  let option = findOptionByCameraId(select, storedCameraId);
  if (!option) {
    option = findOptionByCameraId(select, defaultCameraId) || select.selectedOptions[0] || select.options[0];
    clearViewSelection(printerId);
  } else {
    select.value = storedCameraId;
  }

  if (!option) {
    return;
  }

  renderPreview(printerId, getViewFromOption(option));
}

function restoreStoredViews() {
  queryAll("[data-printer-card]").forEach((card) => {
    const printerId = card.dataset.printerCard;
    if (printerId) {
      restoreStoredViewForPrinter(printerId);
    }
  });
}

function statusToneForPrinter(printer) {
  if (printer.connection_state === "offline") {
    return "offline";
  }

  const state = String(printer.monitor_state || "").toLowerCase();
  if (["printing", "idle", "complete", "paused", "error", "offline"].includes(state)) {
    return state;
  }
  return "unavailable";
}

function setConnectionBadge(printerId, connectionState) {
  const badge = query(`[data-printer-connection="${printerId}"]`);
  if (!badge) {
    return;
  }

  const normalized = ["online", "offline", "unknown"].includes(connectionState)
    ? connectionState
    : "unknown";
  badge.textContent = normalized.charAt(0).toUpperCase() + normalized.slice(1);
  badge.classList.remove(
    "printer-state-badge--online",
    "printer-state-badge--offline",
    "printer-state-badge--unknown",
  );
  badge.classList.add(`printer-state-badge--${normalized}`);
}

function setStatusBadge(printer) {
  const badge = query(`[data-printer-status-badge="${printer.printer_id}"]`);
  if (!badge) {
    return;
  }

  const tone = statusToneForPrinter(printer);
  badge.textContent = printer.printer_status_text || "Status unavailable";
  badge.classList.remove(
    "printer-status-pill--printing",
    "printer-status-pill--idle",
    "printer-status-pill--complete",
    "printer-status-pill--paused",
    "printer-status-pill--error",
    "printer-status-pill--offline",
    "printer-status-pill--unavailable",
  );
  badge.classList.add(`printer-status-pill--${tone}`);
}

function updateText(selector, value) {
  const node = query(selector);
  if (node) {
    node.textContent = value || "--";
  }
}

function setMetadataAttrs(printer) {
  const card = getPrinterCard(printer.printer_id);
  if (!card) {
    return;
  }

  const previousSuccessAt = card.dataset.lastMetadataSuccessAt || "";
  card.dataset.hasMetadataSource = printer.has_metadata_source ? "true" : "false";
  card.dataset.lastMetadataAttemptAt = printer.last_metadata_attempt_at || "";
  card.dataset.lastMetadataSuccessAt = printer.last_metadata_success_at || previousSuccessAt;
}

function formatFreshnessText(printerId) {
  const card = getPrinterCard(printerId);
  if (!card) {
    return "--";
  }

  const hasMetadataSource = card.dataset.hasMetadataSource === "true";
  const successAt = parseIsoDate(card.dataset.lastMetadataSuccessAt);
  const attemptAt = parseIsoDate(card.dataset.lastMetadataAttemptAt);

  if (!hasMetadataSource) {
    return "No metadata source";
  }

  if (!successAt) {
    if (attemptAt) {
      return "Waiting for successful refresh";
    }
    return "Status unavailable";
  }

  const ageSeconds = Math.max(0, Math.round((Date.now() - successAt.getTime()) / 1000));
  if (ageSeconds <= 3) {
    return "Updated just now";
  }
  if (ageSeconds < 60) {
    return `Updated ${ageSeconds}s ago`;
  }

  const ageMinutes = Math.floor(ageSeconds / 60);
  if (ageMinutes < 5) {
    return `Updated ${ageMinutes}m ago`;
  }

  return "Stale";
}

function updateFreshnessLabels() {
  queryAll("[data-printer-updated-text]").forEach((node) => {
    const printerId = node.dataset.printerUpdatedText;
    node.textContent = formatFreshnessText(printerId);
  });
}

function getRefreshButtons() {
  return queryAll("[data-printer-refresh], #printers-refresh-all");
}

function setRefreshBusy(isBusy) {
  getRefreshButtons().forEach((button) => {
    if (button instanceof HTMLButtonElement) {
      button.disabled = isBusy;
    }
  });
}

function getRecordingStatusTone(status) {
  const normalized = String(status || "idle").toLowerCase();
  return ["starting", "recording", "stopping", "downloading", "error"].includes(normalized)
    ? normalized
    : "idle";
}

function getRecordingStatusLabel(status, state = null) {
  const tone = getRecordingStatusTone(status);
  if (tone === "idle") {
    return "Recording: Idle";
  }
  if (tone === "recording" && state && state.requested_duration_seconds) {
    return "Recording: Timed";
  }
  return `Recording: ${tone.charAt(0).toUpperCase() + tone.slice(1)}`;
}

function setRecordingBadge(printerId, stateOrStatus) {
  const badge = query(`[data-printer-recording-badge="${printerId}"]`);
  if (!badge) {
    return;
  }

  const state = stateOrStatus && typeof stateOrStatus === "object" ? stateOrStatus : null;
  const status = state ? state.status : stateOrStatus;
  const tone = getRecordingStatusTone(status);
  badge.textContent = getRecordingStatusLabel(status, state);
  badge.classList.remove(
    "recording-state-pill--idle",
    "recording-state-pill--starting",
    "recording-state-pill--recording",
    "recording-state-pill--stopping",
    "recording-state-pill--downloading",
    "recording-state-pill--error",
  );
  badge.classList.add(`recording-state-pill--${tone}`);
}

function setRecordingError(printerId, message) {
  const errorNode = query(`[data-printer-recording-error="${printerId}"]`);
  if (!errorNode) {
    return;
  }

  if (message) {
    errorNode.hidden = false;
    errorNode.textContent = message;
  } else {
    errorNode.hidden = true;
    errorNode.textContent = "";
  }
}

function setRecordingMessage(printerId, message) {
  updateText(`[data-printer-recording-message="${printerId}"]`, message);
}

function getSelectedCameraId(printerId) {
  const view = getCurrentView(printerId);
  return view && view.camera_id ? view.camera_id : null;
}

function getCustomDurationInput(printerId) {
  return query(`[data-printer-custom-duration="${printerId}"]`);
}

function readCustomDuration(printerId) {
  const input = getCustomDurationInput(printerId);
  if (!(input instanceof HTMLInputElement)) {
    throw new Error("Custom duration input is unavailable.");
  }

  const duration = Number(input.value);
  if (!Number.isInteger(duration)) {
    throw new Error("Custom duration must be a whole number of seconds.");
  }
  if (duration < CUSTOM_DURATION_MIN_SECONDS || duration > CUSTOM_DURATION_MAX_SECONDS) {
    throw new Error(
      `Custom duration must be between ${CUSTOM_DURATION_MIN_SECONDS} and ${CUSTOM_DURATION_MAX_SECONDS} seconds.`,
    );
  }
  return duration;
}

function updatePrinterClipsLink(printerId, cameraId) {
  const link = query(`[data-printer-clips-link="${printerId}"]`);
  if (!link) {
    return;
  }

  link.href = cameraId ? `/clips?camera_id=${encodeURIComponent(cameraId)}` : "/clips";
}

function updateLatestClipLinks(printerId, cameraId) {
  const allLinks = queryAll(
    `[data-printer-latest-all="${printerId}"], [data-printer-clips-link="${printerId}"]`,
  );
  allLinks.forEach((link) => {
    link.href = cameraId ? `/clips?camera_id=${encodeURIComponent(cameraId)}` : "/clips";
  });
}

function latestClipUrl(cameraId) {
  return `/api/clips/latest/${encodeURIComponent(cameraId)}`;
}

function updateLatestClipSection(printerId, latestClip) {
  const nameNode = query(`[data-printer-latest-clip-name="${printerId}"]`);
  const metaNode = query(`[data-printer-latest-clip-meta="${printerId}"]`);
  const previewButton = query(`[data-printer-latest-preview="${printerId}"]`);
  const downloadLink = query(`[data-printer-latest-download="${printerId}"]`);
  const cameraId = latestClip && latestClip.camera_id ? latestClip.camera_id : getSelectedCameraId(printerId);

  if (cameraId) {
    updateLatestClipLinks(printerId, cameraId);
  }

  if (!latestClip || !latestClip.has_latest_clip) {
    if (nameNode) {
      nameNode.textContent = "No clips yet";
    }
    if (metaNode) {
      metaNode.textContent = "--";
    }
    if (previewButton instanceof HTMLButtonElement) {
      previewButton.disabled = true;
    }
    if (downloadLink instanceof HTMLAnchorElement) {
      downloadLink.href = "#";
      downloadLink.setAttribute("aria-disabled", "true");
    }
    return;
  }

  latestClipStates.set(latestClip.camera_id, latestClip);
  if (nameNode) {
    nameNode.textContent = latestClip.filename || "Latest clip";
  }
  if (metaNode) {
    const age = clipAgeText(latestClip.created_at);
    const size = latestClip.size_human || "";
    metaNode.textContent = [age, size].filter(Boolean).join(" | ") || "--";
  }
  if (previewButton instanceof HTMLButtonElement) {
    previewButton.disabled = !latestClip.preview_url;
  }
  if (downloadLink instanceof HTMLAnchorElement) {
    downloadLink.href = latestClip.download_url || "#";
    if (latestClip.download_url) {
      downloadLink.removeAttribute("aria-disabled");
    } else {
      downloadLink.setAttribute("aria-disabled", "true");
    }
  }
}

async function refreshLatestClipForPrinter(printerId) {
  const cameraId = getSelectedCameraId(printerId);
  if (!cameraId) {
    updateLatestClipSection(printerId, { has_latest_clip: false, camera_id: "" });
    return;
  }

  const latestClip = await fetchJson(latestClipUrl(cameraId));
  latestClipStates.set(cameraId, latestClip);
  updateLatestClipSection(printerId, latestClip);
}

async function refreshLatestClipForCamera(cameraId) {
  const matchingCards = queryAll("[data-printer-card]").filter((card) => {
    const printerId = card.dataset.printerCard;
    return printerId && getSelectedCameraId(printerId) === cameraId;
  });

  await Promise.all(
    matchingCards.map((card) => refreshLatestClipForPrinter(card.dataset.printerCard)),
  );
}

function refreshAllLatestClips() {
  queryAll("[data-printer-card]").forEach((card) => {
    const printerId = card.dataset.printerCard;
    if (printerId) {
      refreshLatestClipForPrinter(printerId).catch((error) => console.error(error));
    }
  });
}

function describeRecordingState(printerId, view, state) {
  const viewName = view && view.camera_name ? view.camera_name.trim() : "selected view";
  if (!view || !view.camera_id) {
    return "No recording target selected.";
  }
  if (view.enabled === false) {
    return `${viewName} is disabled.`;
  }
  if (!state) {
    return `Selected view: ${viewName}`;
  }

  const status = getRecordingStatusTone(state.status);
  if (status === "starting") {
    return `Starting recording from ${viewName}...`;
  }
  if (status === "recording") {
    if (state.requested_duration_seconds) {
      return `${state.requested_duration_seconds}-second clip in progress from ${viewName}...`;
    }
    return `Recording from ${viewName}...`;
  }
  if (status === "stopping") {
    return `Stopping recording from ${viewName}...`;
  }
  if (status === "downloading") {
    return "Downloading clip...";
  }
  if (status === "error") {
    return state.last_action_message || state.last_error || "Recording error";
  }

  const lastClip = humanFileName(state.last_completed_output || state.last_downloaded_filename);
  if (lastClip) {
    return `Last clip: ${lastClip}`;
  }
  return `Recording idle. Selected view: ${viewName}`;
}

function updatePrinterRecordingState(printerId) {
  const view = getCurrentView(printerId);
  const cameraId = view && view.camera_id ? view.camera_id : null;
  const state = cameraId ? recordingStates.get(cameraId) : null;
  const status = state ? state.status : "idle";
  const busy = ["starting", "recording", "stopping", "downloading"].includes(
    getRecordingStatusTone(status),
  );
  const canRecord = Boolean(cameraId) && view && view.enabled !== false;

  setRecordingBadge(printerId, state || status);
  setRecordingMessage(printerId, describeRecordingState(printerId, view, state));
  const localError = localRecordingErrors.get(printerId);
  setRecordingError(
    printerId,
    localError || (state && state.last_error ? `Error: ${state.last_error}` : ""),
  );
  updatePrinterClipsLink(printerId, cameraId);

  queryAll(`[data-printer-record-printer="${printerId}"]`).forEach((button) => {
    if (!(button instanceof HTMLButtonElement)) {
      return;
    }

    const action = button.dataset.printerRecordAction;
    if (!canRecord) {
      button.disabled = true;
      return;
    }

    if (action === "stop") {
      button.disabled = !["starting", "recording"].includes(getRecordingStatusTone(status));
      return;
    }

    button.disabled = busy;
  });

  const customInput = getCustomDurationInput(printerId);
  if (customInput instanceof HTMLInputElement) {
    customInput.disabled = busy || !canRecord;
  }
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

function getTimelapseInterval(printerId) {
  const select = query(`[data-printer-timelapse-interval="${printerId}"]`);
  if (!(select instanceof HTMLSelectElement)) {
    return 10;
  }
  const interval = Number(select.value);
  return Number.isInteger(interval) && interval >= 1 && interval <= 300 ? interval : 10;
}

function setTimelapseError(printerId, message) {
  const errorNode = query(`[data-printer-timelapse-error="${printerId}"]`);
  if (!errorNode) {
    return;
  }

  if (message) {
    errorNode.hidden = false;
    errorNode.textContent = message;
  } else {
    errorNode.hidden = true;
    errorNode.textContent = "";
  }
}

function describeTimelapseState(printerId, view, state) {
  const selectedViewName = view && view.camera_name ? view.camera_name.trim() : "selected view";
  if (!view || !view.camera_id) {
    return "No timelapse camera selected.";
  }
  if (view.enabled === false) {
    return `${selectedViewName} is disabled.`;
  }
  if (!state || !state.status || state.status === "idle") {
    return `Timelapse idle. Selected view: ${selectedViewName}`;
  }

  const cameraName = state.camera_name || state.camera_id || selectedViewName;
  const frames = Number(state.frame_count || 0);
  const interval = state.interval_seconds ? `${state.interval_seconds}s` : "--";
  const tone = getTimelapseStatusTone(state.status);
  if (tone === "starting") {
    return `Starting timelapse from ${cameraName}...`;
  }
  if (tone === "running") {
    return `Capturing ${cameraName} every ${interval}. ${frames} frame${frames === 1 ? "" : "s"} captured.`;
  }
  if (tone === "stopping") {
    return `Stopping timelapse from ${cameraName}...`;
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
  return `Timelapse idle. Selected view: ${selectedViewName}`;
}

function updatePrinterTimelapseState(printerId) {
  const view = getCurrentView(printerId);
  const state = timelapseStates.get(printerId) || null;
  const tone = getTimelapseStatusTone(state && state.status);
  const busy = ["starting", "running", "stopping", "rendering"].includes(tone);
  const canStart = Boolean(view && view.camera_id && view.enabled !== false);

  const badge = query(`[data-printer-timelapse-badge="${printerId}"]`);
  if (badge) {
    badge.textContent = getTimelapseStatusLabel(tone);
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
    }[tone] || "idle";
    badge.classList.add(`recording-state-pill--${badgeTone}`);
  }

  updateText(`[data-printer-timelapse-message="${printerId}"]`, describeTimelapseState(printerId, view, state));
  updateText(`[data-printer-timelapse-frames="${printerId}"]`, state ? String(state.frame_count || 0) : "0");
  updateText(
    `[data-printer-timelapse-camera="${printerId}"]`,
    state && state.camera_name ? state.camera_name : (view && view.camera_name ? view.camera_name : "--"),
  );
  updateText(`[data-printer-timelapse-stop-reason="${printerId}"]`, state && state.stop_reason ? state.stop_reason : "--");
  updateText(`[data-printer-timelapse-render="${printerId}"]`, state && state.render_status ? state.render_status : "idle");

  const outputLink = query(`[data-printer-timelapse-output="${printerId}"]`);
  if (outputLink instanceof HTMLAnchorElement) {
    if (state && state.output_url && tone === "complete") {
      outputLink.href = state.output_url;
      outputLink.removeAttribute("aria-disabled");
      outputLink.textContent = state.output_file || "Latest Timelapse";
    } else {
      outputLink.href = "#";
      outputLink.setAttribute("aria-disabled", "true");
      outputLink.textContent = "Latest Timelapse";
    }
  }

  const localError = localTimelapseErrors.get(printerId);
  setTimelapseError(
    printerId,
    localError || (state && (state.last_error || state.render_error) ? `Error: ${state.last_error || state.render_error}` : ""),
  );

  queryAll(`[data-printer-timelapse-printer="${printerId}"]`).forEach((button) => {
    if (!(button instanceof HTMLButtonElement)) {
      return;
    }
    const action = button.dataset.printerTimelapseAction;
    if (action === "stop") {
      button.disabled = !["starting", "running"].includes(tone);
      return;
    }
    button.disabled = busy || !canStart;
  });

  const intervalSelect = query(`[data-printer-timelapse-interval="${printerId}"]`);
  if (intervalSelect instanceof HTMLSelectElement) {
    intervalSelect.disabled = busy;
  }
}

function updateAllPrinterTimelapseStates() {
  queryAll("[data-printer-card]").forEach((card) => {
    const printerId = card.dataset.printerCard;
    if (printerId) {
      updatePrinterTimelapseState(printerId);
    }
  });
}

function updateAllPrinterRecordingStates() {
  queryAll("[data-printer-card]").forEach((card) => {
    const printerId = card.dataset.printerCard;
    if (printerId) {
      updatePrinterRecordingState(printerId);
    }
  });
}

function mergeRecordingState(state) {
  if (state && state.camera_id) {
    const previous = recordingStates.get(state.camera_id);
    const previousTone = previous ? getRecordingStatusTone(previous.status) : "idle";
    const nextTone = getRecordingStatusTone(state.status);
    recordingStates.set(state.camera_id, state);
    const wasBusy = ["starting", "recording", "stopping", "downloading"].includes(previousTone);
    const isBusy = ["starting", "recording", "stopping", "downloading"].includes(nextTone);
    if (wasBusy && !isBusy) {
      setTimeout(() => {
        refreshLatestClipForCamera(state.camera_id).catch((error) => console.error(error));
      }, 1000);
    }
  }
}

function updateCard(printer) {
  setConnectionBadge(printer.printer_id, printer.connection_state);
  setStatusBadge(printer);
  setMetadataAttrs(printer);
  updateText(`[data-printer-file-name="${printer.printer_id}"]`, printer.current_file_name);
  updateText(`[data-printer-progress="${printer.printer_id}"]`, formatProgress(printer.progress_percent));
  updateText(
    `[data-printer-extruder="${printer.printer_id}"]`,
    formatTemp(printer.extruder_current_temp, printer.extruder_target_temp),
  );
  updateText(
    `[data-printer-bed="${printer.printer_id}"]`,
    formatTemp(printer.bed_current_temp, printer.bed_target_temp),
  );
  updateText(`[data-printer-eta="${printer.printer_id}"]`, printer.eta_text);

  const errorNode = query(`[data-printer-error="${printer.printer_id}"]`);
  if (errorNode) {
    if (printer.error_message) {
      errorNode.hidden = false;
      errorNode.textContent = printer.error_message;
    } else {
      errorNode.hidden = true;
      errorNode.textContent = "";
    }
  }
}

function getDomViewIds(printerId) {
  const select = getViewSelect(printerId);
  if (select instanceof HTMLSelectElement) {
    return Array.from(select.options).map((option) => option.value);
  }

  const card = getPrinterCard(printerId);
  if (!card) {
    return [];
  }

  return card.dataset.defaultCameraId ? [card.dataset.defaultCameraId] : [];
}

function printerViewConfigChanged(printer) {
  const card = getPrinterCard(printer.printer_id);
  if (!card) {
    return true;
  }

  if ((card.dataset.defaultCameraId || "") !== (printer.default_camera_id || "")) {
    return true;
  }

  const domViewIds = getDomViewIds(printer.printer_id);
  const payloadViewIds = Array.isArray(printer.available_views)
    ? printer.available_views.map((view) => view.camera_id)
    : [];

  if (domViewIds.length !== payloadViewIds.length) {
    return true;
  }

  return payloadViewIds.some((cameraId, index) => domViewIds[index] !== cameraId);
}

async function refreshPrinterCards() {
  if (refreshInFlight) {
    return;
  }

  refreshInFlight = true;
  setRefreshBusy(true);

  try {
    const payload = await fetchJson("/api/printers/cards");
    const printers = payload.printers || [];
    const currentIds = new Set(queryAll("[data-printer-card]").map((card) => card.dataset.printerCard));
    const payloadIds = new Set(printers.map((printer) => printer.printer_id));

    if (currentIds.size !== payloadIds.size || Array.from(payloadIds).some((id) => !currentIds.has(id))) {
      window.location.reload();
      return;
    }

    if (printers.some(printerViewConfigChanged)) {
      window.location.reload();
      return;
    }

    printers.forEach(updateCard);
    updateFreshnessLabels();
  } finally {
    refreshInFlight = false;
    setRefreshBusy(false);
  }
}

async function refreshRecordingStates() {
  const payload = await fetchJson("/api/record/status");
  (payload.cameras || []).forEach(mergeRecordingState);
  updateAllPrinterRecordingStates();
}

function mergeTimelapseState(printerId, state) {
  if (!printerId || !state) {
    return;
  }
  timelapseStates.set(printerId, state);
}

async function refreshTimelapseStates() {
  const payload = await fetchJson("/api/timelapse/status");
  const states = payload.printers || {};
  Object.entries(states).forEach(([printerId, state]) => mergeTimelapseState(printerId, state));
  updateAllPrinterTimelapseStates();
}

async function startRecording(cameraId, duration) {
  const options = { method: "POST" };
  if (duration !== undefined && duration !== null) {
    options.body = JSON.stringify({ duration });
  }

  const payload = await fetchJson(`/api/record/start/${cameraId}`, options);
  if (payload.camera) {
    mergeRecordingState(payload.camera);
  }
  updateAllPrinterRecordingStates();
}

async function stopRecording(cameraId) {
  const payload = await fetchJson(`/api/record/stop/${cameraId}`, {
    method: "POST",
  });
  if (payload.camera) {
    mergeRecordingState(payload.camera);
  }
  updateAllPrinterRecordingStates();
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
    mergeTimelapseState(printerId, payload.timelapse);
  }
  updateAllPrinterTimelapseStates();
}

async function stopTimelapse(printerId) {
  const payload = await fetchJson(`/api/timelapse/stop/${encodeURIComponent(printerId)}`, {
    method: "POST",
  });
  if (payload.timelapse) {
    mergeTimelapseState(printerId, payload.timelapse);
  }
  updateAllPrinterTimelapseStates();
}

function openPreviewModal(printerId) {
  const modal = query("#printer-preview-modal");
  const modalTitle = query("#printer-preview-modal-title");
  const modalView = query("#printer-preview-modal-view");
  const modalBody = query("#printer-preview-modal-body");
  const card = getPrinterCard(printerId);
  const view = getCurrentView(printerId);

  if (!(modal instanceof HTMLDialogElement) || !modalTitle || !modalView || !modalBody || !card) {
    return;
  }

  const printerName = card.dataset.printerName || "Printer";
  modalTitle.textContent = printerName;
  modalView.textContent = view && view.camera_name ? view.camera_name : "Current view";
  modalBody.replaceChildren(createPreviewNode(printerName, view, true));
  modal.dataset.printerId = printerId;

  if (!modal.open) {
    modal.showModal();
  }
}

function closePreviewModal() {
  const modal = query("#printer-preview-modal");
  const modalBody = query("#printer-preview-modal-body");
  if (!(modal instanceof HTMLDialogElement) || !modalBody) {
    return;
  }

  modalBody.replaceChildren(createPreviewNode("Printer", null, true));
  if (modal.open) {
    modal.close();
  }
}

function buildLatestClipPreviewNode(latestClip) {
  if (!latestClip || !latestClip.has_latest_clip || !latestClip.preview_url) {
    const empty = document.createElement("div");
    empty.className = "no-preview";
    empty.textContent = "No latest clip available";
    return empty;
  }

  const wrapper = document.createElement("div");
  wrapper.className = "latest-clip-preview";

  const video = document.createElement("video");
  video.className = "clip-preview-player latest-clip-preview__video";
  video.controls = true;
  video.preload = "metadata";
  video.src = latestClip.preview_url;

  const error = document.createElement("p");
  error.className = "clip-preview-error";
  error.textContent = "Preview unavailable for this clip.";
  error.hidden = true;

  video.addEventListener("error", () => {
    error.hidden = false;
  });

  wrapper.append(video, error);
  return wrapper;
}

async function openLatestClipModal(printerId) {
  const cameraId = getSelectedCameraId(printerId);
  let latestClip = cameraId ? latestClipStates.get(cameraId) : null;
  const modal = query("#latest-clip-modal");
  const modalTitle = query("#latest-clip-modal-title");
  const modalMeta = query("#latest-clip-modal-meta");
  const modalBody = query("#latest-clip-modal-body");
  const card = getPrinterCard(printerId);
  const view = getCurrentView(printerId);

  if (!(modal instanceof HTMLDialogElement) || !modalTitle || !modalMeta || !modalBody || !card) {
    return;
  }

  const printerName = card.dataset.printerName || "Printer";
  const viewName = view && view.camera_name ? view.camera_name : cameraId || "Selected view";

  if (cameraId && !latestClip) {
    try {
      latestClip = await fetchJson(latestClipUrl(cameraId));
      latestClipStates.set(cameraId, latestClip);
      updateLatestClipSection(printerId, latestClip);
    } catch (error) {
      console.error(error);
    }
  }

  modalTitle.textContent = latestClip && latestClip.filename ? latestClip.filename : "Latest Clip";
  modalMeta.textContent = `${printerName} | ${viewName}`;
  modalBody.replaceChildren(buildLatestClipPreviewNode(latestClip));

  if (!modal.open) {
    modal.showModal();
  }
}

function closeLatestClipModal() {
  const modal = query("#latest-clip-modal");
  const modalBody = query("#latest-clip-modal-body");
  if (!(modal instanceof HTMLDialogElement) || !modalBody) {
    return;
  }

  modalBody.replaceChildren(buildLatestClipPreviewNode(null));
  if (modal.open) {
    modal.close();
  }
}

function bindViewSelectors() {
  queryAll("[data-printer-view-select]").forEach((select) => {
    if (!(select instanceof HTMLSelectElement)) {
      return;
    }

    select.addEventListener("change", () => {
      const printerId = select.dataset.printerViewSelect;
      const option = select.selectedOptions[0];
      if (!printerId || !option) {
        return;
      }

      persistViewSelection(printerId, option.value);
      localRecordingErrors.delete(printerId);
      renderPreview(printerId, getViewFromOption(option));

      const modal = query("#printer-preview-modal");
      if (modal instanceof HTMLDialogElement && modal.open && modal.dataset.printerId === printerId) {
        openPreviewModal(printerId);
      }
    });
  });
}

function bindPreviewInteractions() {
  queryAll("[data-printer-open-preview]").forEach((button) => {
    button.addEventListener("click", () => {
      const printerId = button.dataset.printerOpenPreview;
      if (printerId) {
        openPreviewModal(printerId);
      }
    });
  });

  queryAll("[data-printer-preview]").forEach((preview) => {
    preview.addEventListener("click", (event) => {
      if (event.target instanceof Element && event.target.closest("a, button")) {
        return;
      }
      const printerId = preview.dataset.printerPreview;
      if (printerId) {
        openPreviewModal(printerId);
      }
    });
  });

  const modal = query("#printer-preview-modal");
  const closeButton = query("#printer-preview-modal-close");
  if (closeButton) {
    closeButton.addEventListener("click", closePreviewModal);
  }

  if (modal instanceof HTMLDialogElement) {
    modal.addEventListener("click", (event) => {
      if (event.target === modal) {
        closePreviewModal();
      }
    });
  }
}

function bindRecordingControls() {
  queryAll("[data-printer-record-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const printerId = button.dataset.printerRecordPrinter;
      const action = button.dataset.printerRecordAction;
      if (!printerId || !action) {
        return;
      }

      const cameraId = getSelectedCameraId(printerId);
      if (!cameraId) {
        localRecordingErrors.set(printerId, "Error: no recording target selected");
        updatePrinterRecordingState(printerId);
        return;
      }

      const view = getCurrentView(printerId);
      if (view && view.enabled === false) {
        localRecordingErrors.set(printerId, `Error: ${view.camera_name || cameraId} is disabled`);
        updatePrinterRecordingState(printerId);
        return;
      }

      localRecordingErrors.delete(printerId);
      setRecordingError(printerId, "");
      try {
        if (action === "start") {
          setRecordingMessage(printerId, "Starting recording...");
          await startRecording(cameraId);
        } else if (action === "stop") {
          setRecordingMessage(printerId, "Stopping recording...");
          await stopRecording(cameraId);
        } else if (action === "timed") {
          const duration = Number(button.dataset.duration || 30);
          setRecordingMessage(printerId, `${duration}-second clip starting...`);
          await startRecording(cameraId, duration);
        } else if (action === "custom") {
          const duration = readCustomDuration(printerId);
          setRecordingMessage(printerId, `${duration}-second clip starting...`);
          await startRecording(cameraId, duration);
        }
        await refreshRecordingStates();
      } catch (error) {
        console.error(error);
        localRecordingErrors.set(printerId, `Error: ${error.message}`);
        updatePrinterRecordingState(printerId);
        await refreshRecordingStates().catch((refreshError) => console.error(refreshError));
      }
    });
  });
}

function bindTimelapseControls() {
  queryAll("[data-printer-timelapse-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const printerId = button.dataset.printerTimelapsePrinter;
      const action = button.dataset.printerTimelapseAction;
      if (!printerId || !action) {
        return;
      }

      const view = getCurrentView(printerId);
      const cameraId = view && view.camera_id ? view.camera_id : null;
      if (action === "start" && !cameraId) {
        localTimelapseErrors.set(printerId, "Error: no timelapse camera selected");
        updatePrinterTimelapseState(printerId);
        return;
      }
      if (action === "start" && view && view.enabled === false) {
        localTimelapseErrors.set(printerId, `Error: ${view.camera_name || cameraId} is disabled`);
        updatePrinterTimelapseState(printerId);
        return;
      }

      localTimelapseErrors.delete(printerId);
      setTimelapseError(printerId, "");

      try {
        if (action === "start") {
          updateText(`[data-printer-timelapse-message="${printerId}"]`, "Starting timelapse...");
          await startTimelapse(printerId, cameraId, getTimelapseInterval(printerId));
        } else if (action === "stop") {
          updateText(`[data-printer-timelapse-message="${printerId}"]`, "Stopping timelapse...");
          await stopTimelapse(printerId);
        }
        await refreshTimelapseStates();
      } catch (error) {
        console.error(error);
        localTimelapseErrors.set(printerId, `Error: ${error.message}`);
        updatePrinterTimelapseState(printerId);
        await refreshTimelapseStates().catch((refreshError) => console.error(refreshError));
      }
    });
  });

  queryAll("[data-printer-timelapse-output]").forEach((link) => {
    link.addEventListener("click", (event) => {
      if (link.getAttribute("aria-disabled") === "true") {
        event.preventDefault();
      }
    });
  });
}

function bindLatestClipControls() {
  queryAll("[data-printer-latest-preview]").forEach((button) => {
    button.addEventListener("click", () => {
      const printerId = button.dataset.printerLatestPreview;
      if (printerId) {
        openLatestClipModal(printerId).catch((error) => console.error(error));
      }
    });
  });

  queryAll("[data-printer-latest-download]").forEach((link) => {
    link.addEventListener("click", (event) => {
      if (link.getAttribute("aria-disabled") === "true") {
        event.preventDefault();
      }
    });
  });

  const closeButton = query("#latest-clip-modal-close");
  if (closeButton) {
    closeButton.addEventListener("click", closeLatestClipModal);
  }

  const modal = query("#latest-clip-modal");
  if (modal instanceof HTMLDialogElement) {
    modal.addEventListener("click", (event) => {
      if (event.target === modal) {
        closeLatestClipModal();
      }
    });
  }
}

function bindControls() {
  queryAll("[data-printer-toggle]").forEach((input) => {
    input.addEventListener("change", () => {
      persistVisiblePrinters();
      updateVisiblePrinterCards();
    });
  });

  const selectAllButton = query("#printers-select-all");
  if (selectAllButton) {
    selectAllButton.addEventListener("click", () => setAllPrintersVisible(true));
  }

  const clearAllButton = query("#printers-clear-all");
  if (clearAllButton) {
    clearAllButton.addEventListener("click", () => setAllPrintersVisible(false));
  }

  const refreshAllButton = query("#printers-refresh-all");
  if (refreshAllButton) {
    refreshAllButton.addEventListener("click", () => {
      refreshPrinterCards().catch((error) => console.error(error));
    });
  }

  queryAll("[data-printer-refresh]").forEach((button) => {
    button.addEventListener("click", () => {
      refreshPrinterCards().catch((error) => console.error(error));
    });
  });
}

bindControls();
bindViewSelectors();
bindPreviewInteractions();
bindRecordingControls();
bindTimelapseControls();
bindLatestClipControls();
applySavedVisibility();
restoreStoredViews();
updateFreshnessLabels();
refreshPrinterCards().catch((error) => console.error(error));
refreshRecordingStates().catch((error) => console.error(error));
refreshTimelapseStates().catch((error) => console.error(error));
refreshAllLatestClips();
setInterval(() => {
  refreshPrinterCards().catch((error) => console.error(error));
}, PRINTER_POLL_INTERVAL_MS);
setInterval(() => {
  refreshRecordingStates().catch((error) => console.error(error));
}, PRINTER_RECORDING_POLL_INTERVAL_MS);
setInterval(() => {
  refreshTimelapseStates().catch((error) => console.error(error));
}, PRINTER_TIMELAPSE_POLL_INTERVAL_MS);
setInterval(updateFreshnessLabels, PRINTER_FRESHNESS_INTERVAL_MS);
