const el = (name) => document.getElementById(`timeline-${name}`);
const player = el("player");
let events = [];
let clips = [];
let video = null;
let estimate = null;
let duration = 0;
let listVersion = 0;
let videoVersion = 0;
let inClip = [];

function zeroFor(time) {
  const stamp = time?.frame_zero_at || "";
  return /(?:Z|[+-]\d\d:\d\d)$/i.test(stamp)
    ? Date.parse(stamp) - Number(time.correction_seconds ?? 0) * 1000 : NaN;
}

function currentZero() {
  return zeroFor({frame_zero_at: el("anchor").value.trim(), correction_seconds: el("correction").value});
}

function eventOffset(row, zero) {
  const source = el("clock").value === "source" && row.source_at;
  return (Date.parse(source || row.received_at) - zero) / 1000;
}

function syncOverlay() {
  const overlay = el("overlay");
  const zero = currentZero();
  overlay.hidden = !video || !Number.isFinite(zero) || !el("show-overlay").checked;
  if (overlay.hidden) return;
  const event = inClip.find(({offset}) => offset <= player.currentTime && player.currentTime < offset + 5)?.row;
  const stamp = new Date(zero + Math.floor(player.currentTime) * 1000);
  if (!Number.isFinite(stamp.getTime())) return;
  const summary = [`Video UTC: ${stamp.toISOString()}`];
  if (event) summary.push(`Source: ${event.source_at || "Unavailable"}`, `Received: ${event.received_at}`);
  overlay.textContent = summary.join("\n");
}

function setAlignment(calibration) {
  el("anchor").value = calibration?.frame_zero_at || estimate?.frame_zero_at || "";
  el("correction").value = calibration?.correction_seconds ?? 0;
  el("anchor-note").textContent = calibration
    ? "Using saved alignment for this clip."
    : estimate
      ? "Frame zero is estimated from FFmpeg progress. Adjust the correction against a visible event."
      : "This recording has no time anchor. Enter the known frame-zero time to align events.";
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json();
}

function videoPath(clip) {
  return `/api/timeline/video/${encodeURIComponent(clip.camera_id)}/${encodeURIComponent(clip.filename)}`;
}

function drawEvents() {
  const timeline = el("events");
  const zero = currentZero();
  const search = el("search").value.trim().toLowerCase();
  const kind = el("kind").value;
  const origin = el("origin").value;
  const rows = events.map((row) => ({row, offset: eventOffset(row, zero)}));
  inClip = video ? rows.filter(({offset}) => offset > -5 && offset < duration)
    .sort((a, b) => b.offset - a.offset) : [];
  const matching = rows.filter(({row, offset}) =>
    (!kind || row.kind === kind) && (!origin || row.origin === origin)
    && (!search || `${row.kind} ${row.message}`.toLowerCase().includes(search))
    && (!el("overlap").checked || (video && offset >= 0 && offset < duration)));
  timeline.replaceChildren();
  el("count").textContent = matching.length
    ? `Showing ${Math.min(500, matching.length)} of ${matching.length} matching events`
    : "No matching events.";
  for (const {row, offset} of matching.slice(-500).reverse()) {
    const tr = document.createElement("tr");
    for (const cell of [`${row.kind}: ${row.message}`, row.origin === "klipper-log" && row.source_at
      ? `${row.source_at} (log-derived)` : row.source_at || "Unavailable",
      row.received_at, row.klipper_eventtime?.toFixed(3) ?? "Unavailable"]) {
      tr.insertCell().textContent = cell;
    }
    const cell = tr.insertCell();
    if (video && offset >= 0 && offset < duration) {
      const jump = document.createElement("button");
      jump.type = "button";
      jump.className = "control-button";
      jump.textContent = `${offset.toFixed(2)}s`;
      jump.addEventListener("click", () => { player.currentTime = offset; });
      cell.append(jump);
    } else {
      cell.textContent = "—";
    }
    timeline.append(tr);
  }
  syncOverlay();
}

