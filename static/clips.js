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

function renderClips(clips) {
  const empty = bySelector("#clips-empty");
  const tableWrap = bySelector("#clips-table-wrap");
  const tbody = bySelector("#clips-table-body");
  if (!empty || !tableWrap || !tbody) {
    return;
  }

  tbody.innerHTML = "";
  if (!clips.length) {
    empty.hidden = false;
    tableWrap.hidden = true;
    return;
  }

  empty.hidden = true;
  tableWrap.hidden = false;

  clips.forEach((clip) => {
    const row = document.createElement("tr");

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

    const download = document.createElement("a");
    download.className = "control-button control-button--secondary table-link";
    download.href = downloadUrl(clip.camera_id, clip.filename);
    download.textContent = "Download";

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "control-button control-button--danger";
    remove.dataset.deleteCameraId = clip.camera_id;
    remove.dataset.deleteFilename = clip.filename;
    remove.textContent = "Delete";
    remove.disabled = clip.active;

    actions.append(download, remove);
    actionsCell.appendChild(actions);
    row.appendChild(actionsCell);

    tbody.appendChild(row);
  });
}

function buildCell(label, value) {
  const cell = document.createElement("td");
  cell.dataset.label = label;
  cell.textContent = value;
  return cell;
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

function bindDeletes() {
  const tbody = bySelector("#clips-table-body");
  if (!tbody) {
    return;
  }

  tbody.addEventListener("click", async (event) => {
    const target = event.target;
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
      updateFeedback(`Deleted ${filename}.`);
      await loadClips();
    } catch (error) {
      target.disabled = false;
      updateFeedback(error.message, true);
    }
  });
}

bindFilters();
bindDeletes();
loadClips().catch((error) => {
  updateFeedback(error.message, true);
});
