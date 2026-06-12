let currentTimelapses = [];

function bySelector(selector) {
  return document.querySelector(selector);
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

function timelapseKey(item) {
  return `${item.printer_id}::${item.session_id}::${item.filename}`;
}

function timelapseDeleteUrl(item) {
  return `/api/timelapse/${encodeURIComponent(item.printer_id)}/${encodeURIComponent(item.session_id)}/${encodeURIComponent(item.filename)}`;
}

function updateFeedback(message = "", isError = false) {
  const node = bySelector("#timelapses-feedback");
  if (!node) {
    return;
  }

  if (!message) {
    node.hidden = true;
    node.textContent = "";
    node.classList.remove("storage-warning", "camera-error");
    return;
  }

  node.hidden = false;
  node.textContent = message;
  node.classList.remove("storage-warning", "camera-error");
  node.classList.add(isError ? "camera-error" : "storage-summary");
}

function buildCell(label, value) {
  const cell = document.createElement("td");
  cell.dataset.label = label;
  cell.textContent = value || "--";
  return cell;
}

function populatePrinterFilter(items) {
  const select = bySelector("#timelapse-printer-filter");
  if (!select) {
    return;
  }

  const current = select.value;
  const existing = new Set(Array.from(select.options).map((option) => option.value));
  const printerIds = Array.from(new Set(items.map((item) => item.printer_id))).sort();

  printerIds.forEach((printerId) => {
    if (existing.has(printerId)) {
      return;
    }

    const option = document.createElement("option");
    option.value = printerId;
    option.textContent = printerId;
    select.appendChild(option);
  });

  select.value = current;
}

function filteredTimelapses() {
  const printerFilter = bySelector("#timelapse-printer-filter");
  const searchFilter = bySelector("#timelapse-search-filter");
  const printerId = printerFilter ? printerFilter.value : "";
  const search = searchFilter ? searchFilter.value.trim().toLowerCase() : "";

  return currentTimelapses.filter((item) => {
    if (printerId && item.printer_id !== printerId) {
      return false;
    }
    if (!search) {
      return true;
    }
    return [
      item.printer_id,
      item.printer_name,
      item.camera_id,
      item.camera_name,
      item.session_id,
      item.filename,
      item.relative_path,
    ].some((value) => String(value || "").toLowerCase().includes(search));
  });
}

function buildPreviewContent(item) {
  const wrapper = document.createElement("div");
  wrapper.className = "clip-preview-panel";

  const meta = document.createElement("div");
  meta.className = "clip-preview-panel__meta";
  meta.textContent = `Previewing ${item.filename}`;

  const video = document.createElement("video");
  video.className = "clip-preview-player";
  video.controls = true;
  video.preload = "metadata";
  video.src = item.preview_url;

  const error = document.createElement("p");
  error.className = "clip-preview-error";
  error.textContent = "Preview unavailable for this timelapse.";
  error.hidden = true;

  video.addEventListener("error", () => {
    error.hidden = false;
  });

  wrapper.append(meta, video, error);
  return wrapper;
}

function renderTimelapses(items) {
  const empty = bySelector("#timelapses-empty");
  const tableWrap = bySelector("#timelapses-table-wrap");
  const tbody = bySelector("#timelapses-table-body");
  if (!empty || !tableWrap || !tbody) {
    return;
  }

  tbody.innerHTML = "";

  if (!items.length) {
    empty.hidden = false;
    tableWrap.hidden = true;
    return;
  }

  empty.hidden = true;
  tableWrap.hidden = false;

  items.forEach((item) => {
    const key = timelapseKey(item);
    const row = document.createElement("tr");
    row.className = "clip-row";
    row.dataset.timelapseKey = key;

    row.appendChild(buildCell("Printer", item.printer_name || item.printer_id));
    row.appendChild(buildCell("Camera", item.camera_name || item.camera_id || "--"));

    const fileCell = document.createElement("td");
    fileCell.dataset.label = "Filename";
    const fileWrap = document.createElement("div");
    fileWrap.className = "clip-file";
    const fileName = document.createElement("strong");
    fileName.textContent = item.filename;
    const filePath = document.createElement("span");
    filePath.className = "clip-file__path";
    filePath.textContent = item.relative_path;
    fileWrap.append(fileName, filePath);
    fileCell.appendChild(fileWrap);
    row.appendChild(fileCell);

    row.appendChild(buildCell("Created", formatTimestamp(item.created_at)));
    row.appendChild(buildCell("Frames", String(item.frame_count || 0)));
    row.appendChild(buildCell("Size", item.size_human));

    const actionsCell = document.createElement("td");
    actionsCell.dataset.label = "Actions";
    const actions = document.createElement("div");
    actions.className = "table-actions";

    const previewButton = document.createElement("button");
    previewButton.type = "button";
    previewButton.className = "control-button control-button--secondary";
    previewButton.dataset.previewTimelapseKey = key;
    previewButton.textContent = "Preview";

    const downloadLink = document.createElement("a");
    downloadLink.className = "control-button control-button--secondary table-link";
    downloadLink.href = item.download_url;
    downloadLink.download = item.filename;
    downloadLink.textContent = "Download";

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "control-button control-button--danger";
    deleteButton.dataset.deleteTimelapseKey = key;
    deleteButton.textContent = "Delete";

    actions.append(previewButton, downloadLink, deleteButton);
    actionsCell.appendChild(actions);
    row.appendChild(actionsCell);

    const previewRow = document.createElement("tr");
    previewRow.className = "clip-preview-row";
    previewRow.dataset.previewKey = key;
    previewRow.hidden = true;

    const previewCell = document.createElement("td");
    previewCell.colSpan = 7;
    previewCell.dataset.label = "Preview";
    previewCell.className = "clip-preview-row__cell";
    previewRow.appendChild(previewCell);

    tbody.append(row, previewRow);
  });
}

async function loadTimelapses() {
  const payload = await fetchJson("/api/timelapse/outputs");
  currentTimelapses = payload.timelapses || [];
  populatePrinterFilter(currentTimelapses);
  renderTimelapses(filteredTimelapses());
  updateFeedback("");
}

function applyFilters() {
  renderTimelapses(filteredTimelapses());
}

function togglePreview(key, button) {
  const item = currentTimelapses.find((candidate) => timelapseKey(candidate) === key);
  const previewRow = document.querySelector(`.clip-preview-row[data-preview-key="${CSS.escape(key)}"]`);
  if (!item || !previewRow) {
    return;
  }

  const previewCell = previewRow.querySelector("td");
  if (!previewCell) {
    return;
  }

  if (previewRow.hidden) {
    if (!previewCell.dataset.loaded) {
      previewCell.appendChild(buildPreviewContent(item));
      previewCell.dataset.loaded = "true";
    }
    previewRow.hidden = false;
    button.textContent = "Hide Preview";
    button.setAttribute("aria-expanded", "true");
    return;
  }

  previewRow.hidden = true;
  button.textContent = "Preview";
  button.setAttribute("aria-expanded", "false");
}

async function deleteTimelapse(key) {
  const item = currentTimelapses.find((candidate) => timelapseKey(candidate) === key);
  if (!item) {
    return;
  }

  const confirmed = window.confirm(`Delete timelapse '${item.filename}'? This removes the rendered MP4 and source frames.`);
  if (!confirmed) {
    return;
  }

  await fetchJson(timelapseDeleteUrl(item), { method: "DELETE" });
  await loadTimelapses();
  updateFeedback(`Deleted ${item.filename}.`);
}

function bindFilters() {
  const printerFilter = bySelector("#timelapse-printer-filter");
  const searchFilter = bySelector("#timelapse-search-filter");
  const clearButton = bySelector("#clear-timelapse-filters-button");
  const refreshButton = bySelector("#refresh-timelapses-button");

  if (printerFilter) {
    printerFilter.addEventListener("change", applyFilters);
  }

  if (searchFilter) {
    searchFilter.addEventListener("input", applyFilters);
    searchFilter.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        applyFilters();
      }
    });
    searchFilter.addEventListener("search", applyFilters);
  }

  if (clearButton) {
    clearButton.addEventListener("click", () => {
      if (printerFilter) {
        printerFilter.value = "";
      }
      if (searchFilter) {
        searchFilter.value = "";
      }
      applyFilters();
    });
  }

  if (refreshButton) {
    refreshButton.addEventListener("click", async () => {
      refreshButton.disabled = true;
      try {
        await loadTimelapses();
      } catch (error) {
        updateFeedback(error.message, true);
      } finally {
        refreshButton.disabled = false;
      }
    });
  }
}

function bindTableActions() {
  const tbody = bySelector("#timelapses-table-body");
  if (!tbody) {
    return;
  }

  tbody.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLButtonElement)) {
      return;
    }

    if (target.dataset.previewTimelapseKey) {
      togglePreview(target.dataset.previewTimelapseKey, target);
      return;
    }

    if (target.dataset.deleteTimelapseKey) {
      target.disabled = true;
      try {
        await deleteTimelapse(target.dataset.deleteTimelapseKey);
      } catch (error) {
        updateFeedback(error.message, true);
        target.disabled = false;
      }
    }
  });
}

bindFilters();
bindTableActions();
loadTimelapses().catch((error) => {
  updateFeedback(error.message, true);
});
