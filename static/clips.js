const HANDLE_DB_NAME = "printernvr-download-targets";
const HANDLE_STORE_NAME = "handles";
const HANDLE_KEY = "clips-download-folder";

let currentClips = [];
const selectedClipKeys = new Set();
const downloadTargetState = {
  supported: typeof window.showDirectoryPicker === "function" && window.isSecureContext,
  persistenceSupported: typeof window.indexedDB !== "undefined",
  folderHandle: null,
  persistenceMode: "session-only",
};

function bySelector(selector) {
  return document.querySelector(selector);
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

function downloadUrl(cameraId, filename) {
  return `/api/clips/download/${encodeURIComponent(cameraId)}/${encodeURIComponent(filename)}`;
}

function previewUrl(cameraId, filename) {
  return `/api/clips/preview/${encodeURIComponent(cameraId)}/${encodeURIComponent(filename)}`;
}

function deleteUrl(cameraId, filename) {
  return `/api/clips/${encodeURIComponent(cameraId)}/${encodeURIComponent(filename)}`;
}

function updateFeedback(message = "", isError = false) {
  const node = bySelector("#clips-feedback");
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

function populateFilter(clips) {
  const select = bySelector("#clip-camera-filter");
  if (!select) {
    return;
  }

  const current = select.value;
  const existing = new Set(Array.from(select.options).map((option) => option.value));
  const cameraIds = Array.from(new Set(clips.map((clip) => clip.camera_id))).sort();

  cameraIds.forEach((cameraId) => {
    if (existing.has(cameraId)) {
      return;
    }

    const option = document.createElement("option");
    option.value = cameraId;
    option.textContent = cameraId;
    select.appendChild(option);
  });

  select.value = current;
}

function buildCell(label, value) {
  const cell = document.createElement("td");
  cell.dataset.label = label;
  cell.textContent = value;
  return cell;
}

function clipKey(cameraId, filename) {
  return `${cameraId}::${filename}`;
}

function getVisibleSelectedKeys() {
  return currentClips
    .map((clip) => clipKey(clip.camera_id, clip.filename))
    .filter((key) => selectedClipKeys.has(key));
}

function updateSelectionUi() {
  const selectedCount = getVisibleSelectedKeys().length;
  const countLabel = bySelector("#clips-selected-count");
  const downloadButton = bySelector("#download-selected-button");
  const clearButton = bySelector("#clear-selection-button");

  if (countLabel) {
    countLabel.textContent = `${selectedCount} selected`;
  }

  if (downloadButton) {
    downloadButton.disabled = selectedCount === 0;
  }

  if (clearButton) {
    clearButton.disabled = selectedCount === 0;
  }
}

function createDownloadLink(cameraId, filename) {
  const link = document.createElement("a");
  link.href = downloadUrl(cameraId, filename);
  link.download = filename;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

async function fetchClipBlob(cameraId, filename) {
  const response = await fetch(downloadUrl(cameraId, filename));
  if (!response.ok) {
    throw new Error(`Download failed for ${filename}`);
  }
  return response.blob();
}

function splitFilename(filename) {
  const lastDot = filename.lastIndexOf(".");
  if (lastDot <= 0) {
    return { base: filename, extension: "" };
  }

  return {
    base: filename.slice(0, lastDot),
    extension: filename.slice(lastDot),
  };
}

async function resolveUniqueFilename(directoryHandle, filename) {
  const { base, extension } = splitFilename(filename);
  let attempt = 0;

  while (true) {
    const candidate = attempt === 0 ? filename : `${base} (${attempt})${extension}`;
    try {
      await directoryHandle.getFileHandle(candidate, { create: false });
      attempt += 1;
    } catch (error) {
      if (error && error.name === "NotFoundError") {
        return candidate;
      }
      throw error;
    }
  }
}

async function ensureDirectoryPermission(directoryHandle, requestWrite = false) {
  if (!directoryHandle || typeof directoryHandle.queryPermission !== "function") {
    return false;
  }

  const options = { mode: "readwrite" };
  const current = await directoryHandle.queryPermission(options);
  if (current === "granted") {
    return true;
  }

  if (!requestWrite || typeof directoryHandle.requestPermission !== "function") {
    return false;
  }

  const requested = await directoryHandle.requestPermission(options);
  return requested === "granted";
}

function updateDownloadTargetUi() {
  const statusNode = bySelector("#download-target-status");
  const noteNode = bySelector("#download-target-note");
  const selectButton = bySelector("#select-download-folder-button");
  const clearButton = bySelector("#clear-download-folder-button");

  if (!statusNode || !noteNode || !selectButton || !clearButton) {
    return;
  }

  if (!downloadTargetState.supported) {
    statusNode.textContent = "Using browser downloads.";
    noteNode.textContent = "Direct folder save is available only in Chromium-based browsers on HTTPS or localhost.";
    selectButton.disabled = true;
    clearButton.disabled = true;
    return;
  }

  selectButton.disabled = false;
  clearButton.disabled = !downloadTargetState.folderHandle;

  if (!downloadTargetState.folderHandle) {
    statusNode.textContent = "Using browser downloads.";
    noteNode.textContent = downloadTargetState.persistenceMode === "indexeddb"
      ? "Select a folder to save downloads directly. Folder selection is restored when the browser keeps permission."
      : "Select a folder to save downloads directly. If the browser does not allow persistence, the selection lasts for the current session.";
    return;
  }

  statusNode.textContent = `Saving downloads to selected folder: ${downloadTargetState.folderHandle.name}`;
  noteNode.textContent = downloadTargetState.persistenceMode === "indexeddb"
    ? "Selected folder handle is stored in browser IndexedDB when the browser allows it."
    : "Selected folder is active for this browser session only.";
}

function buildPreviewContent(clip) {
  const wrapper = document.createElement("div");
  wrapper.className = "clip-preview-panel";

  const meta = document.createElement("div");
  meta.className = "clip-preview-panel__meta";
  meta.textContent = `Previewing ${clip.filename}`;

  const video = document.createElement("video");
  video.className = "clip-preview-player";
  video.controls = true;
  video.preload = "metadata";
  video.src = previewUrl(clip.camera_id, clip.filename);

  const error = document.createElement("p");
  error.className = "clip-preview-error";
  error.textContent = "Preview unavailable for this clip.";
  error.hidden = true;

  video.addEventListener("error", () => {
    error.hidden = false;
  });

  wrapper.append(meta, video, error);
  return wrapper;
}

function renderClips(clips) {
  const empty = bySelector("#clips-empty");
  const tableWrap = bySelector("#clips-table-wrap");
  const tbody = bySelector("#clips-table-body");
  if (!empty || !tableWrap || !tbody) {
    return;
  }

  currentClips = clips;
  selectedClipKeys.clear();
  tbody.innerHTML = "";

  if (!clips.length) {
    empty.hidden = false;
    tableWrap.hidden = true;
    updateSelectionUi();
    return;
  }

  empty.hidden = true;
  tableWrap.hidden = false;

  clips.forEach((clip) => {
    const key = clipKey(clip.camera_id, clip.filename);
    const row = document.createElement("tr");
    row.className = "clip-row";
    row.dataset.clipKey = key;

    const selectCell = document.createElement("td");
    selectCell.dataset.label = "Select";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "clip-select-checkbox";
    checkbox.dataset.clipKey = key;
    checkbox.dataset.cameraId = clip.camera_id;
    checkbox.dataset.filename = clip.filename;
    selectCell.appendChild(checkbox);
    row.appendChild(selectCell);

    row.appendChild(buildCell("Camera", clip.camera_id));

    const fileCell = document.createElement("td");
    fileCell.dataset.label = "Filename";
    const fileWrap = document.createElement("div");
    fileWrap.className = "clip-file";
    const fileName = document.createElement("strong");
    fileName.textContent = clip.filename;
    const filePath = document.createElement("span");
    filePath.className = "clip-file__path";
    filePath.textContent = clip.relative_path;
    fileWrap.append(fileName, filePath);
    fileCell.appendChild(fileWrap);
    row.appendChild(fileCell);

    row.appendChild(buildCell("Created", formatTimestamp(clip.created_at)));
    row.appendChild(buildCell("Size", clip.size_human));

    const statusCell = document.createElement("td");
    statusCell.dataset.label = "Status";
    const status = document.createElement("span");
    status.className = clip.active ? "status-chip status-chip--active" : "status-chip";
    status.textContent = clip.active ? "Active" : "Completed";
    statusCell.appendChild(status);
    row.appendChild(statusCell);

    const actionsCell = document.createElement("td");
    actionsCell.dataset.label = "Actions";
    const actions = document.createElement("div");
    actions.className = "table-actions";

    const previewButton = document.createElement("button");
    previewButton.type = "button";
    previewButton.className = "control-button control-button--secondary";
    previewButton.dataset.previewCameraId = clip.camera_id;
    previewButton.dataset.previewFilename = clip.filename;
    previewButton.textContent = "Preview";

    const download = document.createElement("a");
    download.className = "control-button control-button--secondary table-link";
    download.href = downloadUrl(clip.camera_id, clip.filename);
    download.dataset.downloadCameraId = clip.camera_id;
    download.dataset.downloadFilename = clip.filename;
    download.textContent = "Download";

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "control-button control-button--danger";
    remove.dataset.deleteCameraId = clip.camera_id;
    remove.dataset.deleteFilename = clip.filename;
    remove.textContent = "Delete";
    remove.disabled = clip.active;

    actions.append(previewButton, download, remove);
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

  updateSelectionUi();
}

async function loadClips() {
  const select = bySelector("#clip-camera-filter");
  const cameraId = select ? select.value : "";
  const query = cameraId ? `?camera_id=${encodeURIComponent(cameraId)}` : "";
  const payload = await fetchJson(`/api/clips${query}`);
  const clips = payload.clips || [];
  populateFilter(clips);
  renderClips(clips);

  const nextUrl = cameraId ? `/clips?camera_id=${encodeURIComponent(cameraId)}` : "/clips";
  window.history.replaceState({}, "", nextUrl);
  updateFeedback("");
}

async function deleteClip(cameraId, filename) {
  await fetchJson(deleteUrl(cameraId, filename), {
    method: "DELETE",
  });
}

function togglePreview(cameraId, filename, button) {
  const key = clipKey(cameraId, filename);
  const previewRow = document.querySelector(`.clip-preview-row[data-preview-key="${CSS.escape(key)}"]`);
  if (!previewRow) {
    return;
  }

  const previewCell = previewRow.querySelector("td");
  if (!previewCell) {
    return;
  }

  if (previewRow.hidden) {
    if (!previewCell.dataset.loaded) {
      const clip = currentClips.find((item) => item.camera_id === cameraId && item.filename === filename);
      if (!clip) {
        return;
      }
      previewCell.appendChild(buildPreviewContent(clip));
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

function openHandleDb() {
  return new Promise((resolve, reject) => {
    if (!downloadTargetState.persistenceSupported) {
      reject(new Error("IndexedDB unavailable"));
      return;
    }

    const request = window.indexedDB.open(HANDLE_DB_NAME, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(HANDLE_STORE_NAME)) {
        db.createObjectStore(HANDLE_STORE_NAME);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Unable to open IndexedDB"));
  });
}

async function loadPersistedFolderHandle() {
  if (!downloadTargetState.persistenceSupported) {
    return null;
  }

  try {
    const db = await openHandleDb();
    const handle = await new Promise((resolve, reject) => {
      const transaction = db.transaction(HANDLE_STORE_NAME, "readonly");
      const store = transaction.objectStore(HANDLE_STORE_NAME);
      const request = store.get(HANDLE_KEY);
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error || new Error("Unable to read saved folder handle"));
    });
    db.close();
    return handle;
  } catch (_error) {
    return null;
  }
}

async function persistFolderHandle(handle) {
  if (!downloadTargetState.persistenceSupported) {
    downloadTargetState.persistenceMode = "session-only";
    return false;
  }

  try {
    const db = await openHandleDb();
    await new Promise((resolve, reject) => {
      const transaction = db.transaction(HANDLE_STORE_NAME, "readwrite");
      const store = transaction.objectStore(HANDLE_STORE_NAME);
      const request = store.put(handle, HANDLE_KEY);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error || new Error("Unable to save folder handle"));
    });
    db.close();
    downloadTargetState.persistenceMode = "indexeddb";
    return true;
  } catch (_error) {
    downloadTargetState.persistenceMode = "session-only";
    return false;
  }
}

async function clearPersistedFolderHandle() {
  if (!downloadTargetState.persistenceSupported) {
    return;
  }

  try {
    const db = await openHandleDb();
    await new Promise((resolve, reject) => {
      const transaction = db.transaction(HANDLE_STORE_NAME, "readwrite");
      const store = transaction.objectStore(HANDLE_STORE_NAME);
      const request = store.delete(HANDLE_KEY);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error || new Error("Unable to clear folder handle"));
    });
    db.close();
  } catch (_error) {
    // Keep browser-download fallback even if IndexedDB cleanup fails.
  }
}

async function initializeDownloadTarget() {
  updateDownloadTargetUi();
  if (!downloadTargetState.supported) {
    return;
  }

  const persistedHandle = await loadPersistedFolderHandle();
  if (!persistedHandle) {
    updateDownloadTargetUi();
    return;
  }

  const hasPermission = await ensureDirectoryPermission(persistedHandle, false);
  if (!hasPermission) {
    await clearPersistedFolderHandle();
    downloadTargetState.folderHandle = null;
    downloadTargetState.persistenceMode = "session-only";
    updateDownloadTargetUi();
    return;
  }

  downloadTargetState.folderHandle = persistedHandle;
  downloadTargetState.persistenceMode = "indexeddb";
  updateDownloadTargetUi();
}

async function setDownloadFolder() {
  if (!downloadTargetState.supported) {
    updateFeedback("Direct folder save is not available in this browser. Using browser downloads instead.");
    return;
  }

  let handle;
  try {
    handle = await window.showDirectoryPicker();
  } catch (error) {
    if (error && error.name === "AbortError") {
      return;
    }
    throw error;
  }
  const granted = await ensureDirectoryPermission(handle, true);
  if (!granted) {
    downloadTargetState.folderHandle = null;
    await clearPersistedFolderHandle();
    updateDownloadTargetUi();
    throw new Error("Folder access denied; using browser downloads.");
  }

  downloadTargetState.folderHandle = handle;
  downloadTargetState.persistenceMode = "session-only";
  await persistFolderHandle(handle);
  updateDownloadTargetUi();
}

async function clearDownloadFolder() {
  downloadTargetState.folderHandle = null;
  downloadTargetState.persistenceMode = "session-only";
  await clearPersistedFolderHandle();
  updateDownloadTargetUi();
}

async function saveClipToSelectedFolder(cameraId, filename) {
  const handle = downloadTargetState.folderHandle;
  if (!downloadTargetState.supported || !handle) {
    throw new Error("No selected folder available");
  }

  const hasPermission = await ensureDirectoryPermission(handle, true);
  if (!hasPermission) {
    downloadTargetState.folderHandle = null;
    downloadTargetState.persistenceMode = "session-only";
    await clearPersistedFolderHandle();
    updateDownloadTargetUi();
    throw new Error("Folder access denied; using browser downloads.");
  }

  const blob = await fetchClipBlob(cameraId, filename);
  const safeFilename = await resolveUniqueFilename(handle, filename);
  const fileHandle = await handle.getFileHandle(safeFilename, { create: true });
  const writable = await fileHandle.createWritable();
  await writable.write(blob);
  await writable.close();
  return safeFilename;
}

async function trySaveClipToSelectedFolder(cameraId, filename) {
  try {
    const savedName = await saveClipToSelectedFolder(cameraId, filename);
    return { saved: true, fallback: false, filename: savedName };
  } catch (error) {
    createDownloadLink(cameraId, filename);
    return {
      saved: false,
      fallback: true,
      error: error instanceof Error ? error.message : String(error),
      filename,
    };
  }
}

async function handleSingleDownload(cameraId, filename) {
  if (!downloadTargetState.folderHandle || !downloadTargetState.supported) {
    createDownloadLink(cameraId, filename);
    return;
  }

  const result = await trySaveClipToSelectedFolder(cameraId, filename);
  if (result.saved) {
    const name = result.filename === filename ? filename : `${filename} as ${result.filename}`;
    updateFeedback(`Saved ${name} to the selected folder.`);
    return;
  }

  updateFeedback(`${result.error || "Direct save failed"} Falling back to browser download for ${filename}.`, true);
}

async function handleBulkDownload(clips) {
  if (!clips.length) {
    updateFeedback("Select at least one clip to download.", true);
    return;
  }

  if (!downloadTargetState.folderHandle || !downloadTargetState.supported) {
    clips.forEach((clip) => {
      createDownloadLink(clip.camera_id, clip.filename);
    });
    updateFeedback(`Started ${clips.length} download(s). Your browser may ask permission for multiple downloads.`);
    return;
  }

  let savedCount = 0;
  let fallbackCount = 0;

  for (const clip of clips) {
    const result = await trySaveClipToSelectedFolder(clip.camera_id, clip.filename);
    if (result.saved) {
      savedCount += 1;
    } else {
      fallbackCount += 1;
    }
  }

  if (!fallbackCount) {
    updateFeedback(`Saved ${savedCount} file(s) to the selected folder.`);
    return;
  }

  updateFeedback(`Saved ${savedCount} of ${clips.length} file(s) to the selected folder. ${fallbackCount} file(s) fell back to browser downloads.`, true);
}

function bindFilters() {
  const select = bySelector("#clip-camera-filter");
  const refreshButton = bySelector("#refresh-clips-button");
  const initial = document.body.dataset.initialCameraFilter || "";

  if (select) {
    select.value = initial;
    select.addEventListener("change", async () => {
      try {
        await loadClips();
      } catch (error) {
        updateFeedback(error.message, true);
      }
    });
  }

  if (refreshButton) {
    refreshButton.addEventListener("click", async () => {
      refreshButton.disabled = true;
      try {
        await loadClips();
      } catch (error) {
        updateFeedback(error.message, true);
      } finally {
        refreshButton.disabled = false;
      }
    });
  }
}

function bindSelection() {
  const tbody = bySelector("#clips-table-body");
  const selectAllButton = bySelector("#select-all-clips-button");
  const clearButton = bySelector("#clear-selection-button");
  const downloadSelectedButton = bySelector("#download-selected-button");

  if (tbody) {
    tbody.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement) || !target.classList.contains("clip-select-checkbox")) {
        return;
      }

      const key = target.dataset.clipKey;
      if (!key) {
        return;
      }

      if (target.checked) {
        selectedClipKeys.add(key);
      } else {
        selectedClipKeys.delete(key);
      }
      updateSelectionUi();
    });
  }

  if (selectAllButton) {
    selectAllButton.addEventListener("click", () => {
      document.querySelectorAll(".clip-select-checkbox").forEach((node) => {
        if (!(node instanceof HTMLInputElement)) {
          return;
        }
        node.checked = true;
        if (node.dataset.clipKey) {
          selectedClipKeys.add(node.dataset.clipKey);
        }
      });
      updateSelectionUi();
    });
  }

  if (clearButton) {
    clearButton.addEventListener("click", () => {
      selectedClipKeys.clear();
      document.querySelectorAll(".clip-select-checkbox").forEach((node) => {
        if (node instanceof HTMLInputElement) {
          node.checked = false;
        }
      });
      updateSelectionUi();
    });
  }

  if (downloadSelectedButton) {
    downloadSelectedButton.addEventListener("click", async () => {
      const clips = currentClips.filter((clip) => selectedClipKeys.has(clipKey(clip.camera_id, clip.filename)));
      try {
        await handleBulkDownload(clips);
      } catch (error) {
        updateFeedback(error.message, true);
      }
    });
  }
}

function bindDownloadTargetControls() {
  const selectButton = bySelector("#select-download-folder-button");
  const clearButton = bySelector("#clear-download-folder-button");

  if (selectButton) {
    selectButton.addEventListener("click", async () => {
      selectButton.disabled = true;
      try {
        await setDownloadFolder();
        if (downloadTargetState.folderHandle) {
          updateFeedback(`Using selected folder '${downloadTargetState.folderHandle.name}' for clip downloads.`);
        }
      } catch (error) {
        updateFeedback(error.message, true);
      } finally {
        updateDownloadTargetUi();
      }
    });
  }

  if (clearButton) {
    clearButton.addEventListener("click", async () => {
      clearButton.disabled = true;
      try {
        await clearDownloadFolder();
        updateFeedback("Selected folder cleared. Using browser downloads.");
      } finally {
        updateDownloadTargetUi();
      }
    });
  }
}

function bindTableActions() {
  const tbody = bySelector("#clips-table-body");
  if (!tbody) {
    return;
  }

  tbody.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    const downloadLink = target.closest("a[data-download-camera-id]");
    if (downloadLink instanceof HTMLAnchorElement) {
      if (!downloadTargetState.folderHandle || !downloadTargetState.supported) {
        return;
      }

      event.preventDefault();
      try {
        await handleSingleDownload(downloadLink.dataset.downloadCameraId, downloadLink.dataset.downloadFilename);
      } catch (error) {
        updateFeedback(error.message, true);
      }
      return;
    }

    if (target instanceof HTMLButtonElement && target.dataset.previewCameraId && target.dataset.previewFilename) {
      togglePreview(target.dataset.previewCameraId, target.dataset.previewFilename, target);
      return;
    }

    if (!(target instanceof HTMLButtonElement)) {
      return;
    }

    const cameraId = target.dataset.deleteCameraId;
    const filename = target.dataset.deleteFilename;
    if (!cameraId || !filename) {
      return;
    }

    const confirmed = window.confirm(`Delete clip '${filename}' from '${cameraId}'?`);
    if (!confirmed) {
      return;
    }

    target.disabled = true;
    try {
      await deleteClip(cameraId, filename);
      selectedClipKeys.delete(clipKey(cameraId, filename));
      updateFeedback(`Deleted ${filename}.`);
      await loadClips();
    } catch (error) {
      target.disabled = false;
      updateFeedback(error.message, true);
    }
  });
}

bindFilters();
bindSelection();
bindDownloadTargetControls();
bindTableActions();
initializeDownloadTarget()
  .catch(() => {
    downloadTargetState.folderHandle = null;
    updateDownloadTargetUi();
  })
  .finally(() => {
    loadClips().catch((error) => {
      updateFeedback(error.message, true);
    });
  });