function fillClips(selected = "") {
  el("clip").replaceChildren(new Option("Choose a recording", ""));
  for (const clip of clips.filter((item) => item.camera_id === el("camera").value)) {
    el("clip").add(new Option(clip.filename, videoPath(clip)));
  }
  if (Array.from(el("clip").options).some((option) => option.value === selected)) el("clip").value = selected;
}

function fillFilter(field, key, label) {
  const select = el(field);
  const old = select.value;
  select.replaceChildren(new Option(label, ""));
  for (const value of [...new Set(events.map((row) => row[key]).filter(Boolean))].sort()) {
    select.add(new Option(value, value));
  }
  if ([...select.options].some((option) => option.value === old)) select.value = old;
}

async function selectClip(wallTime = NaN) {
  const ticket = ++videoVersion;
  const candidates = Number.isFinite(wallTime)
    ? clips.filter((item) => item.camera_id === el("camera").value && zeroFor(item.timing) <= wallTime)
      .sort((a, b) => zeroFor(b.timing) - zeroFor(a.timing)).slice(0, 10)
    : clips.filter((item) => videoPath(item) === el("clip").value);
  video = null;
  estimate = null;
  duration = 0;
  el("stage").hidden = true;
  player.removeAttribute("src");
  player.load();
  el("anchor").value = "";
  el("correction").value = 0;
  el("extract").disabled = true;
  el("save").disabled = true;
  el("reset").disabled = true;
  el("anchor-note").textContent = "Choose a completed MP4 to align events.";
  drawEvents();
  if (!candidates.length) {
    if (Number.isFinite(wallTime)) el("feedback").textContent = "No aligned recording for this camera at the selected time.";
    return;
  }
  try {
    let clip, metadata, seek;
    for (const candidate of candidates) {
      try {
        metadata = await getJson(videoPath(candidate));
      } catch (error) {
        if (!Number.isFinite(wallTime)) throw error;
        continue;
      }
      if (ticket !== videoVersion) return;
      seek = (wallTime - zeroFor(metadata.calibration || metadata.anchor)) / 1000;
      if (!Number.isFinite(wallTime) || (seek >= 0 && seek < metadata.duration)) {
        clip = candidate;
        break;
      }
    }
    if (ticket !== videoVersion) return;
    if (!clip) {
      el("feedback").textContent = "No aligned recording for this camera at the selected time.";
      return;
    }
    video = clip;
    duration = metadata.duration;
    el("clip").value = videoPath(clip);
    if (Number.isFinite(seek)) {
      player.addEventListener("loadedmetadata", () => {
        if (ticket === videoVersion) player.currentTime = seek;
      }, {once: true});
    }
    player.src = clip.preview_url;
    el("stage").hidden = false;
    el("in").value = 0;
    el("out").value = Math.min(duration, 120).toFixed(3);
    estimate = metadata.anchor;
    setAlignment(metadata.calibration);
    el("feedback").textContent = Number.isFinite(seek) ? "Switched camera at the same aligned time." : "";
    el("extract").disabled = false;
    el("save").disabled = false;
    el("reset").disabled = false;
    drawEvents();
  } catch (error) {
    if (ticket === videoVersion) el("feedback").textContent = error.message;
  }
}

async function updateAlignment(reset) {
  if (!video) return;
  const active = video;
  el("save").disabled = true;
  el("reset").disabled = true;
  try {
    const response = await fetch(`${videoPath(active)}/calibration`, {
      method: "PUT", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({calibration: reset ? null : {
        frame_zero_at: el("anchor").value.trim(),
        correction_seconds: Number(el("correction").value),
      }}),
    });
    const result = await response.json();
    if (video !== active) return;
    if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail
      : "Enter a timezone-aware frame-zero timestamp and a correction within 24 hours.");
    setAlignment(result.calibration);
    active.timing = result.calibration || estimate;
    drawEvents();
  } catch (error) {
    if (video === active) el("feedback").textContent = error.message;
  } finally {
    if (video === active) {
      el("save").disabled = false;
      el("reset").disabled = false;
    }
  }
}

