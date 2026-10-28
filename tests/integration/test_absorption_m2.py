"""M2 policy and disposable interpolation cache boundaries; no remote models."""
import concurrent.futures
import json
import os
from pathlib import Path
import time

import pytest
from PIL import Image

from adapters.spritegen import video_processing as vp
from adapters.spritegen.video_interpolation import Session
from services.api import store as s
from services.worker.video_task import execute_video
from test_video_jobs import client, media, new, upload, queue


@pytest.mark.parametrize('change', ['missing', 'legacy', 'future', 'digest', 'unknown'])
def test_recipe_refuses_retry_and_worker_before_any_processing(client, media, tmp_path, monkeypatch, change):
    p, v = upload(client, new(client), media)
    response = queue(client, p, params={'videoId': v['videoId'], 'frameSelection': 'uniform'})
    job = s.get_job(response.json()['jobId'])
    assert job['processingPolicy'] == vp.processing_policy()
    if change == 'missing': job.pop('processingPolicy')
    elif change in ('legacy', 'future'): job['processingPolicy']['version'] = change
    elif change == 'digest': job['processingPolicy']['engineDigest'] = '0' * 64
    else: job['request']['params']['cachePath'] = '/outside'
    job['status'] = 'interrupted'
    with s.transaction() as c: s.write_job(c, job)
    monkeypatch.setattr(vp, 'process_clip', lambda *a, **k: pytest.fail('incompatible recipe processed'))
    retried = client.post('/v1/jobs/' + job['jobId'] + '/retry', json={'idempotencyKey': 'retry'})
    assert retried.status_code in (409, 422)
    with pytest.raises(s.AppError): execute_video(job, tmp_path / 'output')
    assert not (tmp_path / 'output').exists()


class StandIn:
    def __init__(self): self.calls = 0; self.model = 'one'
    def identity(self): return self.model
    def __call__(self, a, b, t): self.calls += 1; return a.copy()
    def describe(self): return {'model': self.model, 'tta': ''}


def inputs():
    return Image.new('RGBA', (8, 8), (255, 10, 20, 255)), Image.new('RGBA', (8, 8), (10, 255, 20, 255))


def test_cache_hit_corrupt_missing_changed_identity_and_inputs(tmp_path, monkeypatch):
    fake = StandIn(); monkeypatch.setattr(vp, 'rife_interpolator', lambda: fake)
    session = Session(tmp_path)
    a, b = inputs()
    expected = session(a, b, .5).tobytes()
    assert session(a, b, .5).tobytes() == expected and fake.calls == 1
    cached = next(session.directory.glob('*.png')); cached.write_bytes(b'partial')
    assert session(a, b, .5).tobytes() == expected and fake.calls == 2
    cached.unlink()
    session(a, b, .5); fake.model = 'two'; session(a, b, .5)
    session(b, a, .5); session(a, b, .25)
    a.putpixel((0, 0), (1, 2, 3, 4)); session(a, b, .25)
    assert fake.calls == 7
    assert session.describe()['cache']['hits'] == 1
    assert session.describe()['cache']['unreadable'] == 1


@pytest.mark.parametrize('where', ['parent', 'directory', 'entry'])
def test_cache_symlink_boundary_preserves_external_sentinel(tmp_path, monkeypatch, where):
    external = tmp_path / 'external'; external.mkdir(); sentinel = external / 'sentinel'; sentinel.write_bytes(b'original')
    project = tmp_path / 'project'; project.mkdir()
    fake = StandIn(); monkeypatch.setattr(vp, 'rife_interpolator', lambda: fake)
    session = Session(project); a, b = inputs()
    if where == 'parent': (project / '.cache').symlink_to(external, target_is_directory=True)
    elif where == 'directory':
        (project / '.cache').mkdir(); session.directory.symlink_to(external, target_is_directory=True)
    else:
        session(a, b, .5); entry = next(session.directory.glob('*.png')); entry.unlink(); entry.symlink_to(sentinel)
    if where == 'entry':
        session(a, b, .5)
        assert not entry.is_symlink() and fake.calls == 2
    else:
        with pytest.raises(vp.VideoProcessingError, match='심볼릭'): session(a, b, .5)
    assert sentinel.read_bytes() == b'original'


def test_concurrent_cache_publish_has_whole_frames_only(tmp_path):
    rife = vp._engine('video.rife'); a, b = inputs(); fake = StandIn()
    def make(_): return rife.Cache(tmp_path).frame(fake, a, b, .5).tobytes()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        assert set(executor.map(make, range(8))) == {a.tobytes()}
    assert len(list(tmp_path.glob('*.png'))) == 1 and not list(tmp_path.glob('*.tmp'))


