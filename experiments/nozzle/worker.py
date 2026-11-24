"""Private stdio transport. Run in the pinned DVRIP bridge environment."""
import os
import threading
import contextlib
import json
import sys
import time
from bridge import DVRIPController

def main(reply):
    config = json.loads(sys.stdin.readline())
    driver = DVRIPController(dict(name="experiment", channel=0, **config))
    print("ready", file=reply, flush=True)
    for line in sys.stdin:
        axis, sign, duration = json.loads(line)
        if axis not in (0, 1) or sign not in (-1, 1) or not .04 <= duration <= .25:
            raise ValueError("Invalid pulse")
        code = (("Left","Right"),("Up","Down"))[axis][sign > 0]
        params = driver._params(code,1,0)
        def command(action):
            result = driver._client.send_call(dict(method="ptz."+action,params=params,
                object=driver._object_id),errorcodes=True)
            return isinstance(result,dict) and result.get("result") is True
        def emergency_stop():
            spare=DVRIPController(dict(name="stop",channel=0,**config))
            try:
                spare._connect()
                spare._rpc("ptz.stop",params)
            finally:
                spare._disconnect()
        with contextlib.redirect_stdout(sys.stderr):
            driver._connect()
            if not command("stop"):
                driver._disconnect()
                driver._connect()
                if not command("stop"): raise RuntimeError("Stop unavailable")
            timer=threading.Timer(.65,emergency_stop)
            timer.start()
            try:
                if not command("start"): raise RuntimeError("Start failed")
                time.sleep(duration)
            finally:
                if not command("stop"):
                    driver._disconnect()
                    driver._connect()
                    if not command("stop"): raise RuntimeError("Stop failed")
                timer.cancel()
                timer.join()
        print("ok", file=reply, flush=True)
    driver._disconnect()

if __name__ == "__main__":
    reply=os.fdopen(os.dup(1),"w",buffering=1)
    os.dup2(2,1)
    try:
        main(reply)
    except Exception as exc:
        print("error "+type(exc).__name__+" "+str(exc)[:24] if isinstance(exc,RuntimeError) else "error "+type(exc).__name__,file=reply,flush=True)
        raise
