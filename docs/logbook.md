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

## 2026-11-23 | Reconcile draft PR #1 with main

- GitHub comparison showed 12 branch commits ahead and one behind the common ancestor `a68bbb9`. The sole main-side file was `docs/logbook.md`, added independently on both branches. GitHub reported PR #1 unmergeable.
- Ran `python -B -m unittest discover -s tests -q` in a disposable Windows checkout of the hardening code. All 11 baseline tests passed with existing UTC deprecation warnings. The original checkout was read-only to this session.
- Merged main ancestry into the hardening branch using the main logbook, which already contained all branch entries, plus this result. The merge changes only documentation and leaves PR #1 in draft. This branch tracks new procedure entries for the current assignment.

## 2026-11-23 | Phase 13 timeline and video viewer

- Added Moonraker state/layer observation and a validated event ingestion API, with separate receipt, source and Klipper clocks. Added a completed-video viewer, automatic estimated frame-zero anchors, manual clock correction, event-to-video seeking and up-to-120-second extraction.
- Ran `python -B -m unittest discover -s tests -q` in the disposable Windows checkout. All 15 tests passed, including four new tests for clock validation/alignment, persisted events, polling deduplication and real FFmpeg segment extraction. The 1.5-second fixture segment was within one video frame of the requested range and the original bytes were unchanged.
- `node --check static/timeline.js` passed. Building the app OpenAPI schema produced 50 paths. GitHub confirmed PR #1 is now mergeable and still draft, based on main commit `099b304`.
- Camera buffering and poll intervals limit synchronization precision. Live printer, real-camera and interactive browser checks remain unverified at this milestone.

## 2026-11-23: Timelapse shutdown hardening

- Made capture, render, and probe subprocesses cancellable on app shutdown. New starts and retries are rejected after shutdown begins.
- Added a regression using a real child process to verify that closing the manager stops an in-flight render, discards staged output, preserves completed frames, and leaves the session eligible for retry.
- `python -B -m unittest discover -s tests -v`: 16 tests passed, including verified FFmpeg output and the new shutdown test. No live printers or production systems were used.

## 2026-11-23: Monitoring without a configured camera

- Kept printer-first entries with zero cameras visible in `/live`, `/printers`, the cards API, and `/timeline`, with no capture target.
- Verified camera-free Moonraker observations and that disabled printer endpoints are not polled. All 17 automated tests passed; `node --check` passed for timeline, live, printers, clips, and cameras scripts.

## 2026-11-23: Saved Phase 13 alignment

- Added Save alignment and Reset alignment for completed MP4 clips. Calibration is validated and kept separately from the recorder's original estimate.
- Verified calibration round-trip and reset with unchanged recorder estimate. All 18 local automated tests and timeline JavaScript syntax checks passed.

## 2026-11-23: Compatibility camera config mutations

- Patched legacy camera CRUD to preserve nested printer definitions, printer-level settings, default selection and existing output folder mappings.
- The new test creates then updates and removes the last camera of a printer and verifies the empty definition and Moonraker URL are retained. All 19 automated tests passed.

## 2026-11-23: Archived clip resolution

- Reproduced and fixed a clip list/resolver mismatch when a camera ID matched an unclaimed old output folder. Both files now resolve independently, even with identical filenames. Internal export staging paths cannot be indexed or resolved as clips.
- Added `/timeline` to disposable deployment route smoke coverage. All 20 local automated tests and Node syntax checks for timeline and clips passed.

## 2026-11-23: Timeline storage and recording failure isolation

- Bounded per-printer JSONL compaction and preserved the most recent entries, including non-ASCII messages.
- Confirmed a timing sidecar write/validation error cannot change a verified recording into a failed recording.
- Added an HTTP event submission/read round-trip to disposable deployment CI; the final CI run is separate from local verification. All 22 local automated tests passed, as did syntax checks for timeline, live, printers, clips, and cameras JavaScript.

## 2026-11-23: Moonraker monitoring freshness

- Kept the last known readings and success timestamp through failed/incomplete responses, while preserving the current offline/unavailable badge and withholding stale event clocks.
- Tested a good response followed by an outage. Python compilation, all 23 local automated tests, and five JavaScript syntax checks passed. The preceding archive milestone's disposable Docker run and Windows/dependency jobs passed; this commit starts a new CI run.

## 2026-11-23: Disposable timeline verification

- GitHub Actions run 45198366588 passed Ubuntu, Windows, dependencies, and disposable Docker. The next run, 45198676896, passed both platforms and dependency audit but the new HTTP smoke fixture failed: it assumed the installer seeded the example printer, while fresh installs intentionally have an empty config.
- Corrected the disposable test to provision its own inert printer and camera through the revision-checked API. The workflow then submits/reads a dual-timestamp event, generates a synthetic MP4 inside Docker, extracts a one-second clip over HTTP, and checks the original checksum. No live devices are contacted.
- Verified workflow YAML locally and reconciled roadmap/architecture. Local Python compilation, 23 tests, JS syntax, and source diff whitespace checks passed. GitHub verification of the corrected workflow is a separate run.

