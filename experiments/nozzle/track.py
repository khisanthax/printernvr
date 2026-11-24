"""Standalone native-frame tracking and an explicitly simulated PTZ replay."""
import argparse
import concurrent.futures
import csv
import json
import os
from pathlib import Path
import time
import queue
import threading

import cv2
import numpy as np
import psutil

from controls import Camera


def crop_origin(center, size, image):
    return np.clip(np.rint(center - size/2), 0, image-size).astype(int)


def calibrate(frame):
    import tkinter as tk
    import base64
    root=tk.Tk()
    H,W=frame.shape[:2]
    scale=min(1.,(root.winfo_screenwidth()-80)/W,(root.winfo_screenheight()-130)/H)
    photo=tk.PhotoImage(data=base64.b64encode(cv2.imencode(".png",cv2.resize(frame,None,fx=scale,fy=scale))[1]).decode())
    canvas=tk.Canvas(root,width=photo.width(),height=photo.height())
    canvas.pack()
    canvas.create_image(0,0,image=photo,anchor="nw")
    steps=["Click top-left of a distinctive toolhead feature","Click bottom-right of that feature","Click nozzle tip"]
    points=[]
    root.title(steps[0])
    def click(event):
        points.append((round(event.x/scale),round(event.y/scale)))
        if len(points)==3:root.destroy()
        else:root.title(steps[len(points)])
    canvas.bind("<Button-1>",click)
    root.bind("<Escape>",lambda _:root.destroy())
    root.mainloop()
    if len(points)!=3: raise ValueError("Calibration cancelled")
    (x,y),(r,b),tip=points
    if min(r-x,b-y)<8: raise ValueError("Select a larger feature")
    return dict(roi=[x,y,r-x,b-y],tip=tip,shape=[H,W])



class Locator:
    def __init__(self, frame, cal, zone):
        x,y,w,h = map(int,cal["roi"])
        self.template = cv2.cvtColor(frame[y:y+h,x:x+w], cv2.COLOR_BGR2GRAY)
        if self.template.size == 0 or self.template.std() < 4:
            raise ValueError("Calibration needs a textured feature")
        self.offset = np.array(cal["tip"])-[x,y]
        self.zone = np.array(zone)
        self.last = np.array([x,y])
        self.lost = False

    def find(self, frame):
        gray = cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
        h,w = self.template.shape
        H,W = gray.shape
        bounds = np.rint(self.zone * [W,H,W,H]).astype(int)
        x,y,r,b = bounds
        if not self.lost:
            a,c = self.last
            x,y,r,b = max(x,a-110),max(y,c-110),min(r,a+w+110),min(b,c+h+110)
        search=gray[y:b,x:r]
        best=(0,None,1.)
        scales=(1.,.8,1.25,1.6,2.) if self.lost else (getattr(self,"scale",1.),)
        for scale in scales:
            ref=self.template if scale==1 else cv2.resize(self.template,None,fx=scale,fy=scale)
            if search.shape[0]<ref.shape[0] or search.shape[1]<ref.shape[1]: continue
            scores=cv2.matchTemplate(search,ref,cv2.TM_CCOEFF_NORMED)
            _,score,_,loc=cv2.minMaxLoc(scores)
            if score>best[0]: best=score,loc,scale
        score,loc,self.scale=best
        self.lost=score<.76
        if self.lost: return None
        self.last=np.array(loc)+[x,y]
        return self.last+np.rint(self.offset*self.scale).astype(int)



