"""Read-only Klipper API socket sampler. Run on the printer host over SSH."""
import argparse
import json
import socket
import time


def sample(path):
    sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    sock.connect(path)
    def send(data):
        sock.sendall(json.dumps(data).encode()+b"\x03")
    send(dict(id=1,method="motion_report/dump_trapq",params=dict(name="toolhead",response_template={"queue":True})))
    sock.settimeout(.05)
    buf=b""
    due=0
    while True:
        if time.monotonic()>=due:
            send(dict(id=2,method="objects/query",params={"objects":{"toolhead":["estimated_print_time"],"motion_report":["live_position"]}}))
            due=time.monotonic()+.15
        try:
            data=sock.recv(65536)
        except socket.timeout: continue
        if not data: return
        buf+=data
        while b"\x03" in buf:
            raw,buf=buf.split(b"\x03",1)
            msg=json.loads(raw)
            if "error" in msg: raise RuntimeError("Klipper query rejected")
            if msg.get("queue"):
                print(json.dumps({"moves":msg["params"]["data"]}),flush=True)
            elif msg.get("id")==2:
                status=msg["result"]["status"]
                print(json.dumps({"clock":status["toolhead"]["estimated_print_time"],
                                  "xyz":status["motion_report"]["live_position"][:3]}),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("socket")
    sample(parser.parse_args().socket)