async function loadEvents(clear) {
  const ticket = ++listVersion;
  if (clear) {
    clips = [];
    events = [];
    el("camera").replaceChildren();
    el("clip").replaceChildren();
    await selectClip();
  }
  const id = el("printer").value;
  if (!id) {
    el("feedback").textContent = "No printers configured.";
    return;
  }
  try {
    const data = await getJson(`/api/timeline/${encodeURIComponent(id)}`);
    if (ticket !== listVersion) return;
    const selected = video && videoPath(video);
    const camera = el("camera").value;
    clips = data.clips;
    events = data.events;
    el("camera").replaceChildren(...data.cameras.map((item) => new Option(item.name, item.id)));
    if (data.cameras.some((item) => item.id === camera)) el("camera").value = camera;
    else if (clips.length) el("camera").value = clips[0].camera_id;
    fillClips(selected);
    if (video && !el("clip").value) await selectClip();
    fillFilter("kind", "kind", "All types");
    fillFilter("origin", "origin", "All origins");
    drawEvents();
  } catch (error) {
    if (ticket === listVersion) el("feedback").textContent = error.message;
  }
}

el("printer").addEventListener("change", () => loadEvents(true));
el("refresh").addEventListener("click", () => loadEvents(false));
el("clip").addEventListener("change", () => selectClip());
el("camera").addEventListener("change", () => {
  const wallTime = video ? currentZero() + player.currentTime * 1000 : NaN;
  fillClips();
  selectClip(wallTime);
});
el("save").addEventListener("click", () => updateAlignment(false));
el("reset").addEventListener("click", () => updateAlignment(true));
for (const field of ["anchor", "correction", "clock", "kind", "origin", "overlap", "show-overlay"]) {
  el(field).addEventListener("change", drawEvents);
}
el("search").addEventListener("input", drawEvents);
player.addEventListener("timeupdate", syncOverlay);
player.addEventListener("error", () => {
  if (video) el("feedback").textContent = "This browser could not play the selected recording.";
});
el("import").addEventListener("click", async () => {
  const id = el("printer").value;
  const file = el("log").files[0];
  if (!id || !file || file.size > 2 * 1024 * 1024) {
    el("feedback").textContent = "Choose a printer and a log excerpt up to 2 MiB.";
    return;
  }
  el("import").disabled = true;
  try {
    const response = await fetch(`/api/timeline/${encodeURIComponent(id)}/klipper-log`, {
      method: "POST", headers: {"Content-Type": "text/plain"}, body: file,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Log import failed");
    if (id !== el("printer").value) return;
    el("feedback").textContent = result.imported || result.duplicates
      ? `Imported ${result.imported} events; skipped ${result.duplicates} duplicates.`
      : "No anchored Klipper events found.";
    await loadEvents(false);
  } catch (error) {
    el("feedback").textContent = error.message;
  } finally {
    el("import").disabled = false;
  }
});
el("mark-in").addEventListener("click", () => { if (video) el("in").value = player.currentTime.toFixed(3); });
el("mark-out").addEventListener("click", () => { if (video) el("out").value = player.currentTime.toFixed(3); });
el("extract").addEventListener("click", async () => {
  if (!video) return;
  const active = video;
  el("extract").disabled = true;
  try {
    el("feedback").textContent = "Extracting the selected segment…";
    const response = await fetch(`${videoPath(active)}/extract`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ start: Number(el("in").value), end: Number(el("out").value),
        timestamped: el("timestamped").checked, clock: el("clock").value }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(typeof error.detail === "string" ? error.detail : "Invalid clip selection");
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = /filename="?(timeline-[\w-]+\.mp4)/.exec(response.headers.get("content-disposition") || "")?.[1]
      || "timeline-segment.mp4";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
    el("feedback").textContent = "Segment downloaded. The original recording was preserved.";
  } catch (error) {
    el("feedback").textContent = error.message;
  } finally {
    if (video === active) el("extract").disabled = false;
  }
});
loadEvents(true);
