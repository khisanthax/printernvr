"""Repeatable native-resolution replay with a known image-space trajectory and occlusion."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys
import cv2
import numpy as np


def benchmark(source, calibration, output):
    output.mkdir(parents=True,exist_ok=False)
    cap=cv2.VideoCapture(str(source))
    fps=cap.get(cv2.CAP_PROP_FPS)
    cal=json.loads(calibration.read_text())
    H,W=cal["shape"]
    anchor=np.array(cal["tip"])
    roi=cal["roi"]
    movie=output/"stimulus.mkv"
    writer=cv2.VideoWriter(str(movie),cv2.VideoWriter_fourcc(*"FFV1"),fps,(W,H))
    if not writer.isOpened(): raise RuntimeError("FFV1 encoder unavailable")
    truth=[]
    ok,base=cap.read()
    if not ok: raise RuntimeError("Empty input")
    while len(truth)<int(fps*10):
        f=base
        t=len(truth)/fps
        dx=round(W*(.36*min(1,t/3)+.015*np.sin(9*t)))
        dy=round(H*.20*min(1,t/2))
        frame=cv2.warpAffine(f,np.float32([[1,0,dx],[0,1,dy]]),(W,H),
                             borderMode=cv2.BORDER_REPLICATE)
        visible=not (4 <= t < 5)
        if not visible:
            x,y,w,h=roi
            frame[y+dy-25:y+dy+h+100,x+dx-20:x+dx+w+20]=40
        writer.write(frame)
        truth.append([*(anchor+[dx,dy]),visible])
    writer.release()
    cap.release()
    g=np.array(truth)
    for mode in "ABC":
        run=output/mode
        subprocess.run([sys.executable,str(Path(__file__).with_name("track.py")),
                        "--input",str(movie),"--calibration",str(calibration),"--mode",mode,
                        "--output",str(run),"--simulate"],check=True)
        with (run/"frames.csv").open() as f:
            rows=list(csv.DictReader(f))
        def col(key):return np.array([float(r[key]) for r in rows])
        meta=json.loads((run/"runtime.json").read_text())
        target=g[:len(rows),:2]-np.column_stack([col("shift_x"),col("shift_y")])
        loc=target-np.column_stack([col("left"),col("top")])
        crop=np.array(meta["crop"])
        exists=g[:len(rows),2].astype(bool)
        visible=exists & np.all((loc>=0)&(loc<crop),axis=1)
        detected=np.hypot(col("x")-target[:,0],col("y")-target[:,1])<12
        err=np.linalg.norm(loc-crop/2,axis=1)
        after=np.where((col("t")>=5)&detected&visible)[0]
        # Compare encoded target-patch high-frequency contrast to the native ROI.
        # This is an optical-detail proxy, not a filament width measurement.
        def sharp(patch):
            return cv2.Laplacian(cv2.cvtColor(patch,cv2.COLOR_BGR2GRAY),cv2.CV_64F).var()
        ax,ay=anchor.astype(int)
        ref=sharp(base[ay-12:ay+12,ax-12:ax+12])
        encoded=cv2.VideoCapture(str(run/"tracked.mp4"))
        ratios=[]
        for i,(x,y) in enumerate(np.rint(loc).astype(int)):
            ok,f=encoded.read()
            if not ok: break
            if visible[i] and 12<=x<crop[0]-12 and 12<=y<crop[1]-12 and ref>0:
                ratios.append(sharp(f[y-12:y+12,x-12:x+12])/ref)
        encoded.release()
        result=dict(detail_contrast_ratio=float(np.median(ratios)) if ratios else None,visible_pct=100*visible.mean(),center_rms_px=float(np.sqrt(np.mean(err[visible]**2))),
                    reacquire_s=float(col("t")[after[0]]-5) if len(after) else None,
                    jogs_per_min=col("jog").sum()*60/(len(rows)/fps),
                    cpu_core_pct=100*meta["cpu_s"]/meta["wall_s"],rss_peak_mib=max(col("rss_mib")),
                    process_p95_ms=np.percentile(col("processing_ms"),95))
        (run/"scores.json").write_text(json.dumps(result,indent=2))
        print(mode,result,flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    for name in ("source","calibration","output"):p.add_argument(name,type=Path)
    a=p.parse_args()
    benchmark(a.source,a.calibration,a.output)
