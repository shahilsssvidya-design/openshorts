"""Local, best-effort subject-aware FFmpeg cropping for OpenShorts.

Uses intermittent OpenCV face detection for horizontal pan on landscape video.
Does not identify specific people or promise speaker/character identity tracking.
"""
from __future__ import annotations

from pathlib import Path
import math


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def face_keyframes(path: Path, start: float, end: float, interval: float = 2.0):
    """Return (relative_seconds, normalized_horizontal_face_center) samples.

    OpenCV is optional: failures return an empty set for stable center fallback.
    """
    try:
        import cv2
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        if cascade.empty():
            return []
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return []
        samples = []
        last_center = None
        duration = max(0, end-start)
        # Limit expensive seek-and-detect work to ~48 samples per clip.
        interval = max(interval, duration / 48.0)
        t = 0.0
        try:
            while t < duration + 0.01:
                cap.set(cv2.CAP_PROP_POS_MSEC, (start + t) * 1000)
                ok, frame = cap.read()
                if ok:
                    h, w = frame.shape[:2]
                    scale = min(1.0, 640.0 / max(w, h))
                    if scale < 1:
                        frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    faces = cascade.detectMultiScale(gray, scaleFactor=1.12, minNeighbors=5, minSize=(26,26))
                    if len(faces):
                        fw = frame.shape[1]
                        # Prefer the largest face; avoid jumping between similarly sized faces.
                        def score(face):
                            x,y,w0,h0 = face
                            center=(x + w0 / 2) / fw
                            proximity = (1 - abs(center-last_center)) if last_center is not None else 0.5
                            return (w0*h0) * (0.65 + 0.35*proximity)
                        x,y,fw0,fh0 = max(faces, key=score)
                        center = _clamp((x + fw0/2) / fw, 0, 1)
                        last_center=center
                        samples.append((round(t,3), center))
                t += interval
        finally:
            cap.release()
        return samples
    except Exception:
        return []


def crop_filter(path: Path, start: float, end: float, width: int, height: int, mode: str='auto'):
    """Return FFmpeg crop+scale filter string; valid for original and patched apps."""
    if width <= 0 or height <= 0:
        raise ValueError('Invalid video dimensions')
    mode = mode if mode in ('auto', 'center', 'left', 'right') else 'auto'
    if width / height <= 9 / 16:
        crop_h = max(2, min(height, int(width*16/9)//2*2))
        y = max(0,(height-crop_h)//2)
        return f'crop={width}:{crop_h}:0:{y},scale=1080:1920:flags=lanczos,setsar=1'
    crop_w = max(2, min(width, int(height*9/16)//2*2))
    xmax = width-crop_w
    if mode in ('center','left','right'):
        x = {'left':0,'center':xmax//2,'right':xmax}[mode]
        return f'crop={crop_w}:{height}:{x}:0,scale=1080:1920:flags=lanczos,setsar=1'
    samples=face_keyframes(path,start,end)
    if not samples:
        return f'crop={crop_w}:{height}:{xmax//2}:0,scale=1080:1920:flags=lanczos,setsar=1'
    # Map detected face position to legal crop x, limited to <= 170 px per second.
    keyframes = [(0.0, _clamp(width*samples[0][1]-crop_w/2, 0, xmax))]
    for t,center in samples[1:]:
        raw = _clamp(width*center-crop_w/2, 0, xmax)
        prior_t,prior_x = keyframes[-1]
        max_delta = max(1, t-prior_t)*170
        x = _clamp(raw, prior_x-max_delta, prior_x+max_delta)
        keyframes.append((t,x))
    # Gentle smoothing to suppress frame-to-frame jitter while retaining movement.
    smoothed=[]
    for i,(t,x) in enumerate(keyframes):
        left=keyframes[max(0,i-1)][1]
        right=keyframes[min(len(keyframes)-1,i+1)][1]
        smoothed.append((t,round(_clamp(0.2*left+0.6*x+0.2*right,0,xmax),2)))
    if len(smoothed)==1:
        xpos=f'{round(smoothed[0][1])}'
    else:
        # FFmpeg uses t from the -ss trimmed input. Piecewise linear movement.
        expr=f'{smoothed[-1][1]:.2f}'
        for (t0,x0),(t1,x1) in reversed(list(zip(smoothed[:-1],smoothed[1:]))):
            span=max(.001,t1-t0)
            segment=f'({x0:.2f}+({x1-x0:.2f})*(t-{t0:.3f})/{span:.3f})'
            expr=f'if(lt(t,{t1:.3f}),{segment},{expr})'
        # Escape commas in the nested FFmpeg expression so they are not parsed as filter separators.
        xpos=expr.replace(',',r'\,')
    return f'crop={crop_w}:{height}:{xpos}:0,scale=1080:1920:flags=lanczos,setsar=1'
