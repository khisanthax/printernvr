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