def test_cache_hit_still_obeys_cancellation_and_budget(tmp_path, monkeypatch):
    fake = StandIn(); monkeypatch.setattr(vp, 'rife_interpolator', lambda: fake)
    a, b = inputs(); session = Session(tmp_path); session(a, b, .5)
    session.check = lambda: (_ for _ in ()).throw(s.AppError('CANCELED', 'synthetic cancellation'))
    with pytest.raises(s.AppError, match='cancellation'): session(a, b, .5)
    session.check = lambda: None; session.deadline = time.monotonic() - 1
    with pytest.raises(vp._engine('video.rife').RifeUnavailable, match='budget'): session(a, b, .5)
    assert fake.calls == 1


def test_real_subprocess_cancel_kills_local_binary(tmp_path):
    rife = vp._engine('video.rife'); a, b = inputs()
    binary = tmp_path / 'slow'; binary.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep(10)\n'); binary.chmod(0o700)
    checks = 0
    def cancel():
        nonlocal checks
        checks += 1
        if checks > 2: raise s.AppError('CANCELED', 'synthetic cancellation')
    token = rife.RUN_CONTROL.set((time.monotonic() + 2, cancel))
    started = time.monotonic()
    try:
        with pytest.raises(s.AppError): rife._call(binary, tmp_path, a, b, .5, tmp_path)
    finally: rife.RUN_CONTROL.reset(token)
    assert time.monotonic() - started < 2


@pytest.mark.parametrize('body', ['quadruped', 'legless', 'reference'])
def test_non_biped_crossings_never_assert_two_steps(body):
    reading = vp._step_reading([inputs()[0]] * 16, {'bodyPlan': body})
    assert reading.judge(0, 8)['verdict'] == 'uncertain'


def test_repair_lineage_keeps_ghost_replacement_flow_and_easing_sources():
    record = {'rounds': [
        {'why': 'ghost', 'replaced': 1, 'taken': {'source': 2}},
        {'why': 'flow', 'replaced': [3], 'neighbours': [2, 4], 'made': [{'frames': [3], 't': .5}]},
        {'why': 'ease', 'replaced': [3], 'made': [{'frames': [3], 'from': [1, 4], 't': .75}]},
    ]}
    proof = vp._repair_lineage(record, 10, 8)
    assert proof['11'] == {'method': 'ghost-source-replacement', 'sourceFrameIndices': [12], 'fraction': 0.0}
    assert proof['13']['sourceFrameIndices'] == [11, 14] and proof['13']['fraction'] == .75


def test_cache_parent_replaced_during_interpolation_never_writes_outside(tmp_path, monkeypatch):
    project = tmp_path / 'project'; project.mkdir()
    external = tmp_path / 'external'; external.mkdir()
    sentinel = external / 'sentinel'; sentinel.write_bytes(b'original')
    class Replacing(StandIn):
        def __call__(self, a, b, t):
            (project / '.cache').rename(project / '.cache-old')
            (project / '.cache').symlink_to(external, target_is_directory=True)
            return a.copy()
    monkeypatch.setattr(vp, 'rife_interpolator', Replacing)
    with pytest.raises(vp.VideoProcessingError, match='심볼릭'):
        Session(project)(*inputs(), .5)
    assert list(external.iterdir()) == [sentinel] and sentinel.read_bytes() == b'original'


def test_cache_hit_runs_current_align_quality_gate(tmp_path, monkeypatch):
    from adapters.spritegen import video_interpolation
    fake = StandIn(); monkeypatch.setattr(vp, 'rife_interpolator', lambda: fake)
    session = Session(tmp_path); a, b = inputs(); frames = [a, b, a, b]
    align = vp._engine('video.align')
    align.resample(frames, 8, session, between='auto')
    calls = fake.calls
    measured = []
    original = align.faults
    monkeypatch.setattr(align, 'faults', lambda value: measured.append(value) or ['synthetic-current-gate'])
    _, report = align.resample(frames, 8, session, between='auto')
    assert fake.calls == calls and session.describe()['cache']['hits'] > 0
    assert measured and report['nearest_at'] == [1, 3, 5, 7]


def test_binary_absolute_budget_and_cache_write_failure_keep_originals(tmp_path, monkeypatch):
    rife = vp._engine('video.rife'); a, b = inputs()
    binary = tmp_path / 'slow'; binary.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep(10)\n'); binary.chmod(0o700)
    token = rife.RUN_CONTROL.set((time.monotonic() + .15, lambda: None))
    try:
        with pytest.raises(rife.RifeUnavailable, match='budget'): rife._call(binary, tmp_path, a, b, .5, tmp_path)
    finally: rife.RUN_CONTROL.reset(token)
    cache = rife.Cache(tmp_path / 'cache'); fake = StandIn()
    monkeypatch.setattr(rife.os, 'replace', lambda *a, **k: (_ for _ in ()).throw(OSError('synthetic disk full')))
    assert cache.frame(fake, a, b, .5).tobytes() == a.tobytes()
    assert cache.not_kept == 1 and not list(cache.directory.iterdir())
