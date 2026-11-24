"""Use a timestamped queue only while it covers the requested future instant."""
from collections import deque
import json
import subprocess
import threading
import time
import numpy as np


class QueuePrediction:
    def __init__(self, command, projection):
        self.projection=np.array(projection,float).reshape(2,3)
        self.moves=deque(maxlen=4096)
        self.clock=None
        self.lock=threading.Lock()
        self.proc=subprocess.Popen(command,stdout=subprocess.PIPE,text=True)
        threading.Thread(target=self._read,daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            msg=json.loads(line)
            with self.lock:
                if "clock" in msg: self.clock=(time.monotonic(),msg["clock"],np.array(msg["xyz"]))
                if "moves" in msg: self.moves.extend(msg["moves"])

    def displacement(self, horizon):
        with self.lock:
            if not self.clock: return None
            arrival,clock,_=self.clock
            age=time.monotonic()-arrival
            if age>.35: return None
            def xyz(t):
                for start,length,speed,accel,pos,direction in reversed(self.moves):
                    dt=t-start
                    if 0<=dt<=length:
                        return np.array(pos[:3])+np.array(direction[:3])*(speed*dt+.5*accel*dt*dt)
                return None
            current=xyz(clock+age)
            future=xyz(clock+age+horizon)
            if current is None or future is None: return None
            return self.projection@(future-current)

    def close(self):
        self.proc.terminate()
        self.proc.wait(timeout=5)
