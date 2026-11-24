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