class NativeRTSP:
    def __init__(self,url):
        import subprocess
        params = ["-rtsp_transport","tcp","-timeout","6000000"]
        probe = subprocess.run(["ffprobe","-v","quiet",*params,"-select_streams","v:0",
            "-show_entries","stream=width,height,avg_frame_rate","-of","json",url],
            capture_output=True,timeout=15)
        if probe.returncode: raise RuntimeError("Native stream probe failed")
        info=json.loads(probe.stdout)["streams"][0]
        self.width,self.height=info["width"],info["height"]
        from fractions import Fraction
        self.fps=float(Fraction(info["avg_frame_rate"])) if info["avg_frame_rate"]!="0/0" else 25
        self.decoder=subprocess.Popen(["ffmpeg","-loglevel","quiet",*params,"-i",url,"-map","0:v:0",
            "-an","-f","rawvideo","-pix_fmt","bgr24","pipe:1"],stdout=subprocess.PIPE)

    def read(self):
        raw=self.decoder.stdout.read(self.width*self.height*3)
        if len(raw)!=self.width*self.height*3: return False,None
        return True,np.frombuffer(raw,np.uint8).reshape(self.height,self.width,3)

    def release(self):
        if self.decoder.poll() is None: self.decoder.terminate()
        self.decoder.wait(timeout=5)


class LatestFrame:
    def __init__(self, cap):
        self.cap = cap
        self.frames = queue.Queue(1)
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self._pump,daemon=True)
        self.thread.start()

    def _pump(self):
        while not self.closed.is_set():
            ok, frame = self.cap.read()
            try: self.frames.get_nowait()
            except queue.Empty: pass
            self.frames.put((ok,frame))
            if not ok: break

    def read(self):
        return self.frames.get(timeout=8)

    def release(self):
        self.closed.set()
        if isinstance(self.cap,NativeRTSP): self.cap.release()
        self.thread.join(8)
        if not self.thread.is_alive(): self.cap.release()


