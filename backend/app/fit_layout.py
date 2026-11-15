"""Export an entire uncropped video inside a 1080x1920 short with independent background panels.

Only Python's standard library and FFmpeg are required. The background panels may be
solid colors, vertical color gradients, or the live video blurred behind the source.
"""
from __future__ import annotations

import math
import re
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path

W, H = 1080, 1920
HEX = re.compile(r'^#[0-9a-fA-F]{6}$')
MODES = ('solid', 'gradient', 'blur')


def validate_style(clip: dict) -> None:
    if clip.get('layout_mode', 'crop') not in ('crop', 'fit', 'split'):
        raise ValueError('Layout must be crop, fit or split')
    for place in ('top', 'bottom'):
        if clip.get(f'{place}_fill', 'gradient') not in MODES:
            raise ValueError(f'Invalid {place} fill')
        for suffix in ('a', 'b'):
            key = f'{place}_color_{suffix}'
            if not HEX.fullmatch(clip.get(key, '#171126')):
                raise ValueError(f'{key} must be a six-digit hex color')


def fit_dimensions(width: int, height: int) -> tuple[int, int, int, int]:
    if width <= 0 or height <= 0:
        raise ValueError('Invalid source dimensions')
    factor = min(W / width, H / height)
    scaled_w = max(2, min(W, int(width * factor) // 2 * 2))
    scaled_h = max(2, min(H, int(height * factor) // 2 * 2))
    return scaled_w, scaled_h, (W - scaled_w) // 2, (H - scaled_h) // 2


def _rgb(color: str) -> tuple[int, int, int]:
    return tuple(bytes.fromhex(color[1:]))


def _blend(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(round(p * (1 - t) + q * t)) for p, q in zip(a, b))


def background_png(clip: dict, width: int, height: int, target: Path) -> None:
    """Stream an RGBA PNG. Transparent panels reveal the blurred moving source."""
    validate_style(clip)
    _, fitted_h, _, top_end = fit_dimensions(width, height)
    bottom_begin = top_end + fitted_h
    target = Path(target)
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data) & 0xffffffff)
    compressor = zlib.compressobj(level=6)
    compressed: list[bytes] = []
    for y in range(H):
        if y < top_end:
            place, position, length = 'top', y, top_end
        elif y >= bottom_begin:
            place, position, length = 'bottom', y - bottom_begin, H - bottom_begin
        else:
            place, position, length = 'top', 0, 1
        mode = clip.get(f'{place}_fill', 'gradient')
        if top_end <= y < bottom_begin:
            rgba = b'\x00\x00\x00\x00'
        elif mode == 'blur':
            rgba = b'\x00\x00\x00\x00'
        else:
            a = _rgb(clip.get(f'{place}_color_a', '#292044'))
            b = _rgb(clip.get(f'{place}_color_b', '#100E1A'))
            ratio = min(1., position / max(1, length - 1)) if mode == 'gradient' else 0.
            rgba = bytes((*_blend(a, b, ratio), 255))
        compressed.append(compressor.compress(b'\0' + rgba * W))
    compressed.append(compressor.flush())
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('!2I5B', W, H, 8, 6, 0, 0, 0))
    png += chunk(b'IDAT', b''.join(compressed))
    png += chunk(b'IEND', b'')
    target.write_bytes(png)


def ffmpeg_ass_arg(path: Path) -> str:
    """Escape a local filename for FFmpeg's ass filter."""
    escaped = str(path).replace('\\', '\\\\').replace(':', '\\:').replace("'", "\\'").replace(',', '\\,').replace('[', '\\[').replace(']', '\\]')
    return f"ass=filename='{escaped}'"


def build_filter(clip: dict, width: int, height: int, subtitle: Path | None) -> str:
    """Return an FFmpeg filter_complex graph with named [vout] output."""
    needs_blur = any(clip.get(f'{part}_fill', 'gradient') == 'blur' for part in ('top', 'bottom'))
    fg = 'scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos,scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1'
    if needs_blur:
        graph = (
            f'[0:v]split=2[fgsrc][blursrc];'
            f'[blursrc]scale=270:480:force_original_aspect_ratio=increase:flags=fast_bilinear,'
            f'crop=270:480,boxblur=20:2,scale=1080:1920:flags=bilinear,format=rgba[blurred];'
            f'[1:v]format=rgba[panels];'
            f'[blurred][panels]overlay=0:0:shortest=1:format=auto[bg];'
            f'[fgsrc]{fg}[fg];'
            f'[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1:format=auto'
        )
    else:
        graph = (
            f'[0:v]{fg}[fg];'
            f'[1:v]format=rgba[bg];'
            f'[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1:format=auto'
        )
    graph += ',fps=30,setsar=1'
    if subtitle is not None:
        graph += ',' + ffmpeg_ass_arg(subtitle)
    return graph + ',format=yuv420p[vout]'


def render_fit(source: Path, start: float, end: float, clip: dict,
               subtitle: Path | None, output: Path, width: int, height: int) -> None:
    """Create a fitted 9:16 MP4 while retaining the entire source image."""
    if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
        raise ValueError('Invalid source trim interval')
    validate_style(clip)
    source, output = Path(source), Path(output)
    with tempfile.TemporaryDirectory(prefix='openshorts-bg-') as directory:
        bg = Path(directory) / 'background.png'
        background_png(clip, width, height, bg)
        graph = build_filter(clip, width, height, subtitle)
        cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
            '-ss', str(start), '-i', str(source),
            '-loop', '1', '-framerate', '30', '-i', str(bg),
            '-filter_complex', graph, '-map', '[vout]', '-map', '0:a?',
            '-t', str(end - start),
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', str(output)
        ]
        try:
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('Fit video export timed out') from exc
        if process.returncode:
            output.unlink(missing_ok=True)
            raise RuntimeError('Fit video export failed: ' + process.stderr[-1600:])
    if not output.is_file() or output.stat().st_size < 1000:
        raise RuntimeError('Fit video export produced no playable MP4')
