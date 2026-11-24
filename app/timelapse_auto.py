import json
from pathlib import Path
from threading import Event, Lock, Thread

from app.models import TimelapseAutoSettings
from app.operations import camera_lock


class TimelapseAutomation:
    def __init__(self, root, manager, moonraker, cameras):
        self.path = Path(root) / ".timelapse-auto.json"
        self.manager = manager
        self.moonraker = moonraker
        self.cameras = cameras
        self.lock = Lock()
        self.stop = Event()
        self.messages = {}
        self.policies = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        self.thread = Thread(target=self._run, daemon=True, name="timelapse-auto")

    def _save(self):
        pending = self.path.with_suffix(".json.part")
        pending.write_text(json.dumps(self.policies), encoding="utf-8")
        pending.replace(self.path)

    def status(self, printer_id):
        with self.lock:
            result = dict(self.policies.get(printer_id, {"enabled": False}))
            return {**result, "message": self.messages.get(printer_id, "Waiting for print status")}

    def configure(self, printer_id, settings: TimelapseAutoSettings):
        with self.lock:
            existing = self.policies.get(printer_id, {})
            self.policies[printer_id] = {**existing, **settings.model_dump()}
            self._save()
        return self.status(printer_id)

    def _run(self):
        while not self.stop.is_set():
            self.poll()
            self.stop.wait(5)

    def poll(self):
        with self.lock:
            policies = [(key, dict(policy)) for key, policy in self.policies.items() if policy.get("enabled")]
        cameras = {camera.id: camera for camera in self.cameras()}
        for printer_id, policy in policies:
            if self.stop.is_set():
                return
            camera = cameras.get(policy.get("camera_id"))
            if not camera or not camera.enabled or camera.printer_id != printer_id or not camera.moonraker_url:
                self.messages[printer_id] = "Select an enabled camera with a Moonraker URL"
                continue
            if self.moonraker.fetch_status(camera.moonraker_url).monitor_state != "printing":
                self.messages[printer_id] = "Waiting for Moonraker to report an active print"
                continue
            job_id = self.moonraker.active_job_id(camera.moonraker_url)
            if not job_id:
                self.messages[printer_id] = "Waiting for a stable Moonraker history job ID"
                continue
            with camera_lock, self.lock:
                current = self.policies.get(printer_id)
                if self.stop.is_set() or current != policy or current.get("last_job_id") == job_id:
                    continue
                if camera not in self.cameras():
                    continue
                if self.manager.is_printer_busy(printer_id):
                    try:
                        current["last_job_id"] = job_id
                        self._save()
                    except OSError:
                        self.messages[printer_id] = "Unable to persist the print job claim"
                    continue
                # Persist the claim first so a process restart cannot start this job twice.
                current["last_job_id"] = job_id
                try:
                    self._save()
                    self.manager.start_session(
                        printer_id, camera.printer_name, camera, current["interval_seconds"],
                        camera.moonraker_url, capture_mode=current["capture_mode"], print_job_id=job_id,
                    )
                    self.messages[printer_id] = "Started automatically for the active print"
                except (OSError, ValueError) as exc:
                    self.messages[printer_id] = str(exc)

    def shutdown(self):
        self.stop.set()
        self.thread.join(timeout=4)
