const LIVE_POLL_INTERVAL_MS = 7000;
const LIVE_FRESHNESS_INTERVAL_MS = 5000;
const LIVE_VISIBILITY_KEY = "printernvr-live-visible-printers";
const LIVE_VIEW_SELECTION_KEY = "printernvr-printer-view-selections";

let liveRefreshInFlight = false;

function query(selector) {
  return document.querySelector(selector);
}

function queryAll(selector) {
  return Array.from(document.querySelectorAll(selector));
}

async function fetchJson(url) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
    },
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

  const currentText = Number(current).toFixed(0);
  const targetText = target === null || target === undefined || Number.isNaN(Number(target))
    ? "--"
    : Number(target).toFixed(0);
  return `${currentText} / ${targetText} C`;
}

function visiblePrinterIds() {
  return queryAll("[data-live-printer-toggle]")
    .filter((input) => input instanceof HTMLInputElement && input.checked)
    .map((input) => input.dataset.livePrinterToggle)
    .filter(Boolean);
}

function persistVisibility() {
  const selected = visiblePrinterIds();
  const known = queryAll("[data-live-printer-toggle]")
    .map((input) => input.dataset.livePrinterToggle)
    .filter(Boolean);
  writeStorageObject(LIVE_VISIBILITY_KEY, { selected, known });
}

function updateVisibleCards() {
  const visible = new Set(visiblePrinterIds());
  queryAll("[data-live-printer-card]").forEach((card) => {
    card.hidden = !visible.has(card.dataset.livePrinterCard);
  });

  const empty = query("#live-empty-filtered");
  if (empty) {
    const visibleCount = queryAll("[data-live-printer-card]").filter((card) => !card.hidden).length;
    empty.hidden = visibleCount !== 0;
  }
}

function applySavedVisibility() {
  const saved = readStorageObject(LIVE_VISIBILITY_KEY);
  const selected = Array.isArray(saved.selected) ? saved.selected : [];
  const known = Array.isArray(saved.known) ? saved.known : [];
  const selectedSet = new Set(selected);
  const knownSet = new Set(known);

  queryAll("[data-live-printer-toggle]").forEach((input) => {
    if (!(input instanceof HTMLInputElement)) {
      return;
    }
    const printerId = input.dataset.livePrinterToggle;
    input.checked = selectedSet.has(printerId) || !knownSet.has(printerId);
  });
  updateVisibleCards();
}

function setAllVisible(visible) {
  queryAll("[data-live-printer-toggle]").forEach((input) => {
    if (input instanceof HTMLInputElement) {
      input.checked = visible;
    }
  });
  persistVisibility();
  updateVisibleCards();
}

function readViewSelections() {
  return readStorageObject(LIVE_VIEW_SELECTION_KEY);
}

function persistViewSelection(printerId, cameraId) {
  const selections = readViewSelections();
  selections[printerId] = cameraId;
  writeStorageObject(LIVE_VIEW_SELECTION_KEY, selections);
}

function clearViewSelection(printerId) {
  const selections = readViewSelections();
  if (!(printerId in selections)) {
    return;
  }
  delete selections[printerId];
  writeStorageObject(LIVE_VIEW_SELECTION_KEY, selections);
}

function getCard(printerId) {
  return query(`[data-live-printer-card="${printerId}"]`);
}

function getViewSelect(printerId) {
  return query(`[data-live-view-select="${printerId}"]`);
}

