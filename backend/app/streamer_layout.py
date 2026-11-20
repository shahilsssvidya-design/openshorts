"""Render a streamer facecam and gameplay from the SAME source video.

The automatic detector is deliberately conservative: when it cannot verify a
facecam-like face near a corner, the render stops instead of uploading a badly
framed Short. A manual normalized rectangle works without OpenCV.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

CAM_HEIGHT = 720
GAME_HEIGHT = 1200
VIDEO_WIDTH = 1080
LOCATIONS = ('auto', 'top-left', 'top-right', 'bottom-left', 'bottom-right', 'manual')


def validate_options(options: dict) -> None:
    region = options.get('facecam_region', 'auto')
    if region not in LOCATIONS:
        raise ValueError('Invalid facecam location')
    values = [float(options.get(k, default)) for k, default in (
        ('facecam_x', 0.0), ('facecam_y', 0.0),
        ('facecam_w', 0.32), ('facecam_h', 0.32))]
    if any(not math.isfinite(v) for v in values):
        raise ValueError('Facecam coordinates must be finite')
    x, y, w, h = values
    if min(x, y) < 0 or min(w, h) <= 0 or x + w > 1.000001 or y + h > 1.000001:
        raise ValueError('Facecam rectangle must fit entirely inside the source video')


def _manual_roi(options: dict, width: int, height: int) -> tuple[int, int, int, int]:
    x = float(options.get('facecam_x', 0))
    y = float(options.get('facecam_y', 0))
    w = float(options.get('facecam_w', 0.32))
    h = float(options.get('facecam_h', 0.32))
    return (
        int(x * width), int(y * height),
        max(2, int(w * width)), max(2, int(h * height))
    )


def _detect_roi(source: Path, start: float, end: float, width: int, height: int):
    try:
        import cv2
    except ImportError as exc:
        raise ValueError('Auto facecam detection needs opencv-python. Install it or select Manual facecam location.') from exc

    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    if cascade.empty():
        raise ValueError('OpenCV face detector could not be loaded; use Manual facecam location.')
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise ValueError('Could not scan source for facecam; use Manual facecam location.')

    sightings = []
    try:
        span = max(0, end - start)
        for portion in (0.0, 0.2, 0.4, 0.6, 0.8):
            cap.set(cv2.CAP_PROP_POS_MSEC, (start + span * portion) * 1000)
            ok, frame = cap.read()
            if not ok:
                continue
            h, w = frame.shape[:2]
            factor = min(1.0, 640 / max(w, h))
            if factor < 1:
                frame = cv2.resize(frame, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            found = cascade.detectMultiScale(gray, scaleFactor=1.12, minNeighbors=5, minSize=(24, 24))
            fw, fh = frame.shape[1], frame.shape[0]
            for fx, fy, dw, dh in found:
                cx, cy = (fx + dw / 2) / fw, (fy + dh / 2) / fh
                # Reject central gameplay faces and unrealistically huge detections.
                corner = (cx < 0.38 or cx > 0.62) and (cy < 0.42 or cy > 0.58)
                if corner and 0.025 <= dw / fw <= 0.25:
                    sightings.append((cx, cy, dw / fw, dh / fh))
    finally:
        cap.release()

    if len(sightings) < 2:
        raise ValueError('No reliable embedded facecam detected. Choose a corner or Manual facecam rectangle before exporting.')

    # Choose the quadrant with the strongest repeated evidence, not a single face.
    buckets = {}
    for s in sightings:
        key = ('left' if s[0] < 0.5 else 'right', 'top' if s[1] < 0.5 else 'bottom')
        buckets.setdefault(key, []).append(s)
    strongest = max(buckets.values(), key=len)
    if len(strongest) < 2:
        raise ValueError('Facecam location is uncertain. Set its location manually.')
    cx = sum(s[0] for s in strongest) / len(strongest)
    cy = sum(s[1] for s in strongest) / len(strongest)
    face_w = sum(s[2] for s in strongest) / len(strongest)
    face_h = sum(s[3] for s in strongest) / len(strongest)
    roi_w = min(0.55, max(0.24, face_w * 3.5))
    roi_h = min(0.72, max(0.24, face_h * 3.0))
    return (
        int(max(0, min(1 - roi_w, cx - roi_w / 2)) * width),
        int(max(0, min(1 - roi_h, cy - roi_h / 2)) * height),
        int(roi_w * width),
        int(roi_h * height),
    )


def facecam_roi(source: Path, start: float, end: float, width: int, height: int, options: dict):
    validate_options(options)
    region = options.get('facecam_region', 'auto')
    if region == 'auto':
        raw = _detect_roi(source, start, end, width, height)
    elif region == 'manual':
        raw = _manual_roi(options, width, height)
    else:
        # A generous static corner box; users can refine it using Manual.
        w, h = int(width * 0.36), int(height * 0.40)
        x = 0 if region.endswith('left') else width - w
        y = 0 if region.startswith('top') else height - h
        raw = x, y, w, h
    x, y, w, h = raw
    # H.264-friendly even coordinates; never permit a crop outside the source.
    w = max(2, min(width, w) // 2 * 2)
    h = max(2, min(height, h) // 2 * 2)
    x = max(0, min(width - w, x) // 2 * 2)
    y = max(0, min(height - h, y) // 2 * 2)
    return x, y, w, h


def build_filter(roi: tuple[int, int, int, int], subtitle: Path | None = None) -> str:
    x, y, w, h = roi
    if min(w, h) < 2:
        raise ValueError('Facecam crop is too small')
    # Split one input into two synchronized views; preserve original audio.
    graph = (
        '[0:v]split=2[cam_in][game_in];'
        f'[cam_in]crop={w}:{h}:{x}:{y},'
        f'scale={VIDEO_WIDTH}:{CAM_HEIGHT}:force_original_aspect_ratio=increase:flags=lanczos,'
        f'crop={VIDEO_WIDTH}:{CAM_HEIGHT},setsar=1[cam];'
        f'[game_in]scale={VIDEO_WIDTH}:{GAME_HEIGHT}:force_original_aspect_ratio=increase:flags=lanczos,'
        f'crop={VIDEO_WIDTH}:{GAME_HEIGHT},setsar=1[game];'
        '[cam][game]vstack=inputs=2,fps=30,format=yuv420p'
    )
    if subtitle is not None:
        from .fit_layout import ffmpeg_ass_arg
        graph += ',' + ffmpeg_ass_arg(subtitle)
    return graph + '[vout]'


def render_facecam(source: Path, start: float, end: float, clip: dict,
                   subtitle: Path | None, output: Path, width: int, height: int):
    if not (0 <= start < end):
        raise ValueError('Invalid trim interval')
    if width < 2 or height < 2:
        raise ValueError('Invalid input dimensions')
    source, output = Path(source), Path(output)
    roi = facecam_roi(source, start, end, width, height, clip)
    cmd = [
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
        '-ss', str(start), '-i', str(source), '-t', str(end - start),
        '-filter_complex', build_filter(roi, subtitle),
        '-map', '[vout]', '-map', '0:a?',
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', str(output),
    ]
    try:
        run = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('Facecam render timed out') from exc
    if run.returncode:
        raise RuntimeError('Facecam render failed: ' + run.stderr[-900:])
    if not output.is_file() or output.stat().st_size < 1000:
        raise RuntimeError('Facecam render did not produce a usable MP4')
