# Experimental nozzle tracking

Run these programs from this directory on a workstation. They use a separate RTSP reader and write derived views into a new directory for each run. Printer NVR does not import them. Install Python 3.11+, NumPy, OpenCV, requests, psutil, FFmpeg and ffprobe. Guided calibration uses Tk. The optional live keyboard preview requires a GUI-enabled OpenCV build.

## First run

Set NOZZLE_RTSP privately to the camera's main RTSP stream or to a verified main-stream relay alias. The program probes the delivered dimensions. The Mercury Two relay alias tested in November provided 640 × 480, whereas the direct main stream provided 1280 × 960.

```sh
python track.py --live --mode A --output runs/cal --seconds 30
python track.py --live --mode C --actuate --calibration runs/cal/calibration.json --config private.json --output runs/hybrid
python benchmark.py native-sample.mkv runs/cal/calibration.json runs/controlled
```

Click two corners of a distinctive rigid toolhead feature, then the nozzle tip. The saved JSON records native coordinates and the adjacent PNG holds the reference appearance. Keep both together. Calibrate each camera at a representative working distance. Multi-scale search widens to the configured zone after lock loss. A missing detection holds the current crop and suppresses new jogs.

A centers a native-pixel crop. B keeps the crop centered on the sensor and jogs the camera according to predicted target error. C follows rapid movement digitally and requires sustained error before jogging. Joins between recording and tracking streams are unnecessary. Replay B/C requires --simulate. This shifts the recorded scene with a fixed delay and step size. Pixels outside the captured field of view cannot be recovered. Inspect frames.csv alongside tracked.mp4, especially when processing drops frames.

## Control configuration

Example private configuration for a V2:

```json
{
  "protocol": "dvrip", "id": "merucrytwo",
  "host_env": "CAMERA_HOST", "user_env": "CAMERA_USER", "password_env": "CAMERA_PASSWORD",
  "nvr_env": "RECORDER_BASE", "netsdk_env": "AMCREST_SDK_DLL",
  "hold": 0.08, "deadband": 0.10, "dwell_s": 0.55, "cooldown_s": 1,
  "horizon_s": 0.20, "crop_fraction": 0.45, "zone": [0,0,1,1],
  "max_excursion_deg": 15, "hold_file": "manual.hold"
}
```

The zone is normalized left, top, right, bottom. The deadband is a fraction of full-frame width or height. A positive X error commands Right. A positive Y error commands Down. Physical movement requires --actuate and an idle recorder/timelapse check. A and replay do not issue commands. Presence of hold_file suspends new tracking commands and holds the crop. Delete it to resume. An already dispatched pulse finishes with Stop. In preview, Space holds/resumes, Q exits, and C recalibrates a digital-only session. Physical sessions retain their initial background reference for restoration. Inspect restore.json for residual pixels, and verify framing when image registration fails.

The DVRIP worker needs the bridge module and its dependencies. The tested configuration ran the worker in the pinned bridge image on a diagnostic host. Set worker_prefix to an argument array ending in the Python executable, for example ssh, HOST, docker, run, --rm, -i, --cap-drop, ALL, --security-opt, no-new-privileges, IMAGE, python. Set worker_shell to true for SSH. The image used was ghcr.io/gaming09/amcrest-ptz-bridge@sha256:d3de05e863465c2c4537716dd5fed73f7c149260b63e863b4f44a0ff567780b9. An existing authenticated SSH session must work noninteractively. Camera credentials travel on private stdin. The worker arms a second-session Stop timer, sends one start, then stops explicitly and retries Stop after a reconnect if necessary. It never retries a stale start. The optional Windows NetSDK DLL provides angle feedback and a per-session excursion limit. Keep the DLL and credentials outside Git. [Bridge implementation](https://github.com/gaming09/amcrest-ptz-bridge)

For ONVIF, use protocol onvif, specify the verified port and profile, and omit the SDK/worker settings. The adapter discovers the PTZ service and sends authenticated ContinuousMove with a one-second camera timeout and explicit Stop. Verify orientation and pulse length on each mount.

## Klipper read-only lookahead

queue_feed.py takes the Klipper API socket path and emits JSON lines for estimated print time, live XYZ and trapezoid-queue samples. It only subscribes to motion_report/dump_trapq and queries status. For remote use, configure queue_command as an argument array that runs the reader over SSH. It can also be streamed to python3 - SOCKET for diagnostic use without installing anything on the printer.

If a queue command is configured, provide pixels_per_mm as a 2 × 3 local projection matrix. Estimate its columns from native-pixel nozzle displacements and paired XYZ changes observed during normal motion, with the camera stationary. A fixed matrix is a local approximation and requires recalibration across large view changes. QueuePrediction interpolates both ends of the requested horizon using segment start velocity and acceleration. Missing segments or stale clock samples fall back to image velocity. Clock estimates use response arrival time. A moving-print test must establish synchronization and future queue coverage before relying on this path. [Klipper API](https://www.klipper3d.org/API_Server.html#motion_reportdump_trapq)

## Measurements

The benchmark translates the first native frame along a known trajectory and masks the calibrated feature for one second. The experiment has exact image-space labels and a simulated actuator. It writes per-mode scores, timed frame traces and separate videos. Its detail metric compares encoded versus source Laplacian variance in a 24 × 24 target patch. Interpret it as contrast retention. It does not measure extrusion quality. Live runtime reports application and local process-tree usage, decoded frame dimensions, tracking duration and dispatch-to-first-delivered-background-shift latency when measurable. Camera exposure time, player display delay and remote worker CPU require separate instrumentation. Consult the canonical logbook for actual hardware results.
