"""Tests for gaming Shorts visual scoring and post-render quality flags."""
from pathlib import Path
import subprocess
import pytest

from app.moment_intelligence import choose_moments, _visual
from app.output_quality import inspect_export


def transcript():
    return [
        {'start':0,'end':5,'text':'Bro what just happened? This car is going crazy!'},
        {'start':5,'end':10,'text':'Look at the truck! No way that worked!'},
        {'start':10,'end':16,'text':'Wait it is flying and now falling in the water!'},
        {'start':16,'end':20,'text':'That was insane. I cannot believe this bug!'},
    ]


def test_short_complete_moments_without_media():
    clips=choose_moments(transcript(),20)
    assert clips
    assert 8<=clips[0]['end']-clips[0]['start']<=46
    assert clips[0]['score']<=72
    assert clips[0]['quality_metrics']['visual_verified'] is False
    assert clips[0]['style']=='outline'


def test_visual_metrics_and_report(tmp_path):
    src=tmp_path/'motion.mp4'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi',
                    '-i','testsrc2=s=1080x1920:r=15','-t','3',
                    '-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',str(src)],
                    check=True,timeout=120)
    m=_visual(src,0,3)
    assert m is not None
    assert m['visual_activity']>=0
    report=inspect_export(src)
    assert report['width']==1080 and report['height']==1920
    assert isinstance(report['warnings'],list)


def test_bad_geometry_is_rejected(tmp_path):
    src=tmp_path/'landscape.mp4'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi',
                    '-i','color=c=black:s=320x180:r=10','-t','1.5','-c:v','mpeg4',str(src)],
                   check=True,timeout=60)
    with pytest.raises(ValueError,match='1080x1920'):
        inspect_export(src)
