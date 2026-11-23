"""Real Chromium acceptance against isolated synthetic recordings (run directly)."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

from app.clips import ClipStore
from app.timeline import EventInput, Timeline


def browser_flow(base, browser, *, mobile):
    context = browser.new_context(viewport={"width": 375, "height": 812} if mobile else {
        "width": 1366, "height": 900,
    }, is_mobile=mobile, has_touch=mobile, accept_downloads=True)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{base}/timeline")
    expect(page.locator("#timeline-count")).to_have_text("Showing 2 of 2 matching events")
    page.locator("#timeline-camera").select_option("front")
    page.locator("#timeline-clip").select_option(label="front.mp4")
    player = page.locator("#timeline-player")
    expect(player).to_be_visible()
    page.wait_for_function("document.getElementById('timeline-player').readyState >= 1")
    expect(page.locator("#timeline-overlay")).to_contain_text("Video UTC")
    player.evaluate("async (video) => { video.muted = true; await video.play(); }")
    page.wait_for_function("document.getElementById('timeline-player').currentTime > .15")
    player.evaluate("(video) => video.pause()")

    page.locator("#timeline-search").fill("fixture warning")
    expect(page.locator("#timeline-events tr")).to_have_count(1)
    expect(page.locator("#timeline-count")).to_have_text("Showing 1 of 1 matching events")
    page.locator("#timeline-events button").click()
    page.wait_for_function("Math.abs(document.getElementById('timeline-player').currentTime - 1.5) < .08")
    expect(page.locator("#timeline-overlay")).to_contain_text("Source: 2026-01-01T00:00:01.500")
    expect(page.locator("#timeline-overlay")).to_contain_text("Received:")

    page.locator("#timeline-camera").select_option("side")
    expect(page.locator("#timeline-feedback")).to_have_text("Switched camera at the same aligned time.")
    expect(player).to_have_attribute("src", "/api/clips/preview/side/side.mp4")
    page.wait_for_function("Math.abs(document.getElementById('timeline-player').currentTime - 1) < .08")
    page.locator("#timeline-show-overlay").uncheck()
    expect(page.locator("#timeline-overlay")).to_be_hidden()
    page.locator("#timeline-show-overlay").check()

    page.locator(".timeline-import summary").click()
    page.locator("#timeline-log").set_input_files({
        "name": "klippy.log", "mimeType": "text/plain",
        "buffer": b"Start printer at fixture (1767225600.0 30.0)\nStats 31.5: fixture\n",
    })
    page.locator("#timeline-import").click()
    expect(page.locator("#timeline-feedback")).to_contain_text("Imported")
    page.locator("#timeline-search").clear()
    page.locator("#timeline-origin").select_option("klipper-log")
    expect(page.locator("#timeline-events tr")).to_have_count(2)
    expect(page.locator("#timeline-events")).to_contain_text("log-derived")

    if mobile:
        assert page.evaluate("document.documentElement.scrollWidth === window.innerWidth"), "Page overflows mobile viewport"
        assert page.locator(".clips-table-wrap").evaluate("(table) => table.scrollWidth > table.clientWidth")
    else:
        page.locator("#timeline-in").fill("0.5")
        page.locator("#timeline-out").fill("1.5")
        page.locator("#timeline-timestamped").check()
        page.locator("#timeline-correction").fill("-1")
        with page.expect_download(timeout=30_000) as download_info:
            page.locator("#timeline-extract").click()
        download = download_info.value
        assert download.suggested_filename == "timeline-20260101T000002Z.mp4", download.suggested_filename
        assert Path(download.path()).stat().st_size > 0
    page.locator("#timeline-camera").select_option("empty")
    expect(page.locator("#timeline-stage")).to_be_hidden()
    expect(page.locator("#timeline-feedback")).to_contain_text("No aligned recording")
    assert not errors, errors
    context.close()


def main():
    with tempfile.TemporaryDirectory(prefix="browser-test-", dir=Path.cwd()) as folder:
        root = Path(folder)
        recordings = root / "recordings"
        recordings.mkdir()
        cameras = [{"id": "empty", "name": "No footage", "mode": "manual_urls",
                    "record_url": "rtsp://fixture.invalid/unused"}]
        originals = {}
        for camera, zero in (("front", "00:00:00"), ("side", "00:00:00.500")):
            cameras.append({"id": camera, "name": camera.title(), "mode": "manual_urls",
                            "record_url": "rtsp://fixture.invalid/unused"})
            video = recordings / camera / f"{camera}.mp4"
            video.parent.mkdir()
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=15",
                            "-t", "4", "-c:v", "libx264", "-threads", "1", "-movflags", "+faststart",
                            str(video)], check=True, timeout=20)
            originals[video] = video.read_bytes()
            ClipStore(str(recordings)).save_recording_anchor(
                camera, video.name, {"frame_zero_at": f"2026-01-01T{zero}+00:00"},
            )
        config = root / "cameras.json"
        config.write_text(json.dumps({"printers": [{"id": "test", "name": "Fixture", "cameras": cameras}]}))
        store = Timeline(str(recordings))
        store.append("test", EventInput(kind="warning", message="fixture warning",
                                         source_at="2026-01-01T00:00:01.500+00:00"), "submitted")
        store.append("test", EventInput(kind="note", message="other event"), "submitted")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = str(sock.getsockname()[1])
        base = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env.update(APP_CONFIG_PATH=str(config), APP_APP_CONFIG_PATH=str(root / "app.json"),
                   APP_RECORDINGS_DIR=str(recordings), APP_LOGS_DIR=str(root / "logs"),
                   APP_ACCESS_PASSWORD="", APP_BIND_ADDRESS="127.0.0.1", PYTHONDONTWRITEBYTECODE="1")
        with (root / "server.log").open("w", encoding="utf-8") as log:
            server = subprocess.Popen([sys.executable, "-B", "-m", "uvicorn", "app.main:app",
                                       "--host", "127.0.0.1", "--port", port], env=env,
                                      stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 20
                while True:
                    try:
                        with urlopen(f"{base}/ready", timeout=1) as response:
                            assert response.status == 200
                        break
                    except (URLError, OSError):
                        if time.monotonic() >= deadline or server.poll() is not None:
                            raise RuntimeError(f"Fixture server did not start:\n{(root / 'server.log').read_text()}")
                        time.sleep(0.2)
                old = {key: os.environ.get(key) for key in ("TEMP", "TMP", "TMPDIR")}
                os.environ.update({key: folder for key in old})
                try:
                    with sync_playwright() as playwright:
                        options = {"channel": "chrome"} if os.name == "nt" else {}
                        browser = playwright.chromium.launch(**options)
                        browser_flow(base, browser, mobile=True)
                        # Restore only the two initial events for an independent desktop flow.
                        path = recordings / ".timeline" / "test.jsonl"
                        rows = [e for e in store.events("test") if e["origin"] == "submitted"]
                        path.write_text("".join(json.dumps(e) + "\n" for e in rows), encoding="utf-8")
                        browser_flow(base, browser, mobile=False)
                        browser.close()
                finally:
                    for key, value in old.items():
                        if value is None:
                            os.environ.pop(key, None)
                        else:
                            os.environ[key] = value
                assert all(video.read_bytes() == original for video, original in originals.items())
                print("Chromium timeline acceptance passed: desktop and 375px mobile viewport.")
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


if __name__ == "__main__":
    main()