## 2026-11-23: Phase 13 verification result

- [GitHub Actions run 45199452133](https://github.com/khisanthax/printernvr/actions/runs/45199452133) on `edb0a43` passed all four jobs: Ubuntu tests, Windows tests, dependency audit and disposable Docker deployment/update. The latter successfully created a test printer/camera, round-tripped an event with both timestamps, and extracted and probed a one-second MP4 while checking the original file was unchanged.
- Local Jinja rendering with the CI printer fixture and Git whitespace checks for 19 source diffs passed. PR #1 was verified draft and mergeable on the implementation head. Neither `main` nor production was changed; real-device timing and visual browser interaction remain unverified.

## 2026-11-23: Phase 13 acceptance follow-through

- Read the hardening logbook/roadmap and verified draft PR #1 was mergeable before editing. Added explicit Klipper log correlation/import, event filters, aligned camera switching, dual event timestamp overlays and optional burned-in MP4 exports. Imports retain predefined markers, not raw logs; logs without a startup anchor are not guessed. Exports preserve the original file and are serialized without holding the camera transaction during encoding.
- A first export race test caught `WinError 5` for hard links in the Windows workspace. Added a disk-checked snapshot-copy fallback and reran the rename/export and competing-export regressions. Added parallel log import and annotation, simultaneous recording start, and FFmpeg pixel checks proving the caption was rendered.
- The default terminal sandbox denied loopback requests (`WinError 10013`). The approved isolated rerun passed real Chromium on desktop and at a 375px touch viewport, exercising actual playback, event seek, clock overlay toggle, log import/filter, angle switching, UTC-named download, and unchanged original bytes. All 27 local regression tests, Python compilation, five JavaScript syntax checks, workflow YAML parsing, and whitespace checks for 12 source files passed.
- Added a repeatable Chromium CI job and extended isolated Docker smoke to check timestamped extraction. Real printer/physical-camera time alignment, iOS Safari/native fullscreen, and production playback remain unverified. No merge or production deployment.

## 2026-11-23: Viewer/export consistency and hosted Windows race

- The first expanded GitHub run passed dependency audit and disposable Docker (including timestamped extraction), but Windows exposed an output directory resolution race during the new competing-start regression. Moved path resolution under the camera claim lock and tightened the output directory check. Disabled matrix fail-fast so both platforms report independently.
- Timestamped exports now use even unsaved viewer calibration without changing saved metadata. Camera clip quotas are independent; an empty/non-overlapping camera shows a clear message instead of loading another angle's footage.
- All 28 local tests passed. Chrome desktop and 375px touch viewport passed again, including the changed UTC filename with an unsaved correction and the empty-camera fallback. Python compilation and JavaScript syntax checks passed. A new complete GitHub Actions run verifies this revision.

## 2026-11-23: Phase 13 expanded acceptance results

- [GitHub Actions run 45210307754](https://github.com/khisanthax/printernvr/actions/runs/45210307754) on `2f30d81` passed all five jobs: Ubuntu and Windows tests, dependency audit, Chromium/browser acceptance, and disposable Docker deployment/update. Ubuntu Chromium explicitly passed desktop and 375px mobile viewport tests. Docker checked both clean and timestamped segment downloads and original-media preservation.
- Hosted Windows passed the original four-way capture race after path validation was moved under the claim lock. The latest local checks also passed 28 tests, playback in both browser layouts and follow-up source whitespace checks. No main or production changes were made. Physical-device playback and real clock accuracy were not part of these isolated checks.

## 2026-11-24: Prepare a controlled real-printer pilot

- Reconciled the roadmap and architecture against this branch. Added an isolated pilot checklist for RTSP recording, Moonraker events, clock error/drift, physical-browser playback, and measured disk usage. No real printer or production access was used.
- The previous updater backup omitted timeline logs and had no recovery drill. Added verified metadata and full-state backup modes, with link rejection, private output, a revision record, and SHA-256 verification. Extended disposable Docker CI to extract and checksum a full backup, reject corruption/links, then test forward upgrade and rollback to the original image ID while preserving mounted files.
- Added a simulated reported-layer worker test and Chromium review acceptance for rejection, printer/date filters, favorites download, keeper export, and dashboard rename. All 29 local unit tests, Python compilation, and five JavaScript syntax checks passed. Loopback Chrome passed the clip review and existing timeline desktop/375px mobile checks. Local Docker was unavailable and Git Bash was denied by the Windows sandbox; the recovery drill runs in hosted Linux CI.
