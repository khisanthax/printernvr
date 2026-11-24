"""Optional camera transports; nothing in this module controls a printer."""
import base64
import json
import subprocess
import sys
import ctypes
import os
import time
from pathlib import Path

import requests


class NetPose:
    def __init__(self, host, user, password, library):
        path = Path(library).resolve()
        self.directory = os.add_dll_directory(str(path.parent))
        dll = ctypes.WinDLL(str(path))
        self.dll = dll
        i, p, l, s = ctypes.c_int, ctypes.c_void_p, ctypes.c_longlong, ctypes.c_char_p
        for name, ret, args in [
            ("Init", i, [p, p]), ("LoginEx2", l, [s, ctypes.c_ushort, s, s, i, p, p, p]),
            ("QueryDevState", i, [l, i, p, i, p, i]), ("Logout", i, [l]), ("Cleanup", None, [])
        ]:
            fn = getattr(dll, "CLIENT_" + name)
            fn.restype, fn.argtypes = ret, args
        if not dll.CLIENT_Init(None, None):
            raise RuntimeError("NetSDK initialization failed")
        buf = ctypes.create_string_buffer(4096)
        self.handle = dll.CLIENT_LoginEx2(host.encode(), 37777, user.encode(), password.encode(),
                                          0, None, buf, ctypes.byref(i()))
        if not self.handle:
            self.close()
            raise RuntimeError("NetSDK login failed")

    def read(self):
        buf = ctypes.create_string_buffer(2048)
        size = ctypes.c_int()
        if self.dll.CLIENT_QueryDevState(self.handle, 0x36, buf, len(buf), ctypes.byref(size), 500) and size.value >= 12:
            _, x, y = (ctypes.c_int * 3).from_buffer(buf)
            return x / 10, y / 10
        return None

    def close(self):
        if self.handle:
            self.dll.CLIENT_Logout(self.handle)
        self.dll.CLIENT_Cleanup()
        self.directory.close()


class Camera:
    def __init__(self, config):
        self.config = config
        self.feedback = None
        host, user, pw = [os.environ[config[key]] for key in ("host_env", "user_env", "password_env")]
        self.v2 = config["protocol"] == "dvrip"
        if self.v2:
            program = base64.b64encode(Path(__file__).with_name("worker.py").read_bytes()).decode()
            argv = config.get("worker_prefix", [sys.executable])
            bootstrap = f"exec(__import__('base64').b64decode('{program}'))"
            # Remote shells must receive a quoted Python expression as one argument.
            if config.get("worker_shell"):
                import shlex
                bootstrap = shlex.quote(bootstrap)
            self.worker = subprocess.Popen([*argv,"-u","-c",bootstrap],stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
            self.worker.stdin.write(json.dumps(dict(host=host,username=user,password=pw))+"\n")
            self.worker.stdin.flush()
            if self.worker.stdout.readline().strip() != "ready":
                raise RuntimeError("DVRIP worker unavailable")
            if config.get("netsdk_env"):
                self.feedback = NetPose(host, user, pw, os.environ[config["netsdk_env"]])
        elif config["protocol"] == "onvif":
            from onvif_ptz import OnvifPTZ
            self.driver=OnvifPTZ(host,config.get("port",80),user,pw,config["profile"])
        else:
            raise ValueError("Unknown camera protocol")

    def pose(self):
        return self.feedback.read() if self.feedback else None

    def stop(self):
        if self.v2:
            return  # Each worker request includes Stop before returning.
        else:
            self.driver.stop()

    def jog(self, axis, sign, hold=None):
        hold_file = self.config.get("hold_file")
        if hold_file and Path(hold_file).exists():
            return
        base = os.environ[self.config["nvr_env"]].rstrip("/")
        def status(path):
            response = requests.get(base + path, timeout=1)
            response.raise_for_status()
            return response.json()
        state = status("/api/record/status")["cameras"]
        if not any(c["camera_id"] == self.config["id"] and c["status"] == "idle"
                   and c["recording"] is False for c in state):
            raise RuntimeError("Recorder unavailable or busy")
        if any(p["status"] not in ("idle", "complete", "cancelled")
               for p in status("/api/timelapse/status")["printers"].values()):
            raise RuntimeError("Timelapse active")
        x, y = (sign, 0) if axis == 0 else (0, -sign)
        hold = float(self.config.get("hold", .12) if hold is None else hold)
        if not .04 <= hold <= .25:
            raise ValueError("Hold must be 40–250 ms")
        try:
            if self.v2:
                self.worker.stdin.write(json.dumps([axis, int(sign), hold])+"\n")
                self.worker.stdin.flush()
                answer=self.worker.stdout.readline().strip()
                if answer != "ok":
                    reason=answer if answer in ("error RuntimeError Start failed","error RuntimeError Stop failed","error RuntimeError Stop unavailable","error ConnectionError") else "worker protocol error"
                    raise RuntimeError("DVRIP pulse failed: "+reason)
                return
            else:
                self.driver.move(x*.25,y*.25)
            time.sleep(hold)
        finally:
            self.stop()

    def close(self):
        try:
            self.stop()
        finally:
            if self.feedback:
                self.feedback.close()
            if self.v2:
                self.worker.stdin.close()
                self.worker.wait(timeout=8)