def scene_shift(before, after, roi):
    # Recover framing from stationary printer surroundings, independent of the nozzle.
    mask=np.full(before.shape[:2],255,np.uint8)
    x,y,w,h=roi
    mask[max(0,y-h):y+2*h,max(0,x-w):x+2*w]=0
    mask[:before.shape[0]//9]=0
    orb=cv2.ORB_create(1400)
    ka,da=orb.detectAndCompute(before,mask)
    kb,db=orb.detectAndCompute(after,None)
    if da is None or db is None: return None
    pairs=cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(da,db,k=2)
    good=[p[0] for p in pairs if len(p)==2 and p[0].distance<.72*p[1].distance]
    if len(good)<20: return None
    a=np.float32([ka[m.queryIdx].pt for m in good])
    b=np.float32([kb[m.trainIdx].pt for m in good])
    mat,inliers=cv2.estimateAffinePartial2D(a,b,ransacReprojThreshold=3)
    if mat is None or inliers.sum()<18: return None
    center=np.array(before.shape[1::-1])/2
    return mat@np.r_[center,1]-center


def run(args):
    cv2.setNumThreads(2)
    cfg = json.loads(Path(args.config).read_text()) if args.config else {}
    source = os.environ["NOZZLE_RTSP"] if args.live else args.input
    cam = None
    if args.mode!="A" and not (args.actuate or args.simulate):
        raise ValueError("Select --simulate for replay or --actuate for physical tracking")
    if args.actuate and (not args.live or args.mode == "A" or args.simulate):
        raise ValueError("Actuation requires live B or C")
    out = Path(args.output)
    out.mkdir(parents=True,exist_ok=False)
    if args.live:
        device = NativeRTSP(source)
        fps = device.fps
        cap = LatestFrame(device)
    else:
        cap = cv2.VideoCapture(source)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
    ok,first = cap.read()
    if not ok:
        raise RuntimeError("Could not read native video")
    cal = json.loads(Path(args.calibration).read_text()) if args.calibration else calibrate(first)
    if tuple(cal["shape"]) != first.shape[:2]:
        raise ValueError("Calibration resolution differs from source")
    (out/"calibration.json").write_text(json.dumps(cal))
    zone = cfg.get("zone",[0,0,1,1])
    if not (0 <= zone[0]<zone[2]<=1 and 0<=zone[1]<zone[3]<=1):
        raise ValueError("Zone must be normalized left, top, right, bottom")
    tracker = Locator(first, cal, zone)
    if args.calibration:
        ref = Path(args.calibration).with_suffix(".png")
        if ref.is_file():
            image = cv2.imread(str(ref),cv2.IMREAD_GRAYSCALE)
            if image is None or image.shape != tracker.template.shape:
                raise ValueError("Calibration template size mismatch")
            tracker.template = image
            tracker.lost = True
    cv2.imwrite(str(out/"calibration.png"),tracker.template)
    anchor = tracker.find(first)
    deadline=time.monotonic()+3
    while args.live and anchor is None and time.monotonic()<deadline:
        ok,first=cap.read()
        if not ok: break
        anchor=tracker.find(first)
    if args.actuate and anchor is None:
        raise ValueError("Cannot identify initial framing")
    H,W = first.shape[:2]
    size = np.array([W,H])
    fraction = float(cfg.get("crop_fraction",.45))
    if not 0 < fraction <= 1:
        raise ValueError("Invalid crop fraction")
    crop = (size*fraction/2).astype(int)*2
    writer = cv2.VideoWriter(str(out/"tracked.mp4"),cv2.VideoWriter_fourcc(*"mp4v"),fps,tuple(map(int,crop)))
    if not writer.isOpened():
        raise RuntimeError("Video encoder unavailable")
    proc = psutil.Process()
    def resources():
        cpu=rss=0
        for task in [proc,*proc.children(recursive=True)]:
            try:
                times=task.cpu_times()
                cpu+=times.user+times.system
                rss+=task.memory_info().rss
            except psutil.NoSuchProcess: pass
        return cpu,rss/2**20
    tree_start,_=resources()
    tree_cpu=tree_peak=0.
    cpu0 = time.process_time()
    start = time.monotonic()
    data = []
    latency_ref=None
    responses=[]
    shift = np.zeros(2)
    pending = None
    future = None
    pool = concurrent.futures.ThreadPoolExecutor(1)
    last_target = None
    last_time = 0.
    previous_output=-1
    velocity = np.zeros(2)
    dwell = None
    last_dir = None
    next_move = 0.
    desired = size/2
    paused = False
    frame = first
    pose = None
    initial_pose = None
    queue_predictor = None
    override=Path(cfg["hold_file"]) if cfg.get("hold_file") else None
    try:
        if args.live and cfg.get("queue_command"):
            from prediction import QueuePrediction
            queue_predictor=QueuePrediction(cfg["queue_command"],cfg["pixels_per_mm"])
        if args.actuate:
            cam = Camera(cfg)
            pose = cam.pose()
            initial_pose = pose
        while frame is not None:
            begin = time.monotonic()
            t = begin-start if args.live else len(data)/fps
            if t >= args.seconds:
                break
            if pending and t >= pending[0]:
                shift[pending[1]] += pending[2]
                pending = None
            if args.simulate and np.any(shift):
                frame = cv2.warpAffine(frame,np.float32([[1,0,-shift[0]],[0,1,-shift[1]]]),(W,H))
            if future and future.done():
                future.result()
                future = None
                pose = cam.pose()
            point = tracker.find(frame)
            issued = False
            if point is None or paused or (override and override.exists()):
                dwell = last_dir = last_target = None
                velocity[:] = 0
            else:
                if last_target is not None:
                    velocity = .7*velocity+.3*(point-last_target)/max(.01,t-last_time)
                last_target,last_time = point.copy(),t
                horizon=cfg.get("horizon_s",.20)
                offset=queue_predictor.displacement(horizon) if queue_predictor else None
                predicted=point+np.clip(velocity*horizon if offset is None else offset,-size*.12,size*.12)
                error = (predicted-size/2)/size
                axis = int(np.argmax(np.abs(error)))
                direction = (axis,int(np.sign(error[axis])))
                if abs(error[axis]) < cfg.get("deadband",.13):
                    dwell = last_dir = None
                elif direction != last_dir:
                    dwell,last_dir = t,direction
                elif (args.mode != "A" and (cam or args.simulate) and t>=next_move and
                      t-dwell >= (cfg.get("dwell_s",.5) if args.mode=="C" else 0)
                      and not future and not pending):
                    if cam:
                        if initial_pose is not None:
                            pose=cam.pose()
                            if pose is None or max(abs(np.array(pose)-initial_pose))>cfg.get("max_excursion_deg",15):
                                break
                        latency_ref=(time.monotonic(),frame.copy(),len(data))
                        future = pool.submit(cam.jog,*direction)
                    else:
                        pending = (t+cfg.get("horizon_s",.20),axis,direction[1]*cfg.get("step_px",36))
                    issued = True
                    next_move = t+cfg.get("cooldown_s",.55)
                desired = point if args.mode != "B" else size/2
            left,top = crop_origin(desired,crop,size)
            view = frame[top:top+crop[1],left:left+crop[0]]
            output_index=int(round(t*fps)) if args.live else previous_output+1
            for _ in range(max(0,output_index-previous_output)):
                writer.write(view)
            previous_output=output_index
            if latency_ref and len(data)>latency_ref[2]:
                displacement=scene_shift(latency_ref[1],frame,cal["roi"])
                if displacement is not None and max(abs(displacement))>4:
                    responses.append(1000*(time.monotonic()-latency_ref[0]))
                    latency_ref=None
            p = point if point is not None else [np.nan,np.nan]
            tree_total,tree_rss=resources()
            tree_cpu=max(tree_cpu,tree_total-tree_start)
            tree_peak=max(tree_peak,tree_rss)
            data.append([t,*p,left,top,*shift,int(issued),(time.monotonic()-begin)*1000,
                         proc.memory_info().rss/2**20,*(pose or [None,None])])
            if args.preview:
                cv2.imshow("Tracked view: space hold/resume, c recalibrate, q quit", view)
                key = cv2.waitKey(1)&255
                if key==ord("q"): break
                if key==32:
                    paused=not paused
                    if paused and future:
                        future.result()
                        future=None
                if key==ord("c"):
                    if cam: continue  # Preserve the physical restoration reference.
                    tracker=Locator(frame,calibrate(frame),zone)
                    last_target=dwell=last_dir=None
                    velocity[:]=0
            ok,frame=cap.read()
            if not ok: break
    finally:
        if queue_predictor: queue_predictor.close()
        pool.shutdown(wait=True,cancel_futures=True)
        if cam:
            try:
                for _ in range(8):
                    if paused or (override and override.exists()):
                        break
                    # Use a settled, fresh view after the previous command.
                    time.sleep(.6)
                    ok,current = cap.read()
                    error = scene_shift(first,current,cal["roi"]) if ok else None
                    if error is None: break
                    axis = int(np.argmax(abs(error)))
                    (out/"restore.json").write_text(json.dumps(error.tolist()))
                    if max(abs(error)) < cfg.get("restore_tolerance_px",18): break
                    if _ == 7: break
                    cam.jog(axis,int(np.sign(error[axis])),hold=.055)
            finally:
                cam.close()
        writer.release()
        cap.release()
        if args.preview: cv2.destroyAllWindows()
        with (out/"frames.csv").open("w",newline="") as f:
            w=csv.writer(f)
            w.writerow("t x y left top shift_x shift_y jog processing_ms rss_mib pan tilt".split())
            w.writerows(data)
        (out/"runtime.json").write_text(json.dumps(dict(cpu_s=time.process_time()-cpu0,
            wall_s=time.monotonic()-start,fps=fps,width=W,height=H,crop=crop.tolist(),
            tree_cpu_s=tree_cpu,tree_peak_mib=tree_peak,tracking_s=(data[-1][0] if data else 0),mode=args.mode,simulated=args.simulate,live=args.live,dispatch_to_visible_ms=responses),indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    src=parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--input")
    src.add_argument("--live",action="store_true")
    parser.add_argument("--mode",choices=list("ABC"),required=True)
    parser.add_argument("--config")
    parser.add_argument("--calibration")
    parser.add_argument("--output",required=True)
    parser.add_argument("--seconds",type=float,default=60)
    parser.add_argument("--actuate",action="store_true")
    parser.add_argument("--simulate",action="store_true")
    parser.add_argument("--preview",action="store_true")
    run(parser.parse_args())
