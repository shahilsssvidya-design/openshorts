"""Post-render checks for vertical Shorts.

These checks catch broken geometry, bad duration, excessive darkness, and
visually static exports. They do not understand story semantics or guarantee
audience retention. Manual exports receive warnings, not forced rejection.
"""
from __future__ import annotations
import json, math, subprocess
from pathlib import Path
from .moment_intelligence import _visual

def inspect_export(path: Path) -> dict:
    path=Path(path)
    if not path.is_file() or path.stat().st_size<1000:
        raise ValueError('Export file is missing or empty')
    try:
        run=subprocess.run(
            ['ffprobe','-v','error','-show_entries','stream=codec_type,width,height:format=duration',
             '-of','json',str(path)],capture_output=True,text=True,timeout=30,check=True)
        payload=json.loads(run.stdout)
        stream=next(s for s in payload['streams'] if s['codec_type']=='video')
        w,h=int(stream['width']),int(stream['height'])
        duration=float(payload['format']['duration'])
    except (OSError,ValueError,KeyError,StopIteration,subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
        raise ValueError('Rendered video cannot be probed') from exc
    if w!=1080 or h!=1920:
        raise ValueError(f'Export must be 1080x1920, got {w}x{h}')
    if not math.isfinite(duration) or duration<1:
        raise ValueError('Export video has an invalid duration')
    warnings=[]
    if duration>60: warnings.append('Longer than 60 seconds; consider trimming pauses.')
    if duration<8: warnings.append('Very short; check that the story has a payoff.')
    evidence=_visual(path,0,min(duration,35))
    if evidence is None:
        warnings.append('Visual activity could not be verified.')
    else:
        if evidence['static']: warnings.append('Little visual change detected. Review pacing and action.')
        if evidence['dark']: warnings.append('Dark frames dominate. Check gameplay visibility.')
    return {'width':w,'height':h,'duration':round(duration,2),
            'visual_metrics':evidence,'warnings':warnings,
            'publish_ready':len(warnings)==0 and evidence is not None}

def save_report(path: Path) -> dict:
    report=inspect_export(path)
    dest=Path(str(path)+'.quality.json')
    dest.write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report
