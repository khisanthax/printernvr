# Controlled real-printer pilot

**Status:** Runbook only. No physical-printer pilot or production deployment has been run. Attach a dated pass/fail record to the logbook after an authorized pilot. Treat the thresholds below as proposed acceptance gates, not measured performance.

## Scope and go/no-go

- Assign an operator and a printer owner, name the one printer and camera, agree on a short observation window and disk budget, and record the exact tested commit and image ID. Start with a single primary camera. Add an alternate only after the single-camera checks pass.
- Use a disposable Linux host or VM with a **separate Docker engine, checkout, and storage**. A different Compose project name alone is insufficient because Compose sets a fixed container name. Do not change the production checkout, mount its recordings, expose new ports on a printer, or write to Klipper configuration. Start from fresh config; do not import production auto-start or retention policies.
- Keep the web port on loopback (use a trusted tunnel if needed). Point the pilot at only the approved existing RTSP/go2rtc and Moonraker endpoints. Begin with external go2rtc, no automatic timelapse start, and retention `alert_only` or disabled. Do not cancel a print just to create an event. Do not turn off camera or printer services to simulate an outage.
- Before connecting real devices: check `/ready`, confirm free space and a separate backup destination, and rehearse backup verification and image rollback with synthetic footage. If any gate fails, stop and investigate before proceeding.

## Backup, restore rehearsal and rollback

Run commands from the isolated checkout only. The helper assumes the repository's default bind mounts. With custom mounts, take snapshots of the actual volumes instead. Backups contain credentials and potentially private video; keep them access-controlled and copy to suitably protected storage outside the recorder volume. Do not attach archives or full diagnostic logs to GitHub.

1. Finish captures, optimizer jobs and exports in the app. Record the current image ID and Git revision. If testing a pilot upgrade, tag the known-good running image **before** stopping it. Do not prune that image.

   ```sh
   previous_image=$(docker inspect -f '{{.Image}}' "$(docker compose ps -q printernvr)")
   git rev-parse HEAD
   docker image tag "$previous_image" printernvr-pilot-rollback:known-good
   docker compose stop printernvr
   ```

2. With all writers stopped, verify capacity for a full copy, then create and verify the full backup. If using bundled go2rtc, stop any companion that writes to the backed-up config and use the same Compose files/profile for its lifecycle. The updater takes a **metadata-only** archive, which is not a substitute for this full backup.

   ```sh
   backup=$(bash scripts/backup.sh --full)
   (cd "$backup" && sha256sum -c SHA256SUMS && tar -tf state.tar)
   ```

   Archive coverage: `.env` if present, `config/`, and all of `recordings/`, including clips, timelapse frames and manifests, clip review and timing metadata, auto-start settings, and timeline events. Logs and any externally chosen export destinations are not included. Abort if the helper rejects links or if tar or checksum verification fails. Keep the full backup and its manifest together.

3. Rehearse recovery **into a new directory**, not an existing deployment. Use only an archive you created and trust. Compare content hashes against the stopped pilot, verify several representative MP4s with FFprobe, and confirm required hidden metadata and timelapse frames are present. Keep pilot files created after the backup separate; do not overwrite them with the snapshot.

   ```sh
   restore=$(mktemp -d)
   (cd "$backup" && sha256sum -c SHA256SUMS) &&
     tar --extract --no-same-owner --file "$backup/state.tar" --directory "$restore"
   diff -r config "$restore/config"
   diff -r recordings "$restore/recordings"
   if [ -f .env ]; then cmp -s .env "$restore/.env" || echo 'Environment file differs'; fi
   ```

