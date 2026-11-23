const el = (name) => document.getElementById(`timeline-${name}`);
const player = el("player");
let events = [];
let clips = [];
let video = null;
let estimate = null;
let duration = 0;
let listVersion = 0;
let videoVersion = 0;

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
  const value = el("anchor").value.trim();
  const anchor = /(?:Z|[+-]\d\d:\d\d)$/i.test(value) ? Date.parse(value) : NaN;
  const correction = Number(el("correction").value);
  const useSource = el("clock").value === "source";
  timeline.replaceChildren();
  for (const row of events.slice(-500).reverse()) {
    const stamp = useSource ? (row.source_at || row.received_at) : row.received_at;
    const offset = (Date.parse(stamp) - anchor) / 1000 + correction;
    const tr = document.createElement("tr");
    for (const cell of [`${row.kind}: ${row.message}`, row.source_at || "Unavailable",
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
}

async function selectClip() {
  const ticket = ++videoVersion;
  const clip = clips[el("clip").selectedIndex - 1];
  video = null;
  estimate = null;
  duration = 0;
  player.hidden = true;
  player.removeAttribute("src");
  player.load();
  el("anchor").value = "";
  el("correction").value = 0;
  el("extract").disabled = true;
  el("save").disabled = true;
  el("reset").disabled = true;
  el("anchor-note").textContent = "Choose a completed MP4 to align events.";
  drawEvents();
  if (!clip) return;
  try {
    const metadata = await getJson(videoPath(clip));
    if (ticket !== videoVersion) return;
    video = clip;
    duration = metadata.duration;
    player.src = clip.preview_url;
    player.hidden = false;
    el("in").value = 0;
    el("out").value = Math.min(duration, 120).toFixed(3);
    estimate = metadata.anchor;
    setAlignment(metadata.calibration);
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
    clips = data.clips;
    events = data.events;
    el("clip").replaceChildren(new Option("Choose a recording", ""));
    for (const clip of clips) {
      el("clip").add(new Option(`${clip.camera_id} / ${clip.filename}`, videoPath(clip)));
    }
    if (selected && clips.some((clip) => videoPath(clip) === selected)) el("clip").value = selected;
    else if (video) await selectClip();
    el("feedback").textContent = `${events.length} events loaded. Showing up to 500 most recently received.`;
    drawEvents();
  } catch (error) {
    if (ticket === listVersion) el("feedback").textContent = error.message;
  }
}

el("printer").addEventListener("change", () => loadEvents(true));
el("refresh").addEventListener("click", () => loadEvents(false));
el("clip").addEventListener("change", selectClip);
el("save").addEventListener("click", () => updateAlignment(false));
el("reset").addEventListener("click", () => updateAlignment(true));
for (const field of ["anchor", "correction", "clock"]) el(field).addEventListener("change", drawEvents);
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
      body: JSON.stringify({ start: Number(el("in").value), end: Number(el("out").value) }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(typeof error.detail === "string" ? error.detail : "Invalid clip selection");
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = "timeline-segment.mp4";
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
