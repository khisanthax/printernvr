const PRINTER_POLL_INTERVAL_MS = 7000;
const PRINTER_FRESHNESS_INTERVAL_MS = 5000;
const PRINTER_VISIBILITY_KEY = "printernvr-visible-printers";
const PRINTER_VIEW_SELECTION_KEY = "printernvr-printer-view-selections";

let refreshInFlight = false;

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
  container.replaceChildren(createPreviewNode(printerName, view));
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
applySavedVisibility();
restoreStoredViews();
updateFreshnessLabels();
refreshPrinterCards().catch((error) => console.error(error));
setInterval(() => {
  refreshPrinterCards().catch((error) => console.error(error));
}, PRINTER_POLL_INTERVAL_MS);
setInterval(updateFreshnessLabels, PRINTER_FRESHNESS_INTERVAL_MS);