4. Default rollback for this branch is **stop or discard the isolated pilot**, not a production rollback. To rehearse an in-place *pilot* image rollback, stop capture, keep a new snapshot of the current data, and use a temporary Compose override with the saved image tag. Do not reset Git, build or pull an image, prune Docker, delete volumes, or extract a backup over the live bind mounts.

   ```sh
   rollback=$(mktemp)
   printf 'services:\n  printernvr:\n    image: printernvr-pilot-rollback:known-good\n' > "$rollback"
   docker compose -f docker-compose.yml -f "$rollback" up -d \
     --no-deps --no-build --pull never --force-recreate --wait printernvr
   test "$(docker inspect -f '{{.Image}}' "$(docker compose ps -q printernvr)")" = "$previous_image"
   curl --fail --silent --show-error http://127.0.0.1:8787/ready
   ```

   Substitute the configured loopback port if changed. For a bundled companion, include its Compose file and profile and leave its state unchanged. If the old image cannot read the retained state, stop it; restore a verified snapshot into a **different** isolated checkout and storage instead. A clean `/ready` is necessary but not sufficient: reopen existing clips and check metadata and content hashes again.

## Physical acceptance checklist

| Check | Procedure and proposed pass condition | Evidence |
| --- | --- | --- |
| Camera recording | Probe the approved recording URL, confirm the live preview identifies the same physical view, then capture manual Start/Stop, 30 seconds, and one representative longer manual sample (2-5 minutes). Verify all completed files play and probe, land in the selected camera's folder, contain only video, and no temporary file appears as a finished clip. Check recording on a second view only after the first passes. | Clip ID, view, elapsed and media duration, resolution/FPS, codec, bytes, relevant redacted errors. |
| Moonraker events | Observe one normal supervised print through start, sample layers where reported, and normal completion. Verify changes appear in the correct printer timeline; do not treat a short unobserved transition as guaranteed to be captured. If the owner supplies an authorized log excerpt containing a startup clock line, import it twice and verify correlation and deduplication without publishing raw logs. | UTC witness times, event type/origin, source time where available, recorder receipt time, observed lag. |
| Timestamp synchronization | Check recorder and printer wall-clock status read-only where available. Use two safe visible cues, independently note their UTC times, and submit them as timeline markers. Measure the uncorrected seek error at both cues for each camera, then save a per-clip correction and repeat. Aim for at most 2 s absolute error after correction and at most 2 s drift between cues; report the observed error separately from Moonraker polling latency. Verify an overlapping camera switch and UTC-named burned export match the same instant. | Clock status, cue times and playhead offsets, raw and corrected errors, drift, calibration, export filename. |
| Browser and playback | On the intended desktop browser and one physical mobile device, play, pause, seek, preview and download a clean and a burned segment. Check the two event clock labels when available, native fullscreen behavior, tab resume and manual stream refresh. Check that camera or printer status changes never blank other cards during normal polling. | OS/browser/device, playback and controls pass/fail, codec/unsupported behavior. Browser emulation is not a substitute for a real phone. |
| Storage | Snapshot free bytes and inventory before and after. Collect at least three completed manual samples per camera when practical, including the longer sample, and separate source frame bytes, timelapse MP4, ordinary clips and temporary files. For each clip compute `MB/min = bytes * 60 / duration_seconds / 1000000`; project from observed **recording** hours, not total printer uptime. If comparing an optimized copy, compare size and visible detail at source resolution; never replace the original during the pilot. | Free bytes, per-clip measurements, median/range, projected GB/day, original and optimized hashes and visible quality. |

Read-only inventory and media measurements on the pilot recorder:

```sh
curl --fail --silent --show-error http://127.0.0.1:8787/api/storage/inventory
df -k recordings
ffprobe -v error -show_entries format=duration,size,bit_rate:stream=codec_type,codec_name,width,height,avg_frame_rate \
  -of json "/path/to/pilot-recording.mp4"
```

Include the configured capture reserve and free-space warning in the disk budget, plus room for a full backup and temporary exports. For a first pilot, stop well before the configured warning. Pause or stop the pilot on unreadable media, an incorrect recording target, unexpected printer/camera load, missing backup validation, unexpected writes to production paths, or a disk/retention warning. Stop recording through the UI first and let FFmpeg finalize. Stop only the isolated app if it cannot recover; leave the printer and external services alone.

At closeout, record the commit and image IDs, exact scope, checks and measured outcomes (including skipped checks), custody of the backup, remaining risks, and the operator's explicit go/no-go decision. Passing the pilot does not authorize general deployment.
