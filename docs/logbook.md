# Printer NVR procedure logbook

Use this append-only log to hand work between Codex and ChatGPT. Read the latest entries before continuing an existing procedure. The roadmap tracks planned work and the audit retains the original findings.

## What to record

For every procedure, log the date, purpose, steps or commands, environment, commit or branch, observed results, and the evidence needed to reproduce or verify them. Include failed attempts and partial results, skipped checks with reasons, resulting changes, and any next step. Group related checks under the same procedure and record each outcome. Link to commits, pull requests, CI runs, and relevant repository files. Keep conclusions separate from unverified assumptions. Redact credentials, tokens, private keys, and sensitive deployment configuration. Commit log updates to the project repository alongside the work they describe.

## 2026-11-23 | Establish the repository logbook

- **Procedure.** Checked whether this file already existed on the hardening branch, verified the branch head, and looked up GitHub Actions for that commit.
- **Results.** GitHub reported no existing logbook. The branch head was `b202010aca9a3a6ec39c15ecece2e2a4219f8b41` before this entry. GitHub Actions reported the `Tests` workflow completed successfully for that commit. [Workflow run](https://github.com/khisanthax/printernvr/actions/runs/45074450816)
- **Change.** Added this logbook to the project repository on `printernvr-hardening`, the branch behind [draft PR #1](https://github.com/khisanthax/printernvr/pull/1).

## 2026-11-22 | Hardening verification baseline

- **Recording and tests.** Eleven regression tests passed on Windows and Ubuntu. Local checks also passed for JavaScript syntax, all six page handlers rendered with fixtures, and Compose configuration. Coverage included graceful manual Stop, timed capture, invalid output rejection, staging protection, deletion policy, review concurrency, inventory and optimization with the original preserved, interrupted timelapse retry, and auto-start and layer eligibility.
- **Dependencies and deployment.** The dependency audit passed. The disposable Docker test performed a fresh install and a simulated fast-forward upgrade with optional bundled go2rtc. Readiness and all page routes responded successfully, and file checksums confirmed that the fixture configuration and recording survived. [CI evidence](https://github.com/khisanthax/printernvr/actions/runs/45074237667)
- **Failed local attempts.** The local Docker engine was unavailable. Installing the pinned dependencies and pushing via the local Git CLI failed in that environment. GitHub Actions provided independent deployment and dependency verification, and the GitHub connector published the branch after checking its file tree against the local tree.
- **Open.** Real-camera behavior, browser acceptance, production compression savings, and the remaining engineering checks in the [roadmap](ROADMAP.md) and [project audit](PROJECT-AUDIT.md) remain open. No production deployment or media was changed.

## 2026-11-23 | Check logbook placement across projects

- **Procedure.** Listed repositories through the GitHub connector and sampled 13 repositories including Printer NVR. On `main`, checked `LOGBOOK.md`, `logbook.md`, `docs/LOGBOOK.md`, and `docs/logbook.md`.
- **Results.** Two files were found across 52 path checks. [Klipper Cost Dashboard](https://github.com/khisanthax/klipper-cost-dashboard/blob/main/LOGBOOK.md) and [TDX Chat Relay](https://github.com/khisanthax/tdx-chat-relay/blob/main/docs/LOGBOOK.md) both keep their logbooks on `main`. The other 50 checks returned 404, including the four Printer NVR `main` paths. This sample did not check other file names or feature branches.
- **Decision.** Recorded the comparison. Printer NVR's logbook remains on the hardening branch pending a decision about moving it to `main`.

## 2026-11-23 | Establish the canonical logbook on main

- **Procedure.** Checked for `docs/logbook.md` on `main` and `printernvr-hardening` using the GitHub connector. The file was absent from `main` and present on the hardening branch.
- **Result.** Copied the complete logbook to `main` in a documentation-only commit. [Draft PR #1](https://github.com/khisanthax/printernvr/pull/1) remains separate.
- **Follow-up.** Use this copy on `main` for future procedure results, including results from work on other branches.

## 2026-11-24 | Amcrest ASH21-B-V2 local pan and tilt

**Decision.** Reuse Mercury Two, SV07 and SV08 for manual jogging and occasional automatic reframing. For continuous predictive nozzle tracking, use a fixed view with digital cropping where the image resolution suffices, or qualify a different PTZ head if physical tracking is required. Timing jitter, variable displacement, single-axis motion and unverified absolute pointing prevent a reliable open-loop trajectory. The tests used idle recorder channels and stationary scene features. Tracking error against a running nozzle and end-to-end video latency remain unmeasured.

| Camera | Hardware / installed firmware | Verified local controls | Pan displacement at speed 1 → 4, 180 ms hold | Shortest repeatable pan hold in this sample | Start / Stop ACK range, ms |
|---|---|---|---|---|---|
| Mercury Two | ASH21-B-V2 / hardware ID 1.00 / 2.680.00AC008.0.R | DVRIP left, right, up, down, Stop, speed selection. NetSDK pan/tilt readback. | 32–49 → 135 px (speed 4 right) | 80 ms, 6/6. At 40 ms one start failed. | 6–202 / 6–76 |
| SV07 | ASH21-B-V2 / hardware ID 1.00 / 2.680.00AC008.0.R | DVRIP left, right, up, down, Stop, speed selection. NetSDK pan/tilt readback. | 16–19 → 57–58 px | 80 ms, 6/6. Smallest shift 3 px. | 11–32 / 9–75 |
| SV08 | ASH21-B-V2 / hardware ID 1.00 / 2.680.00AC008.0.R | DVRIP left, right, up, down, Stop, speed selection. NetSDK pan/tilt readback. | 10–12 → 45–52 px | 180 ms, 6/6. At 80 ms several pulses produced zero shift. | 8–39 / 8–105 |

### Interfaces, firmware and cause of the ONVIF failure

- Each camera returned the same model, hardware ID and firmware build date (2022-04-06) via ONVIF GetDeviceInformation. The authenticated account reported Administrator via GetUsers. GetServices and GetCapabilities omitted PTZ. Neither Media nor Media2 profile included a PTZ configuration. GetStatus on both Profile000 and Profile001 returned ActionNotSupported / NotImplemented. Earlier separate-axis ContinuousMove, RelativeMove, Stop and GetPresets also faulted. The installed V2 ONVIF implementation is the strongest explanation. A camera-side setting that selectively enables ONVIF PTZ is unverified. E5P is a V3 with different firmware and verified ONVIF continuous movement.
- The official ASH21-B-V2 listing matches the installed version and date. No newer public build for this revision was identified. In-app staged firmware availability was not verified. [Official SmartHome firmware catalog](https://www.amcrest.com/pages/firmware-ash) and [dated Amcrest listing](https://dev.amcrest.com/firmware-ash).
- Digest-capable CGI client, channel 1, port 80. On each camera, ptz.cgi actions getStatus, getCurrentProtocolCaps, getPresets, stop (Right, arguments 0/1/0), and moveRelatively (zero vector) timed out. The hardware-version CGI and ordinary HTTP RPC2 login challenge also timed out. The relative request took 2.00–2.03 s to reach its client timeout. The capability query on port 8086 failed to connect or obtain an HTTP response. No usable HTTP authentication challenge was established. Home Assistant's Amcrest integration and open-source HTTP clients expose this family of controls, so installing another CGI client offers little benefit here. [Amcrest HTTP SDK](https://support.amcrest.com/hc/en-us/articles/24359277217421-Amcrest-HTTP-API-SDK), [Home Assistant Amcrest](https://www.home-assistant.io/integrations/amcrest/), [amdacli](https://github.com/BourgeoisBear/amdacli), [Dahua Home Assistant integration](https://github.com/rroller/dahua).
- Amcrest documents authenticated LAN IP/domain access in Surveillance Pro. The mobile SmartHome app supports pan/tilt. Its exact wire protocol was not observed. The open-source ASH21 bridge demonstrates authenticated DVRIP on TCP 37777. This investigation used its controller in disposable diagnostic processes with default credential authentication, channel 0 and no listening bridge service. [Amcrest Surveillance Pro procedure](https://support.amcrest.com/hc/en-us/articles/360039064232-How-to-Add-Your-Camera-Into-Amcrest-Surveillance-Pro-ASH21), [Amcrest V2 setup](https://support.amcrest.com/hc/en-us/articles/4411396353933-How-To-Setup-the-ASH21-V2-Using-the-Ethernet-Only-Method), [bridge implementation](https://github.com/gaming09/amcrest-ptz-bridge).

### Commands and observations

1. Mercury Two was probed first. Authenticated DVRIP ptz.factory.instance(channel=0), ptz.getCurrentProtocolCaps and ptz.listMethod succeeded. The service listed start, stop, capability query, factory and method listing. Its capability data advertised pan, tilt, absolute motion and 25 preset slots, and explicitly excluded all four diagonal directions. ptz.getStatus, ptz.getPresets and ptz.moveRelatively returned InterfaceNotFound. A read of the PtzPreset configuration also failed.
2. Movement used ptz.start and ptz.stop on the same object with channel, direction, horizontal speed in arg1, vertical speed in arg2 and zero in arg3. The harness checked NVR/timelapse status, paired moves with explicit Stop and set an 850 ms fallback Stop timer. Comparison used successive JPEGs from the existing relay, resized to 640 × 360, with optical flow, forward/backward consistency and robust affine fitting. ACK latency is RPC round-trip time. The hold starts after the start ACK. Sparse JPEG sampling cannot measure first visible motion latency or the exact braking time.
3. Image evidence verified each cardinal direction. Speed 4 produced larger displacements at the same hold time. Both tested diagonal commands (RightUp and LeftDown) acknowledged without measurable displacement on every camera. Settled frame pairs showed at most about 0.1 px drift. Older persistent sessions sometimes failed a start or Stop. A fresh session could issue Stop successfully. This makes session liveness and independent Stop recovery essential. One initial Mercury login failed transiently. A parallel diagnostic harness failed during output capture and was rerun in isolated processes.
4. The installed 64-bit Amcrest Surveillance Pro NetSDK (DLL 3.5.0.41370) authenticated via CLIENT_LoginEx2 on all cameras. CLIENT_QueryDevState(0x36) returned changing pan and tilt in tenths of a degree, including intermediate values. CLIENT_DHPTZControlEx2 idle Right Stop returned 0x80000007. The structured absolute command 0x45 returned failure (0xffffffff) on all three. ExactGoto (0x43), targeting current pan +4°, same tilt and zoom, acknowledged on each without a measurable pose or image change. A +1° Mercury trial also had no effect. Native relative positioning remains unverified. Opposite timed jogs gave unequal displacement. They should not be exposed as a calibrated relative move.
5. CLIENT_QueryDevState(0x57) preset-list requests failed on all three (0x8000004f). Without a verified stored token or known vacant slot, preset save/recall was left unverified. Existing presets were preserved. [NetSDK function and structure reference](https://github.com/txline0420/general-netsdk-springboot/blob/main/src/main/java/com/netsdk/lib/NetSDKLib.java).
6. After paired pulses and framing corrections, final NetSDK pan/tilt residuals against the reference were Mercury Two +0.3°/+1.0°, SV07 +1.0°/+0.7°, and SV08 −1.1°/+0.6°. SV07 and SV08 references preceded their tests. Mercury Two's first angle reference came **after** movement began, so its exact original framing could not be certified. The final check found all seven recorder channels idle, no active timelapse, and valid JPEGs for all three V2s. No production application, firmware or camera settings were changed.

### Printer NVR adapter proposal

Key capabilities by camera, hardware, firmware and protocol. Bind these V2s to a DVRIP motion adapter and optional NetSDK pose reader. Use a separate ONVIF motion adapter for E5P. The unified interface should expose verified capabilities, bounded single-axis jog, preemptive Stop, and timestamped pose where available. Treat absolute, native relative, diagonal and preset operations as unavailable until independently demonstrated. Keep credentials and device addresses server-side and separate command handling from media capture.

Serialize moves per physical camera, check recording policy before each jog, maintain a session heartbeat, and give Stop a reconnect path independent of the active move. Never replay a stale start after reconnect. Return command acceptance, pose age and image verification as separate observations. For occasional automatic reframing, use image feedback with a deadband and wait for settling before another correction. A predictive-tracking qualification would need synchronized nozzle telemetry, frame timestamps, repeated per-axis response curves, reversal error, and tracking-error measurements at actual printing speeds.

<details><summary>Redacted individual motion measurements</summary>

Columns give camera, direction, speed, requested post-ACK hold (ms), (start accepted, start ACK ms, Stop ACK ms), then three [x,y] image shifts in pixels: movement, settled drift, and residual against that run's first frame. None means too few matched scene features. Runs used different baselines.

```text
mercurytwo Right 1 80 (True, 103, 33) [-12.7, 0.3] [-0.0, -0.0] [-12.6, 0.2]
mercurytwo Left 1 80 (True, 27, 9) [7.1, -0.2] [0.0, 0.0] [-5.1, 0.1]
mercurytwo Right 1 80 (True, 16, 38) [-18.3, 0.8] [0.0, 0.0] [-23.3, 1.2]
mercurytwo Left 1 80 (True, 47, 17) [12.2, -0.1] [0.0, 0.0] [-10.5, 0.4]
mercurytwo Right 1 80 (True, 17, 16) [-14.4, 0.7] [0.0, 0.0] [-25.1, 0.7]
mercurytwo Left 1 80 (True, 25, 15) [13.1, -0.4] [0.0, 0.0] [-11.2, 0.1]
mercurytwo Right 1 180 (True, 58, 6) [-32.2, 1.2] [-0.0, 0.0] [-43.1, 2.0]
mercurytwo Left 1 180 (True, 52, 30) [34.3, 0.2] [-0.0, -0.0] [-5.6, 0.2]
mercurytwo Right 1 180 (True, 35, 67) [-48.7, 0.7] [-0.0, 0.0] [-51.8, 1.5]
mercurytwo Left 1 180 (True, 9, 35) [41.6, 0.5] [-0.0, 0.0] [-11.5, 0.2]
SV07 Right 1 80 (True, 11, 19) [-11.0, -0.0] [-0.0, 0.0] [-11.0, -0.1]
SV07 Left 1 80 (True, 32, 25) [6.1, -0.1] [-0.0, -0.0] [-4.9, -0.4]
SV07 Right 1 80 (True, 16, 9) [-3.1, 0.3] [-0.0, -0.0] [-8.0, -0.1]
SV07 Left 1 80 (True, 13, 18) [3.1, -0.2] [-0.0, -0.0] [-4.9, -0.4]
SV07 Right 1 80 (True, 30, 37) [-3.4, 0.2] [-0.0, -0.0] [-8.3, -0.2]
SV07 Left 1 80 (True, 13, 75) [8.5, 0.4] [-0.0, -0.0] [0.2, -0.1]
SV07 Right 1 180 (True, 20, 18) [-15.7, 0.2] [-0.0, -0.0] [-15.4, 0.2]
SV07 Left 1 180 (True, 14, 20) [15.6, 0.8] [-0.0, -0.0] [0.2, -0.0]
SV07 Right 1 180 (True, 20, 20) [-15.8, 0.2] [-0.0, -0.0] [-15.5, 0.2]
SV07 Left 1 180 (True, 24, 25) [16.2, 0.9] [-0.0, -0.0] [0.5, -0.0]
SV08 Right 1 80 (True, 17, 35) [-11.3, -0.2] [0.0, 0.0] [-11.2, -0.4]
SV08 Left 1 80 (True, 8, 20) [0.0, 0.0] [0.0, 0.0] [-11.3, -0.2]
SV08 Right 1 80 (True, 10, 21) [-0.0, -0.0] [-0.0, -0.0] [-11.1, -0.3]
SV08 Left 1 80 (True, 12, 23) [0.0, 0.0] [0.0, 0.0] [-11.3, -0.5]
SV08 Right 1 80 (True, 8, 17) [-0.0, -0.0] [-0.0, -0.0] [-11.1, -0.3]
SV08 Left 1 80 (True, 32, 11) [-0.0, -0.0] [0.0, 0.0] [-11.3, -0.2]
SV08 Right 1 180 (True, 9, 26) [-11.5, -0.3] [0.0, 0.0] [-22.8, 0.2]
SV08 Left 1 180 (True, 10, 10) [11.6, 0.8] [-0.0, -0.0] [-11.0, -0.3]
SV08 Right 1 180 (True, 21, 71) [-11.7, -0.2] [-0.0, -0.0] [-23.3, 0.3]
SV08 Left 1 180 (True, 16, 31) [11.8, 0.8] [0.0, -0.0] [-11.0, -0.2]
mercurytwo Up 1 120 (True, 13, 51) [1.3, 46.0] [-0.0, 0.0] [0.4, 42.1]
mercurytwo Down 1 120 (True, 67, 9) [0.2, -13.2] [-0.0, -0.1] [0.4, 29.2]
mercurytwo Right 4 180 (True, 14, 21) [-134.9, 12.8] [0.0, -0.1] [-134.0, 44.1]
mercurytwo Left 4 180 (True, 8, 38) None [-0.0, -0.0] [12.4, 28.4]
mercurytwo RightUp 1 120 (True, 15, 53) [0.0, -0.0] [-0.0, -0.0] [12.2, 27.8]
mercurytwo LeftDown 1 120 (True, 7, 44) [0.0, -0.0] [-0.0, -0.0] [12.2, 27.8]
mercurytwo Right 1 40 (True, 11, 51) [-9.4, -0.0] [-0.0, -0.0] [3.3, 27.7]
mercurytwo Left 1 40 (True, 34, 61) [11.9, -0.3] [0.0, -0.0] [14.8, 27.7]
mercurytwo Right 1 40 (True, 202, 74) [-21.0, 0.4] [0.0, -0.0] [-5.0, 27.2]
mercurytwo Left 1 40 (True, 12, 76) [12.6, -0.3] [0.0, -0.0] [7.1, 27.3]
mercurytwo Right 1 40 (False, 0, 2) [0.0, -0.0] [-0.0, -0.0] [7.2, 27.5]
mercurytwo Left 1 40 (True, 30, 68) [32.2, -0.1] [0.0, -0.0] [36.3, 26.9]
mercurytwo Right 1 80 (True, 87, 9) [-10.5, 0.2] [0.0, -0.0] [26.7, 27.0]
mercurytwo Down 1 80 (True, 6, 32) [-0.5, -34.4] [0.0, -0.0] [27.1, -4.2]
mercurytwo Right 1 80 (True, 15, 12) [-32.5, 0.3] [-0.0, -0.0] [-4.7, -4.0]
mercurytwo Left 1 80 (True, 99, 17) [10.8, -0.3] [-0.0, -0.0] [5.7, -4.2]
SV07 Up 1 180 (True, 23, 21) [0.7, 41.3] [-0.0, -0.0] [0.7, 41.4]
SV07 Down 1 180 (True, 25, 39) [-0.4, -42.4] [-0.0, -0.0] [-0.1, -1.2]
SV07 Right 4 180 (True, 11, 13) [-56.5, 8.0] [-0.0, -0.0] [-56.3, 6.4]
SV07 Left 4 180 (True, 20, 11) [58.1, 8.7] [-0.0, 0.0] [2.6, -1.1]
SV07 RightUp 1 120 (True, 30, 50) [-0.0, 0.0] [0.0, 0.0] [2.6, -1.2]
SV07 LeftDown 1 120 (True, 31, 20) [0.0, 0.0] [-0.0, -0.0] [2.6, -1.2]
SV07 Right 1 180 (True, 21, 10) [-19.0, 0.3] [-0.0, -0.0] [-16.2, -0.9]
SV07 Left 1 180 (True, 20, 22) [16.0, 0.9] [-0.0, -0.0] [-0.1, -1.1]
SV08 Up 1 180 (True, 12, 17) [0.2, 27.2] [0.0, -0.0] [-0.1, 27.1]
SV08 Down 1 180 (True, 14, 19) [0.7, -30.5] [-0.0, -0.0] [0.0, -3.2]
SV08 Right 4 180 (True, 15, 26) [-52.4, 5.2] [-0.0, -0.0] [-54.2, 1.4]
SV08 Left 4 180 (True, 11, 22) [45.3, 5.5] [-0.0, -0.0] [-7.0, -3.4]
SV08 RightUp 1 120 (True, 26, 14) [-0.0, 0.0] [0.0, -0.0] [-7.0, -3.4]
SV08 LeftDown 1 120 (True, 39, 12) [0.0, -0.0] [0.0, 0.0] [-7.0, -3.4]
SV08 Right 1 180 (True, 8, 27) [-9.7, -0.2] [-0.0, -0.0] [-17.3, -3.3]
SV08 Left 1 180 (True, 12, 25) [9.9, 0.6] [0.0, -0.0] [-6.7, -3.5]
SV08 Left 1 80 (True, 15, 105) [16.0, 1.2] [0.0, 0.0] [9.2, -2.7]
SV08 Right 1 80 (True, 11, 8) [-0.0, -0.0] [-0.0, 0.0] [9.2, -2.7]
SV08 Right 1 80 (True, 26, 36) [-14.9, -0.2] [-0.0, -0.0] [-5.9, -3.4]
SV08 Left 1 80 (True, 27, 41) [1.0, 0.0] [-0.0, -0.0] [-4.8, -3.4]
```

</details>

## 2026-11-24 | Experimental hybrid nozzle tracking

**Decision.** Use digital cropping as the reference implementation. Hybrid control is a candidate for occasional reframing when the nozzle approaches the edge of the native image. Physical-only tracking had the largest centering error. These short runs establish feasibility on existing hardware and do not qualify a long-running print tracker. [Experimental code and instructions](https://github.com/khisanthax/printernvr/tree/codex/hybrid-nozzle-tracking/experiments/nozzle)

### Setup and scope

- The workstation used an independent native RTSP reader. The Mercury Two relay stream was 640 × 480. Its direct main stream delivered 1280 × 960 at 15 fps. SV07, SV08 and E5P main streams probed at 1920 × 1080. Wansview 3V3 Plus delivered 2304 × 1296. Physical tracking trials used Mercury Two. The other streams were qualified for dimensions only in this experiment.
- Guided calibration uses a rigid feature box and a nozzle-tip click in native coordinates. The tracker searches locally, then reacquires over a configurable zone and multiple scales. A centers a digital crop. B predicts target displacement and jogs one physical axis with a sensor-centered crop. C follows digitally and issues physical jogs only after sustained displacement. A manual hold suppresses new commands. Outputs use a fresh directory with a separate tracked video, timing trace and calibration.
- The V2 adapter used authenticated DVRIP start/Stop and read angles from NetSDK. Each pulse checked recorder/timelapse state. A separate connection can issue watchdog Stop. The ONVIF adapter discovered and acknowledged Stop on E5P and Wansview. Wansview required GetCapabilities(All) to discover the PTZ address. The prior investigation covers physical ONVIF direction testing. No recorder process or production application was deployed or modified. All seven channels reported idle at final verification. No printer motion commands were issued.
- A passive Mercury Two query returned live XYZ and zero velocity while in standby. A short socket subscription returned print-clock samples. The optional queue reader uses only objects/query and motion_report/dump_trapq. The predictor integrates the trapezoid velocity and acceleration between the estimated current and future print times and projects the delta with a configurable local calibration matrix. If either instant lacks segment coverage, it falls back to visual velocity. Future queue lead, camera/MCU clock synchronization and the projection matrix across changing poses still need validation on a moving print. The published numerical comparisons used visual prediction. [Klipper queue API](https://www.klipper3d.org/API_Server.html#motion_reportdump_trapq) and [Klipper lookahead implementation](https://www.klipper3d.org/Code_Overview.html).

### Live Mercury Two measurements

These were separate short runs with different toolhead appearances. Retention below counts frames with the tracker-estimated tip inside the delivered crop. RMS centering is relative to the estimate on detected frames. Digital centering of that estimate is exact whenever the crop can move freely. The matched replay below gives an independently labeled comparison.

| Method | Delivered tracking samples | Estimated tip retained | RMS center error, native px | Tracking jogs / observation | Frame processing p95 | Python CPU / peak RSS |
|---|---:|---:|---:|---|---:|---:|
| A digital | 114 | 100% | 0 | 0 / 8 s | 7.6 ms | 23% / 70 MiB |
| B physical | 30 | 100% | 168 | 2 / 5 s | 247 ms | 23% / 87 MiB |
| C hybrid | 59 | 98.3% | 0 | 5 / 8 s | 414 ms | 70% / 208 MiB |

- Live hybrid command dispatch to first delivered view with a registered background shift above 4 px was **692 ms**, one identifiable event. This includes software detection overhead. Camera exposure-to-screen delay and nozzle-motion-to-screen delay were not measured. Processing p95 includes native tracking and encoding, and sometimes background registration. CPU is process time divided by wall time, with 100% equal to one core. The figures exclude the external decoder and remote worker. A later B run measured 4.80 CPU seconds across the local process tree during 9.96 seconds of tracking and 360 MiB peak local-tree RSS.
- B was inconsistent. A second eight-second run retained the estimate on only 1/48 frames and issued zero jogs. Another ten-second run retained it on 32/32 samples, issued three jogs and had 197 px RMS centering error. C's 5/8 s is a short-window rate of 37.5 jogs/min. These samples do not establish a sustained duty cycle or latency distribution.
- B's first restoration check reported 48 px vertical residual before its last correction. Later trials added a settled post-correction measurement. C finished about 1.7 px horizontally and 3.7 px vertically from its starting background. The later B run finished within 1 px. Restoration uses scene features outside the selected toolhead region. Manual hold takes priority.
- A narrow strand visible on the purge fixture measured a median apparent width of **2 native pixels** at half contrast over 12 scanlines, with median peak-to-background contrast 51/255. The 576 × 432 derived views crop native pixels without upscaling. Strand diameter in millimeters and deposited bead quality were not calibrated.

### Matched comparisons

The first replay used a 12-second stream-copy excerpt from the actual Mercury Two main feed. Eleven once-per-second nozzle locations were manually labeled. One motion-blurred sample was excluded. All three methods included the labeled location on **11/11** scored samples. RMS centering error was **28 px for A, 167 px for B and 28 px for C**. A issued zero jogs. B and C each requested one simulated jog. Simulated motion shifted the captured scene within its original field of view.

The second replay used a frozen native Mercury Two frame with known translations, small rapid motion, a sustained offset and a one-second occlusion during a ten-second run. This yields exact reference coordinates. The physical response model used a 36 px step and 200 ms lag. It did not include backlash or measured network jitter. The live 692 ms observation shows why these results cannot establish real printer tracking accuracy.

| Metric | A digital | B physical, simulated | C hybrid, simulated |
|---|---:|---:|---:|
| Visible / all frames, including occlusion | 90% | 90% | 90% |
| RMS centering while visible | 0 px | 160 px | 0 px |
| Jogs per 10 seconds | 0 | 7 | 4 |
| Recovery after reveal | First frame | First frame | First frame |
| Median encoded/source target-patch contrast metric | 0.975 | 0.975 | 0.975 |
| Python CPU / peak RSS | 161% / 154 MiB | 162% / 152 MiB | 169% / 154 MiB |
| Frame processing p95 during concurrent workstation activity | 131 ms | 153 ms | 133 ms |

Recovery was within one 15 fps sampling interval (67 ms) in this controlled case. The contrast metric is the ratio of Laplacian variance in a 24 × 24 target patch. Reported jog counts exclude framing restoration. The independent source excerpt and the three sets of derived videos and traces were retained locally. Camera images, connection addresses and credentials were excluded from Git.

### Failures and remaining limits

- Native video exposed depth-dependent scale change and motion blur. Single-scale calibration lost the toolhead in a different pose. Multi-scale reacquisition and a three-second initial lock window improved recovery. Some physical sessions still correctly declined to start when the initial target could not be identified. Occlusion of the actual tip by the shroud remains possible even when a toolhead feature matches.
- Initial OpenCV RTSP capture and an unsupported FFmpeg timeout option failed. The live reader now uses FFmpeg, its supported RTSP timeout, native dimensions and a latest-frame queue. Headless OpenCV cleanup initially aborted replay output. Calibration now uses Tk and headless runs avoid GUI cleanup.
- An early worker-protocol failure during a DVRIP trial led to isolating diagnostic output from control replies and adding independent Stop recovery. Existing continuous recordings and printer movement were outside the experiment. A short archived SV08 clip did not provide a usable Mercury Two comparison.
- A first benchmark incorrectly assumed a moving source clip had stationary ground truth under synthetic translation. Those scores were discarded. The controlled benchmark now freezes the reference frame, and the separate real-motion replay uses manual labels. The prototype could still lose frames under load and falsely lock at a new depth. A print-length validation needs independent tip labels, synchronized timestamps, per-axis calibration and a measured physical-response model before unattended use.

## 2026-11-24 | Native nozzle tracking and custom firmware feasibility

**Decision.** Keep the stock firmware on Mercury Two, SV07 and SV08. Stock Smart Tracking merits a controlled non-human-target test on a spare ASH21-B-V2. A custom on-camera detector on this revision has no verified deployment or recovery path. A supported Thingino camera is the better bench platform for developing a native loop. This investigation used documentation and existing measurements. It issued no requests to cameras and changed no production systems.

### What the stock tracker can follow

Amcrest’s ASH21 quick-start guide describes Smart Tracking following moving objects and illustrates it with a cat. The guide describes Human Detection separately as a filter for alerts. Amcrest’s black V2 product listing emphasizes tracking people. Together these support a **plausible general-motion mode**, but give no tested minimum target size, speed, or mapping between the alert filter and the tracker’s candidate selection on our build. Turning off the human filter alone does not establish that a nozzle or toolhead will be followed. A moving bed, hands, gantry, reflections and a larger moving part all provide competing targets. [Amcrest quick-start guide](https://m.media-amazon.com/images/I/81PRzgIkNkL.pdf) and [exact V2 product listing](https://dealers.amcrest.com/products/amcrest-smarthome-ai-human-detection-wifi-camera-pan-tilt-ash21-b).

Autonomous motion following and local SD event recording are consistent with an onboard control loop. Local recording alone cannot establish where inference happens, whether an app session is required, or whether the camera depends on WAN access after setup. No offline tracking test or native response-time specification was found for the installed build. The prior **692 ms** observation measured external command dispatch through visible movement in a delivered frame. It included control, mechanics and the video return path. It was one event and supplies neither native tracker latency nor the milliseconds saved by moving inference onboard. [Amcrest V2 local recording](https://support.amcrest.com/hc/en-us/articles/4411395887117-How-to-Setup-Continuous-Recording-ASH21-V2) and [prior measured trial](https://github.com/khisanthax/printernvr/blob/228d3ce/docs/logbook.md#2026-11-24--experimental-hybrid-nozzle-tracking).

### Hardware and firmware evidence

All three fleet devices previously identified themselves as ASH21-B-V2, hardware ID 1.00, firmware 2.680.00AC008.0.R dated April 6, 2022. Amcrest lists a 7.4 MB update for this revision and lists V3 separately. The exact V2 datasheet specifies a 2 MP 1/2.8-inch CMOS sensor, a fixed 3.6 mm lens, 355° pan and −5° to 80° tilt. These are travel limits. The filing indexed under ZZ2-ASH21 includes a V3 manual and V3 test evidence, so it cannot identify the processor in our V2 cameras. [V2 datasheet](https://drive.google.com/file/d/1bjvK3PDDjeS8UTAPishvw9DIwE7J0mFe/view), [firmware catalog](https://www.amcrest.com/pages/firmware-ash), [FCC exhibits](https://fccid.io/ZZ2-ASH21).

| Item | What the available evidence establishes |
|---|---|
| Processor / architecture | SoC part number, CPU family and instruction set unresolved. DVRIP compatibility identifies an external protocol. It does not identify the silicon. |
| RAM / onboard flash | Installed capacities and free working RAM unresolved. The download size measures the update payload. The microSD capacity describes removable recording storage. |
| AI acceleration | Person detection is a verified product feature. A dedicated NPU, accessible inference runtime, supported model formats and spare inference capacity are unverified. |
| Operating system | Exact OS, kernel and application ABI unresolved for hardware ID 1.00. No vendor-supported on-device app or model-loading SDK was located. |
| Motor controller | Both axes physically move and NetSDK exposes angles. Driver IC, electrical interface, motor step size, gearing, feedback sensor and direct motor API are unresolved. |
| Bootloader / firmware format | Vendor publishes a model-specific update. Bootloader identity, package internals, signing policy, partition layout, boot selection and downgrade acceptance remain unverified. |

### Firmware choices and native algorithms

OpenIPC documents support by SoC and board-dependent peripherals. Thingino publishes exact Ingenic camera targets. Neither provided a verified ASH21-B-V2 target in the reviewed lists. The Dafang project also targets specific hardware. No supported stock extension was found for installing a toolhead model, accessing pre-encode frames or replacing the motor algorithm. The Amcrest SDK used by Printer NVR runs on a client and provides remote control. Every potential port still needs a matching sensor/ISP path, video encoder, Wi-Fi, motor driver and retained calibration. The same uncertainty applies to transferring a conclusion to the V3 E5P or the Wansview identified only as NAV. [OpenIPC hardware](https://openipc.org/supported-hardware/full-list), [OpenIPC board guidance](https://github.com/OpenIPC/wiki/blob/master/en/guide-supported-devices.md), [Thingino hardware list](https://github.com/themactep/thingino-firmware/blob/master/docs/hardware/supported-hardware.md), [Dafang supported devices](https://github.com/EliasKotlyar/Xiaomi-Dafang-Hacks).

| Design | Practical feasibility |
|---|---|
| Stock Smart Tracking | Inspect target selection on a spare. There is no documented nozzle class, user-supplied detector or guarantee that disabling human alerts removes a tracking gate. |
| Toolhead recognition | A small detector could run on a platform with frame access, measured CPU/RAM headroom and a model runtime. Changing nozzle appearance, blur, depth and shroud occlusion require labeled sequences. Stock V2 model replacement is unverified. |
| Visual marker | Best first native experiment. Use a distinctive marker on a spare target, detect its centroid in low-resolution luma frames and map a calibrated offset to the nozzle. Test scale, blur, lighting and tag loss. The prior footage resolved one thin strand at about two native pixels, making the larger toolhead a better feature. |
| Prediction, zones and centering | Use frame timestamps, position/velocity estimates, a configurable image mask and a deadband. Suspend actuation after confidence loss and reacquire within the zone. External Klipper lookahead adds a telemetry link and clock alignment even with local vision. A camera’s alert mask needs separate verification as a tracker mask. |
| Direct actuation | On a supported board, use its motor driver with travel limits, bounded single-axis jogs, Stop and a watchdog. Chip-level control on the ASH21-B-V2 is unverified. Even fast inference needs to respect backlash, settling and trajectory reversals. |

A detector consuming local ISP frames could remove RTSP encode, transport, buffering, workstation decode and the return PTZ network command **from the control loop**. Remote viewing and recording would retain their own encode and network latency. Exposure, sensor readout, frame scheduling, inference, motor startup and settling remain. At the tested 15 fps external stream rate, successive frames were about 67 ms apart. The native detector’s cadence is unknown.

### Mechanics and a non-destructive test design

The earlier 180 ms pan holds shifted the scene by about 32–49 px at speed 1 versus 135 px at speed 4 on Mercury Two, 16–19 versus 57–58 px on SV07, and 10–12 versus 45–52 px on SV08. These are image displacements at 640 × 360 with network-controlled start/Stop timing. They cannot establish mechanical degrees/s by dividing by the requested hold. Diagonal requests produced no measured displacement. A faster detector could choose a correction earlier, while single-axis motion and settling would still constrain a fast reversing target. [Per-device motion measurements](https://github.com/khisanthax/printernvr/blob/356871b/docs/logbook.md#2026-11-24--amcrest-ash21-b-v2-local-ptz-tests).

1. **Offline now:** use the saved native footage and manual labels to compare marker, template and toolhead detectors. Report error, loss/reacquisition and CPU/memory. This can establish algorithm quality; it cannot certify V2 execution speed.
2. **Future spare-only stock test:** move a toolhead-sized target on an independent fixture with a stationary background. Repeat the same trajectory with Smart Tracking enabled, first with human filtering enabled and then disabled. Include a person as a positive control, and a moving bed or distractor as a negative control. Repeat with the app closed, then with WAN unavailable on the isolated bench LAN. Record lock rate and false follows. No production printer movement is needed.
3. **Separate timing:** film target and housing together with a high-frame-rate independent camera and an angular reference. Measure target onset to first housing motion, angle versus time once moving, reversal delay and time to settle. Compare stock tracking against externally commanded jogs at matched angle and direction. Measure video-delivery delay separately. Report repeated median and p95 by axis, speed and lighting.
4. **Backup and recovery:** preserve the revision label, installed version, configuration inventory, calibration references and original recordings. An official update file is useful for version matching. It is not evidence of a restorable per-unit image with calibration, identity and settings. No documented V2 full backup/restore, alternate boot, or rollback to the installed build was verified. Factory reset concerns configuration and does not demonstrate a firmware downgrade. Require a model-specific vendor recovery procedure and demonstrated recovery on a spare before considering firmware replacement. No firmware image was modified or installed.

### Low-cost development hardware

**First choice: an exact Wyze Cam Pan v2 with a matching Thingino board target.** Thingino lists a T31X/GC2053/ATBM6031 build; check the actual board variant before buying. Wyze’s refurbished listing showed US $15.98, sold out at review, and specifies up to 110°/s rotation. That rating is not a nozzle-tracking latency or reversal measurement. **Second choice: a used Wyze Cam Pan v1** matching Thingino’s T20X/JXF22/RTL8189ETV profile if available below the cost of the v2. Both have model-specific community installer entries. Verify pan/tilt, pre-encode frame access, sustained frame rate and recovery on the chosen unit before adopting it. These are development spares; there is no measured basis to replace the working fleet for digital tracking. [Thingino board profiles](https://github.com/themactep/thingino-firmware/blob/master/docs/hardware/supported-hardware.md), [model-specific installer inventory](https://github.com/wltechblog/thingino-installers), [Wyze v2 price, availability and motor specification](https://www.wyze.com/products/wyze-cam-pan-v2-refurbished).
