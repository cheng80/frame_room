"""v2.34 adapter contracts; pixel fixtures are synthetic, not generated art."""
from pathlib import Path
import math

import numpy as np
from PIL import Image, ImageDraw
import pytest

from adapters.spritegen import video_processing as vp
from test_video_processing import make_clip


def test_game_walk_default_keeps_eight_original_samples_and_cycle_time(tmp_path, monkeypatch):
    clip = make_clip(tmp_path / 'source', count=37)
    monkeypatch.setattr(vp, 'rife_interpolator', lambda: pytest.fail('eight original samples need no RIFE'))
    result = vp.process_clip(clip, tmp_path / 'work', {'loopMode': 'manual', 'startFrame': 0, 'endFrame': 24})
    assert [f['sourceFrameIndex'] for f in result['frames']] == list(range(0, 24, 3))
    assert [f['durationMs'] for f in result['frames']] == [125] * 8
    assert result['selection']['durationMs'] == 1000
    assert result['version'] == vp.VERSION
    assert len(result['source']['timesMs']) == 38
    assert result['source']['streamIndex'] == 0
    for f in result['frames']:
        assert not f['interpolated']
        assert Path(f['keyedPath']).read_bytes() == Path(f['originalKeyedPath']).read_bytes()
    assert result['selection']['retake']['automaticGeneration'] is False
    assert 'suspects' in result['selection']['period']


@pytest.mark.parametrize('between,expected_made', [('auto', 0), ('off', 0), ('on', 4)])
def test_rejected_resample_uses_actual_nearest_parent_after_rotation_and_repair(tmp_path, monkeypatch, between, expected_made):
    paths = []
    for i in range(4):
        image = Image.new('RGBA', (32, 40))
        ImageDraw.Draw(image).rectangle((8, 5, 22, 37), fill=(220, 180 + i, 150, 255))
        path = tmp_path / f'{i}.png'; image.save(path); paths.append(path)
    class DarkInterpolator:
        def __call__(self, a, b, t):
            if between == 'off': pytest.fail('nearest-only must never interpolate')
            out = a.copy();out.paste((0, 0, 0, 255), (8, 5, 23, 38));return out
        def describe(self): return {'kind': 'synthetic-dark-test-double'}
    monkeypatch.setattr(vp, 'rife_interpolator', DarkInterpolator)
    selection = {'loop': True, 'startFrame': 0, 'endFrame': 4, 'repair': {'sourceFrameIndices': [1]}}
    options = {'targetFrameCount': 8, 'between': between, 'direction': 'side', 'facing': 'right',
               'startFoot': 'auto', 'startIndex': 1}
    frames, report = vp._align_selected_cycle(paths, paths, paths, {'timesMs': [0, 100, 200, 300, 400]}, selection, options, tmp_path)
    assert report['made_by_rife'] == expected_made
    assert sum(f['durationMs'] for f in frames) == 400
    assert frames[0]['processing']['sampleIndex'] == 1
    if between != 'on':
        assert report['nearest_at'] == [1, 3, 5, 7]
        assert frames[0]['sourceFrameIndex'] == 1
        assert frames[0]['sourceTimeMs'] == 100
        assert frames[0]['interpolated'] is True  # prior jump repair remains identified
        assert frames[0]['interpolation']['method'] == 'rife-jump-repair'
        assert frames[6]['sourceFrameIndex'] == 0  # wrap nearest
        assert frames[6]['sourceTimeMs'] == 0
        assert frames[6]['interpolated'] is False
        for f in frames:
            with Image.open(f['keyedPath']) as actual, Image.open(paths[f['sourceFrameIndex']]) as expected:
                assert actual.tobytes() == expected.tobytes()
        if between == 'auto':
            assert all(item['faults'] for item in report['smear'])


def test_size_hold_padding_maps_first_anchor_and_keeps_top_pixels():
    images = []
    for h in (38, 34, 30, 26):
        image = Image.new('RGBA', (32, 40));ImageDraw.Draw(image).rectangle((8, 39-h, 24, 38), fill=(180, 90, 70, 255));images.append(image)
    measured = {'height': np.array([38., 34., 30., 26.]), 'foot_x': np.full(4, 16.), 'foot_y': np.full(4, 39.)}
    out, proof = vp._scale_correction(images, measured)
    for index, frame in enumerate(out):
        transform = proof['frames'][index]['sourceTransform']
        assert transform['scaleY'] == pytest.approx(38 / measured['height'][index])
        assert transform['offsetY'] == pytest.approx(39 * (1 - transform['scaleY']) + proof['paddingLTRB'][1])
        assert frame.size == out[0].size
        assert frame.getchannel('A').getbbox() is not None
    assert proof['resampler'] == 'separate-color-alpha-affine'


def test_manual_output_phase_rotates_time_with_frames_and_rejects_out_of_range(tmp_path):
    clip = make_clip(tmp_path / 'source', count=37)
    settings = {'loopMode': 'manual', 'startFrame': 0, 'endFrame': 25, 'maxFrames': 8}
    base = vp.process_clip(clip, tmp_path / 'work', settings)
    rotated = vp.process_clip(clip, tmp_path / 'work', {**settings, 'startIndex': 3})
    pairs = lambda r: [(f['sourceFrameIndex'], f['durationMs']) for f in r['frames']]
    assert pairs(rotated) == pairs(base)[3:] + pairs(base)[:3]
    assert rotated['selection']['durationMs'] == base['selection']['durationMs']
    with pytest.raises(vp.VideoProcessingError) as error:
        vp.process_clip(clip, tmp_path / 'work', {**settings, 'startIndex': 8})
    assert error.value.code == 'VIDEO_INVALID_PHASE'


def test_non_biped_keeps_foot_identity_unconfirmed():
    images=[]
    for i in range(8):
        image=Image.new('RGBA',(40,50));ImageDraw.Draw(image).rectangle((10,10+i%2,30,43),fill=(170,80,50,255));images.append(image)
    strike=vp._foot_strike(images,{'direction':'side','facing':'right','startFoot':'right','bodyPlan':'quadruped'})
    assert strike['start_foot'] is None and strike['start_foot_source'] is None
    assert 'not biped' in strike['foot_why']
