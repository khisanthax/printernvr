const PRINTER_POLL_INTERVAL_MS = 7000;
const PRINTER_VISIBILITY_KEY = "printernvr-visible-printers";

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
  window.localStorage.setItem(
    PRINTER_VISIBILITY_KEY,
    JSON.stringify({ selected: visible, known }),
  );
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
  if (!raw) {
    updateVisiblePrinterCards();
    return;
  }

  let saved = [];
  let known = [];
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
  const savedSet = new Set(Array.isArray(saved) ? saved : []);
  const knownSet = new Set(Array.isArray(known) ? known : []);

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

function setBadge(printerId, connectionState) {
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

function updateText(selector, value) {
  const node = query(selector);
  if (node) {
    node.textContent = value || "--";
  }
}

function updateCard(printer) {
  setBadge(printer.printer_id, printer.connection_state);
  updateText(`[data-printer-status-text="${printer.printer_id}"]`, printer.printer_status_text);
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

async function refreshPrinterCards() {
  const payload = await fetchJson("/api/printers/cards");
  const printers = payload.printers || [];
  const currentIds = new Set(queryAll("[data-printer-card]").map((card) => card.dataset.printerCard));
  const payloadIds = new Set(printers.map((printer) => printer.printer_id));

  if (currentIds.size !== payloadIds.size || Array.from(payloadIds).some((id) => !currentIds.has(id))) {
    window.location.reload();
    return;
  }

  printers.forEach(updateCard);
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
}

bindControls();
applySavedVisibility();
refreshPrinterCards().catch((error) => console.error(error));
setInterval(() => {
  refreshPrinterCards().catch((error) => console.error(error));
}, PRINTER_POLL_INTERVAL_MS);