function getPreviewContainer(printerId) {
  return query(`[data-live-preview="${printerId}"]`);
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

function getCurrentView(printerId) {
  const select = getViewSelect(printerId);
  if (select instanceof HTMLSelectElement && select.selectedOptions[0]) {
    return getViewFromOption(select.selectedOptions[0]);
  }

  const card = getCard(printerId);
  const preview = getPreviewContainer(printerId);
  const defaultCameraId = card ? card.dataset.defaultCameraId || "" : "";
  if (!defaultCameraId) {
    return null;
  }

  return {
    camera_id: defaultCameraId,
    camera_name: query(`[data-live-current-view-label="${printerId}"]`)?.textContent || defaultCameraId,
    preview_url: preview ? preview.dataset.previewUrl || "" : "",
    preview_mode: preview ? preview.dataset.previewMode || "none" : "none",
    preview_available: preview ? preview.dataset.previewAvailable === "true" : false,
    enabled: card.dataset.defaultCameraEnabled !== "false",
  };
}

function createPreviewNode(printerName, view) {
  if (view && view.preview_mode === "embedded" && view.preview_url) {
    const frame = document.createElement("iframe");
    frame.title = `${printerName} live view`;
    frame.src = view.preview_url;
    frame.loading = "lazy";
    frame.allowFullscreen = true;
    return frame;
  }

  if (view && view.preview_mode === "external_link" && view.preview_url) {
    const fallback = document.createElement("div");
    fallback.className = "live-wall-preview__fallback";

    const description = document.createElement("p");
    description.textContent = "Preview opens externally for this view.";

    const link = document.createElement("a");
    link.href = view.preview_url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Open Preview";

    fallback.append(description, link);
    return fallback;
  }

  const empty = document.createElement("div");
  empty.className = "live-wall-preview__fallback";
  empty.textContent = view && view.enabled === false ? "Camera disabled" : "Preview unavailable";
  return empty;
}

function renderPreview(printerId, view) {
  const container = getPreviewContainer(printerId);
  const card = getCard(printerId);
  const label = query(`[data-live-current-view-label="${printerId}"]`);
  if (!container || !card) {
    return;
  }

  const printerName = card.dataset.printerName || "Printer";
  if (label) {
    label.textContent = view && view.camera_name ? view.camera_name : "No default camera";
  }

  container.dataset.currentCameraId = view && view.camera_id ? view.camera_id : "";
  container.dataset.previewUrl = view && view.preview_url ? view.preview_url : "";
  container.dataset.previewMode = view && view.preview_mode ? view.preview_mode : "none";
  container.dataset.previewAvailable = view && view.preview_available ? "true" : "false";
  container.dataset.viewEnabled = view && view.enabled === false ? "false" : "true";
  container.replaceChildren(createPreviewNode(printerName, view));
}

function restoreStoredViewForPrinter(printerId) {
  const select = getViewSelect(printerId);
  if (!(select instanceof HTMLSelectElement)) {
    clearViewSelection(printerId);
    return;
  }

  const card = getCard(printerId);
  const defaultCameraId = card ? card.dataset.defaultCameraId || "" : "";
  const storedCameraId = readViewSelections()[printerId];
  let option = Array.from(select.options).find((candidate) => candidate.value === storedCameraId);

  if (!option) {
    option = Array.from(select.options).find((candidate) => candidate.value === defaultCameraId)
      || select.selectedOptions[0]
      || select.options[0];
    clearViewSelection(printerId);
  } else {
    select.value = storedCameraId;
  }

  if (option) {
    renderPreview(printerId, getViewFromOption(option));
  }
}

function restoreStoredViews() {
  queryAll("[data-live-printer-card]").forEach((card) => {
    const printerId = card.dataset.livePrinterCard;
    if (printerId) {
      restoreStoredViewForPrinter(printerId);
    }
  });
}

function statusTone(printer) {
  if (printer.connection_state === "offline") {
    return "offline";
  }

  const state = String(printer.monitor_state || "").toLowerCase();
  if (["printing", "idle", "complete", "paused", "error", "offline"].includes(state)) {
    return state;
  }
  return "unavailable";
}

function setStatus(printer) {
  const node = query(`[data-live-status="${printer.printer_id}"]`);
  if (!node) {
    return;
  }

  const tone = statusTone(printer);
  node.textContent = printer.printer_status_text || "Status unavailable";
  node.classList.remove(
    "live-wall-status--printing",
    "live-wall-status--idle",
    "live-wall-status--complete",
    "live-wall-status--paused",
    "live-wall-status--error",
    "live-wall-status--offline",
    "live-wall-status--unavailable",
  );
  node.classList.add(`live-wall-status--${tone}`);
}

function updateText(selector, value) {
  const node = query(selector);
  if (node) {
    node.textContent = value || "--";
  }
}

function setMetadataAttrs(printer) {
  const card = getCard(printer.printer_id);
  if (!card) {
    return;
  }

  const previousSuccessAt = card.dataset.lastMetadataSuccessAt || "";
  card.dataset.lastMetadataAttemptAt = printer.last_metadata_attempt_at || "";
  card.dataset.lastMetadataSuccessAt = printer.last_metadata_success_at || previousSuccessAt;
}

function formatFreshnessText(printerId) {
  const card = getCard(printerId);
  if (!card) {
    return "--";
  }

  const successAt = parseIsoDate(card.dataset.lastMetadataSuccessAt);
  const attemptAt = parseIsoDate(card.dataset.lastMetadataAttemptAt);
  if (!successAt) {
    return attemptAt ? "Waiting for status" : "No metadata source";
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
  queryAll("[data-live-updated-text]").forEach((node) => {
    node.textContent = formatFreshnessText(node.dataset.liveUpdatedText);
  });
}

function updateCard(printer) {
  setStatus(printer);
  setMetadataAttrs(printer);
  updateText(`[data-live-progress="${printer.printer_id}"]`, formatProgress(printer.progress_percent));
  updateText(`[data-live-file-name="${printer.printer_id}"]`, printer.current_file_name);
  updateText(
    `[data-live-extruder="${printer.printer_id}"]`,
    formatTemp(printer.extruder_current_temp, printer.extruder_target_temp),
  );
  updateText(
    `[data-live-bed="${printer.printer_id}"]`,
    formatTemp(printer.bed_current_temp, printer.bed_target_temp),
  );
  updateText(`[data-live-eta="${printer.printer_id}"]`, printer.eta_text);

  const errorNode = query(`[data-live-error="${printer.printer_id}"]`);
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

function domViewIds(printerId) {
  const select = getViewSelect(printerId);
  if (select instanceof HTMLSelectElement) {
    return Array.from(select.options).map((option) => option.value);
  }

  const card = getCard(printerId);
  return card && card.dataset.defaultCameraId ? [card.dataset.defaultCameraId] : [];
}

function viewConfigChanged(printer) {
  const card = getCard(printer.printer_id);
  if (!card) {
    return true;
  }

  if ((card.dataset.defaultCameraId || "") !== (printer.default_camera_id || "")) {
    return true;
  }

  const existingIds = domViewIds(printer.printer_id);
  const incomingIds = Array.isArray(printer.available_views)
    ? printer.available_views.map((view) => view.camera_id)
    : [];

  if (existingIds.length !== incomingIds.length) {
    return true;
  }

  return incomingIds.some((cameraId, index) => existingIds[index] !== cameraId);
}

async function refreshLiveCards() {
  if (liveRefreshInFlight) {
    return;
  }

  liveRefreshInFlight = true;
  try {
    const payload = await fetchJson("/api/printers/cards");
    const printers = payload.printers || [];
    const currentIds = new Set(queryAll("[data-live-printer-card]").map((card) => card.dataset.livePrinterCard));
    const payloadIds = new Set(printers.map((printer) => printer.printer_id));

    if (currentIds.size !== payloadIds.size || Array.from(payloadIds).some((id) => !currentIds.has(id))) {
      window.location.reload();
      return;
    }

    if (printers.some(viewConfigChanged)) {
      window.location.reload();
      return;
    }

    printers.forEach(updateCard);
    updateFreshnessLabels();
  } finally {
    liveRefreshInFlight = false;
  }
}

function bindVisibilityControls() {
  queryAll("[data-live-printer-toggle]").forEach((input) => {
    input.addEventListener("change", () => {
      persistVisibility();
      updateVisibleCards();
    });
  });

  const selectAll = query("#live-select-all");
  if (selectAll) {
    selectAll.addEventListener("click", () => setAllVisible(true));
  }

  const clearAll = query("#live-clear-all");
  if (clearAll) {
    clearAll.addEventListener("click", () => setAllVisible(false));
  }
}

function bindViewSelectors() {
  queryAll("[data-live-view-select]").forEach((select) => {
    if (!(select instanceof HTMLSelectElement)) {
      return;
    }

    select.addEventListener("change", () => {
      const printerId = select.dataset.liveViewSelect;
      const option = select.selectedOptions[0];
      if (!printerId || !option) {
        return;
      }

      persistViewSelection(printerId, option.value);
      renderPreview(printerId, getViewFromOption(option));
    });
  });
}

bindVisibilityControls();
bindViewSelectors();
applySavedVisibility();
restoreStoredViews();
updateFreshnessLabels();
refreshLiveCards().catch((error) => console.error(error));
setInterval(() => {
  refreshLiveCards().catch((error) => console.error(error));
}, LIVE_POLL_INTERVAL_MS);
setInterval(updateFreshnessLabels, LIVE_FRESHNESS_INTERVAL_MS);
