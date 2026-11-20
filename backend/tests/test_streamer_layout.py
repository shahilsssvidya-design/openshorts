"""Regression tests for the embedded streamer-facecam layout."""
from pathlib import Path
import subprocess

import pytest

from app.streamer_layout import build_filter, facecam_roi, validate_options
from app.main import checked_layout_settings


def test_project_defaults_are_safe():
    assert checked_layout_settings({})['layout_mode'] == 'crop'
    selected = checked_layout_settings({'layout_mode': 'facecam', 'facecam_region': 'top-right'})
    assert selected['layout_mode'] == 'facecam'
    assert selected['facecam_region'] == 'top-right'


@pytest.mark.parametrize('invalid', [
    {'layout_mode': 'unknown'},
    {'layout_mode': 'facecam', 'facecam_region': 'somewhere'},
    {'layout_mode': 'facecam', 'facecam_region': 'manual', 'facecam_x': .9, 'facecam_w': .3},
    {'layout_mode': 'facecam', 'facecam_region': 'manual', 'facecam_h': 0},
    {'layout_mode': 'facecam', 'facecam_x': float('nan')},
    {'layout_mode': 'facecam', 'unknown': True},
])
def test_project_rejects_invalid_values(invalid):
    with pytest.raises((ValueError, TypeError)):
        checked_layout_settings(invalid)


def test_manual_and_corner_rois_are_inside_source():
    source = Path('/not-needed-for-manual-or-corner.mp4')
    for region in ('top-left', 'top-right', 'bottom-left', 'bottom-right'):
        x, y, w, h = facecam_roi(source, 0, 10, 1920, 1080, {'facecam_region': region})
        assert x >= 0 and y >= 0 and x + w <= 1920 and y + h <= 1080
    region = {'facecam_region': 'manual', 'facecam_x': .1, 'facecam_y': .1,
              'facecam_w': .25, 'facecam_h': .3}
    x, y, w, h = facecam_roi(source, 0, 10, 1920, 1080, region)
    assert x == 192 and y == 108 and w == 480 and h == 324


def test_filter_has_two_views_from_same_video():
    graph = build_filter((0, 0, 400, 300))
    assert '[0:v]split=2' in graph
    assert 'vstack=inputs=2' in graph
    assert '1080:720' in graph
    assert '1080:1200' in graph


def test_render_without_optional_opencv(tmp_path):
    source = tmp_path / 'source.mp4'
    output = tmp_path / 'short.mp4'
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                    '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=15',
                    '-f', 'lavfi', '-i', 'sine=frequency=440',
                    '-t', '1.1', '-c:v', 'mpeg4', '-c:a', 'aac', str(source)],
                   check=True)
    from app.streamer_layout import render_facecam
    render_facecam(source, 0, 1.0, {'facecam_region': 'top-left'}, None, output, 640, 360)
    assert output.is_file() and output.stat().st_size > 1000
    dimensions = subprocess.check_output([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height', '-of', 'csv=s=x:p=0', str(output)
    ], text=True).strip()
    assert dimensions == '1080x1920'
