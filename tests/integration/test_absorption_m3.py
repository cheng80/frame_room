"""Synthetic contract drawings and an actual local MP4; no generated/provider imagery."""
import copy
from contextlib import nullcontext
import io
import json
import shutil
import subprocess
import sys
import sqlite3

import pytest
from PIL import Image, ImageDraw

from adapters.spritegen import clip_comparison as cc
from alignment.pipeline import render_occurrence
from services.api import store as s, videos
from test_clip_tools import client, queue, run, artifact, make_project, params
from services.worker.task import execute
from services.worker.main import publish


def request(p, clip=None, **extra):
    clip = clip or p['clips'][0]
    return dict(clipId=clip['clipId'], clipRevisionId=clip['clipRevisionId'], **extra)


def native_project(client, tmp_path, *, existing=None, phase=0, frame_count=12):
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = existing or client.post('/v1/projects', json={'name': 'M3 합성 source 복원', 'parentDirectory': str(tmp_path)}).json()
    originals = []
    for i in range(12):
        image = Image.new('RGBA', (64, 80)); d = ImageDraw.Draw(image)
        y = [0, 1, 2, 1, 0, -1][i % 6]
        d.rectangle((16, 10+y, 46, 57+y), fill=(210, 160, 110), outline=(20, 20, 20), width=3)
        d.rectangle((15+i%6, 58, 26+i%6, 74), fill=(45, 35, 25))
        d.rectangle((39-i%6, 58, 48-i%6, 74), fill=(65, 45, 25))
        d.line((15, 14+y, 15, 52+y), fill=(30, 30, 30, 170))
        originals.append(image)
    source_dir = tmp_path / 'synthetic-keyed'; source_dir.mkdir(parents=True)
    for i, image in enumerate(originals): image.save(source_dir / f'{i:03d}.png')
    mp4 = tmp_path / 'synthetic.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-framerate', '12', '-i', str(source_dir / '%03d.png'),
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(mp4)], check=True)
    damaged = [im.copy() for im in originals]
    for index in (2, 8):
        for y in range(8, 58):
            for x in range(64):
                if damaged[index].getpixel((x, y))[:3] in ((20, 20, 20), (30, 30, 30)):
                    damaged[index].putpixel((x, y), (210, 160, 110, 255))
    with s.project_scope(p['projectId']), nullcontext(None) as db:
        video = videos.register(mp4.read_bytes(), 'synthetic.mp4', {'kind': 'synthetic-contract-fixture'}, c=db)
        assets, frames, alignments, slots = [], [], {}, []
        gid, gr = s.uid(), s.uid()
        for i, image in enumerate(damaged):
            data = io.BytesIO(); image.save(data, format='PNG')
            a = s.register_asset(data.getvalue(), f'damaged-{i}.png', 'derived', {'kind': 'synthetic-fixture'}, c=db)
            assets.append(a); fid = s.uid()
            frames.append(dict(frameId=s.uid(), frameVersionId=fid, rawAssetId=a['assetId'], imageAssetId=a['assetId'],
                sourceRect={'x': 0, 'y': 0, 'width': 64, 'height': 80}, sourceToFrameTransform={'scaleX': 1, 'scaleY': 1, 'offsetX': 0, 'offsetY': 0},
                extractionVersion='synthetic-fixture', nativeScaleGroupId=gid, review='pending', hidden=False))
            alignments[fid] = dict(frameVersionId=fid, groupRevisionId=gr, sourceAnchor={'x': 0, 'y': 0}, anchorSpace='crop',
                method='manual', contactMode='grounded', authoredOffsetPx={'x': 0, 'y': 0}, approval='pending')
            slots.append(dict(occurrenceId=s.uid(), frameVersionId=fid, durationMs=80+i, timingMode='explicit', transform={'dx': 0, 'dy': 0}, pixelEdits=[]))
        group = dict(alignmentGroupId=gid, groupRevisionId=gr, frameVersionIds=[f['frameVersionId'] for f in frames],
            mode='preserve-source-scale', sharedScale=1, cell={'width': 64, 'height': 80, 'edge': 0},
            targetAnchor={'x': 0, 'y': 0}, bodyMeasurement=None, resampler='nearest', roundingVersion='js-round-v1')
        clip = dict(clipId=s.uid(), clipRevisionId=s.uid(), name='합성 복원 대상', stateId='walk', facing='right', direction='side',
                    referenceRevisionId=None, loop=True, endBehavior='hold-last', defaultFps=12, occurrences=slots, review='pending')
        if phase: clip['occurrences'] = slots[phase:] + slots[:phase]
        clip['occurrences'] = clip['occurrences'][:frame_count]
        p.update(assets=p['assets'] + assets, frames=p['frames'] + frames, clips=p['clips'] + [clip], alignmentGroups=p['alignmentGroups'] + [group], alignments={**p['alignments'], **alignments}, videos=p['videos'] + [video])
        rendered = [render_occurrence(p, clip, slot, s.asset_path, include_outline=False) for slot in clip['occurrences']]
        normalization = dict(sourceRect={'x': 0, 'y': 0, 'width': 64, 'height': 80}, width=64, height=80,
            anchor={'x': 0, 'y': 0}, sourceToFrameTransform={'scaleX': 1, 'scaleY': 1, 'offsetX': 0, 'offsetY': 0})
        items = [dict(originalKeyedPath=str(source_dir / f'{i:03d}.png'), keyedPath=str(source_dir / f'{i:03d}.png'),
                      sourceFrameIndex=i, sourceTimeMs=i*1000/12) for i in range(12)]
        if phase: items = items[phase:] + items[:phase]
        items = items[:frame_count]
        cc.capture_video(p, clip, [im for im, _ in rendered], rendered, items, assets, video, normalization,
                         {'mode': 'rgba', 'cellWidth': 64, 'cellHeight': 80}, {'options': {'key': 'green'}}, s.project_folder(p['projectId']))
        clip['comparisonEvidence']['slotIds'] = [o['occurrenceId'] for o in clip['occurrences']]
        p['assets'] = list({a['assetId']: a for a in p['assets'] + assets}.values())
        with s.transaction() as c: s.write_project(c, p, '합성 증거 준비')
    return s.get_project(p['projectId'])


def test_native_restoration_repeated_save_outputs_backup_and_cacheless_reopen(client, tmp_path):
    p = native_project(client, tmp_path)
    frozen = copy.deepcopy(p['clips'][0]); ids = {key: frozen['comparisonEvidence'][key] for key in ('source', 'origin')}
    previews = []
    for _ in range(2):
        selected = p['clips'][-1]
        preview = run(queue(client, p, 'preview_restore', request(p, selected)))
        report = preview['result']['report']; previews.append(preview)
        assert report['verdict'] == 'improved' and report['canApply'], report
        assert report['schema_version'] == 4 and report['comparison_schema'] == 6
        applied = run(queue(client, p, 'apply_follow', {'previewJobId': preview['jobId']}))
        p = s.get_project(p['projectId']); created = p['clips'][-1]
        assert created['clipId'] == applied['result']['clipId']
        for key in ids: assert created['comparisonEvidence'][key] == ids[key]
        assert [o['durationMs'] for o in created['occurrences']] == [80+i for i in range(12)]
        with s.project_scope(p['projectId']):
            for i, slot in enumerate(created['occurrences']):
                cell = render_occurrence(p, created, slot, s.asset_path, include_outline=False)[0]
                assert cell.tobytes() == Image.open(io.BytesIO(artifact(client, preview, f'after/{i:03d}.png'))).convert('RGBA').tobytes()
    assert p['clips'][0] == frozen
    assert p['clips'][-1]['comparisonEvidence']['applied'] == [2, 8]
    backup = run(client.post(f"/v1/projects/{p['projectId']}/backup", json={'savedRevision': p['revision']}))
    archive = artifact(client, backup, 'project-backup.zip')
    restored = run(client.post('/v1/projects/restore', files={'backupZip': ('m3.zip', archive, 'application/zip')}, data={'idempotencyKey': s.uid()}))
    q = s.get_project(restored['result']['projectId'])
    assert q['clips'][-1]['comparisonEvidence']['origin'] == ids['origin']
    # A restored project has assets/videos, without the source job or interpolation caches.
    with s.project_scope(q['projectId']):
        from adapters.spritegen.clip_tools import render_clip
        cells, durations, _ = render_clip(q, request(q, q['clips'][-1]), s.asset_path)
        evidence, _, _, _ = cc.read_evidence(q, q['clips'][-1], cells, durations)
        assert evidence['source'] == ids['source']
    preview = run(queue(client, q, 'preview_restore', request(q, q['clips'][-1])))
    assert preview['result']['report']['verdict'] == 'non_regressing'
    assert preview['result']['report']['canApply'] is False


@pytest.mark.parametrize('change', ['schema', 'policy', 'origin', 'time', 'sample', 'pixel-edit', 'crop', 'source-map', 'key', 'facing'])
def test_invalid_source_evidence_stays_unknown_without_overwriting(client, tmp_path, change):
    p = native_project(client, tmp_path); clip = p['clips'][0]; e = clip['comparisonEvidence']
    if change == 'schema': e['schemaVersion'] = 99
    elif change == 'policy': e['policy']['metric_version'] = 'future'
    elif change == 'origin': e['origin']['sha256'] = '0'*64
    elif change == 'time': clip['occurrences'][0]['durationMs'] += 1
    elif change == 'sample': clip['occurrences'].reverse()
    elif change == 'crop': p['frames'][0]['sourceRect']['x'] += 1
    elif change == 'source-map': p['frames'][0]['sourceFrameIndex'] = 999
    elif change == 'key': e['key'] = 'magenta'
    elif change == 'facing': e['facing'] = 'left'
    else: clip['occurrences'][0]['pixelEdits'] = [{'x': 30, 'y': 30, 'color': [255, 0, 0, 255]}]
    with s.transaction() as db: s.write_project(db, p, '잘못된 증거 fixture')
    p = s.get_project(p['projectId']); frozen = copy.deepcopy(p)
    preview = run(queue(client, p, 'preview_restore', request(p)))
    assert preview['result']['report']['verdict'] == 'unknown'
    assert queue(client, p, 'apply_follow', {'previewJobId': preview['jobId']}).status_code == 409
    assert s.get_project(p['projectId']) == frozen


def test_restoration_save_failure_retries_completed_bytes_without_execution(client, tmp_path, monkeypatch):
    p = native_project(client, tmp_path)
    preview = run(queue(client, p, 'preview_restore', request(p)))
    j = s.get_job(queue(client, p, 'apply_follow', {'previewJobId': preview['jobId']}).json()['jobId'])
    out = s.job_directory(j['jobId']) / j['attemptId'] / 'staging'; result = execute(j, out)
    result['publicationHashes'] = {name: s.digest((out / name).read_bytes()) for name in result['files']}
    s.atomic_bytes(out.parent / 'result.json', s.dumps({'ok': True, 'result': result}).encode())
    with monkeypatch.context() as patch:
        patch.setattr(s, 'write_project', lambda *a, **k: (_ for _ in ()).throw(OSError('synthetic publication failure')))
        with pytest.raises(OSError): publish(j, {'ok': True, 'result': copy.deepcopy(result)})
    assert s.get_project(p['projectId']) == p
    with s.transaction() as db:
        failed = s.get_job(j['jobId'], db); failed.update(status='failed', completedResult=True); s.write_job(db, failed)
    response = client.post(f"/v1/jobs/{j['jobId']}/retry", json={'idempotencyKey': 'store-complete-only'})
    assert response.status_code == 200, response.text
    retried = s.get_job(j['jobId']); assert retried['reuseResultAttemptId'] == j['attemptId']
    monkeypatch.setenv('SPRITE_DATA_DIR', str(s.DATA))
    code = "from services.worker import task; task.execute=lambda *a: (_ for _ in ()).throw(AssertionError('must reuse completed bytes')); task.main()"
    subprocess.run([sys.executable, '-c', code, j['jobId'], retried['attemptId']], check=True)
    payload = json.loads((s.job_directory(j['jobId']) / retried['attemptId'] / 'result.json').read_bytes())
    assert payload['ok']; publish(retried, payload)
    q = s.get_project(p['projectId']); assert len(q['clips']) == 2
    with sqlite3.connect(s.project_folder(q['projectId']) / 'project.sqlite3') as db:
        saved = json.loads(db.execute('SELECT snapshot FROM projects WHERE id=?', (q['projectId'],)).fetchone()[0])
    assert saved['clips'] == q['clips'] and saved['frames'] == q['frames']
    assert q['clips'][-1]['comparisonEvidence']['origin'] == p['clips'][0]['comparisonEvidence']['origin']
    reopened = client.post('/v1/project-folders/open', json={'path': str(s.project_folder(q['projectId']))})
    assert reopened.status_code == 200 and reopened.json()['clips'] == q['clips']


@pytest.mark.parametrize('field', ['origin', 'schema', 'policy', 'stale'])
def test_restore_preview_rechecks_origin_schema_policy_and_revision_on_save(client, tmp_path, field):
    p = native_project(client, tmp_path); preview = run(queue(client, p, 'preview_restore', request(p)))
    if field == 'origin':
        with s.project_scope(p['projectId']):
            record = p['clips'][0]['comparisonEvidence']['originCells'][0]
            s.asset_path(record['assetId']).write_bytes(b'changed-origin')
    elif field in ('schema', 'policy'):
        with s.transaction() as db:
            stored = s.get_job(preview['jobId'], db)
            if field == 'schema': stored['result']['report']['comparison']['schema_version'] = 1
            else: stored['result']['policy']['metric_version'] = 'same-sample-defects-v1'
            s.write_job(db, stored)
    else:
        with s.transaction() as db:
            p['characterName'] = '다른 저장'; s.write_project(db, p, 'stale preview fixture')
        p = s.get_project(p['projectId'])
    response = queue(client, p, 'apply_follow', {'previewJobId': preview['jobId']})
    assert response.status_code in (409, 424), response.text
    assert len(s.get_project(p['projectId'])['clips']) == 1


def test_legacy_comparison_and_read_on_mismatch_cannot_claim_improvement(client):
    p = make_project(client)
    restored = run(queue(client, p, 'preview_restore', request(p)))
    assert restored['result']['report']['verdict'] == 'unknown'
    compared = run(queue(client, p, 'compare_clips', request(p, candidateClipId=p['clips'][0]['clipId'], candidateClipRevisionId=p['clips'][0]['clipRevisionId'])))
    assert compared['result']['report']['metric_version'] == 'same-sample-defects-v1'
    assert compared['result']['report']['schema_version'] == 1
    assert compared['result']['report']['verdict'] == 'unknown'
    followed = run(queue(client, p, settings=params(p, readOn='0'*64)))
    assert followed['result']['report']['readOn']['relation'] == 'uncertain'
    assert queue(client, p, 'apply_follow', {'previewJobId': followed['jobId']}).status_code == 409


def test_general_comparison_requires_exact_clock_basis_and_distinguishes_regression():
    cells = [Image.new('RGBA', (8, 8), (90+i, 60, 30, 255)) for i in range(4)]
    durations = [37, 83, 61, 119]; basis = {'samples': [0, 2, 4, 6], 'crop': [0, 0, 8, 8]}
    report = cc.compare_cells(cells, cells, durations, durations, basis, basis)
    assert report['verdict'] == 'non_regressing'
    assert cc.compare_cells(cells, cells, durations, durations[::-1], basis, basis)['verdict'] == 'unknown'
    assert cc.compare_cells(cells, cells, durations, durations, basis, {'crop': [1, 0, 8, 8]})['verdict'] == 'unknown'
    after = [im.copy() for im in cells]; after[-1] = Image.new('RGBA', (8, 8), (255, 255, 255, 255))
    assert cc.compare_cells(cells, after, durations, durations, basis, basis)['verdict'] == 'regressed'


def test_read_on_transports_only_exact_original_samples_and_checks_hash(client, tmp_path):
    p = native_project(client, tmp_path / 'origin')
    p = native_project(client, tmp_path / 'rotated', existing=p, phase=3)
    source, current = p['clips'][0], p['clips'][-1]
    settings = dict(clipId=current['clipId'], clipRevisionId=current['clipRevisionId'], region=[32, 36, 16, 18], gain=.5,
                    readOnClipId=source['clipId'], readOnClipRevisionId=source['clipRevisionId'])
    preview = run(queue(client, p, settings=settings))
    report = preview['result']['report']
    assert report['readOn']['relation'] == 'transported', report
    assert report['readOn']['sourceCells'] == [*range(3, 12), *range(3)]
    assert report['canApply'] is True
    wrong = run(queue(client, p, settings={**settings, 'readOn': '0'*64}))
    assert wrong['result']['report']['readOn']['relation'] == 'uncertain'
    assert queue(client, p, 'apply_follow', {'previewJobId': wrong['jobId']}).status_code == 409
    saved = run(queue(client, p, 'apply_follow', {'previewJobId': preview['jobId']}))
    q = s.get_project(p['projectId']); made = q['clips'][-1]
    assert made['clipId'] == saved['result']['clipId']
    assert made['comparisonEvidence']['source'] == current['comparisonEvidence']['source']
    assert made['comparisonEvidence']['origin'] == current['comparisonEvidence']['origin']


def test_legacy_source_proof_is_independent_of_unsupported_origin(client, tmp_path):
    p = native_project(client, tmp_path); clip = p['clips'][0]; clip.pop('comparisonEvidence')
    with s.transaction() as db: s.write_project(db, p, 'legacy source fixture')
    p = s.get_project(p['projectId'])
    response = queue(client, p, 'preview_restore', request(p)); job = s.get_job(response.json()['jobId'])
    job['operation'] = 'process_video'; job['result'] = {'clipId': clip['clipId'], 'videoId': p['videos'][0]['videoId']}; job['published'] = True
    with s.transaction() as db:
        db.execute('UPDATE jobs SET operation=? WHERE id=?', ('process_video', job['jobId']))
        s.write_job(db, job)
    base = s.artifact_directory(job['jobId']) / job['attemptId'] / 'processing'; manifest = []
    for lane in ('raw', 'keyed'):
        folder = base / 'extractions' / 'proof' / 'attempt-1' / lane; folder.mkdir(parents=True)
        for i in range(12):
            path = folder / f'{i:03d}.png'; path.write_bytes((tmp_path / 'synthetic-keyed' / f'{i:03d}.png').read_bytes())
            manifest.append({'file': path.relative_to(base).as_posix(), 'sha256': s.digest(path.read_bytes())})
    complete = base / 'extractions' / 'proof' / 'complete.json'
    complete.write_text(json.dumps({'options': {'sourceSha256': p['videos'][0]['sha256']}, 'manifest': manifest}))
    with s.project_scope(p['projectId']):
        status = cc.source_status(p, clip)
        assert status['source'] == 'verified-full-extraction' and status['origin'] == 'unsupported-legacy', status
        (base / manifest[0]['file']).write_bytes(b'changed-keyed-or-raw')
        assert cc.source_status(p, clip)['source'] == 'unknown'


def rewrite_preview_metadata(job_id, mutate):
    """Even coherently corrupted DB/report bytes cannot replace the actual source identities."""
    with s.transaction() as db:
        job = s.get_job(job_id, db); result = job['result']; mutate(result)
        data = s.dumps({k: v for k, v in result.items() if k not in ('fileHashes', 'publicationHashes', 'files')}).encode()
        path = s.artifact_directory(job_id) / job['attemptId'] / 'report.json'; path.write_bytes(data)
        sha = s.digest(data)
        next(r for r in result['fileHashes'] if r['name'] == 'report.json')['sha256'] = sha
        next(r for r in job['artifacts'] if r['name'] == 'report.json')['sha256'] = sha
        db.execute('UPDATE artifacts SET sha256=? WHERE job_id=? AND name=?', (sha, job_id, 'report.json'))
        s.write_job(db, job)


@pytest.mark.parametrize('phase', ['enqueue', 'execute', 'publish'])
@pytest.mark.parametrize('field', ['source', 'origin', 'baseline', 'candidate'])
def test_restoration_binds_all_report_identities_to_actual_pixels_at_every_boundary(client, tmp_path, phase, field):
    p = native_project(client, tmp_path); preview = run(queue(client, p, 'preview_restore', request(p)))
    if phase != 'enqueue':
        job = s.get_job(queue(client, p, 'apply_follow', {'previewJobId': preview['jobId']}).json()['jobId'])
        out = s.job_directory(job['jobId']) / job['attemptId'] / 'staging'
        if phase == 'publish': result = execute(job, out)
    def corrupt(result):
        for row in (result['report'], result['report']['comparison']):
            row[field]['id'] = row[field]['sha256'] = '0' * 64
    rewrite_preview_metadata(preview['jobId'], corrupt)
    if phase == 'enqueue':
        response = queue(client, p, 'apply_follow', {'previewJobId': preview['jobId']})
        assert response.status_code == 424, response.text
    else:
        with pytest.raises(s.AppError):
            if phase == 'execute': execute(job, out)
            else: publish(job, {'ok': True, 'result': result})
    assert s.get_project(p['projectId']) == p


@pytest.mark.parametrize('field', ['source', 'origin', 'baseline', 'candidate'])
def test_general_comparison_binds_report_identities_before_saving(client, tmp_path, field):
    p = native_project(client, tmp_path); clip = p['clips'][0]
    preview = run(queue(client, p, 'compare_clips', request(p, candidateClipId=clip['clipId'], candidateClipRevisionId=clip['clipRevisionId'])))
    assert preview['result']['report']['canApply']
    rewrite_preview_metadata(preview['jobId'], lambda result: result['report'][field].update(id='0'*64, sha256='0'*64))
    response = queue(client, p, 'apply_follow', {'previewJobId': preview['jobId']})
    assert response.status_code == 424 and s.get_project(p['projectId']) == p


@pytest.mark.parametrize('field', ['origin', 'candidate'])
def test_nested_comparison_cannot_disagree_with_outer_restoration(client, tmp_path, field):
    p = native_project(client, tmp_path); preview = run(queue(client, p, 'preview_restore', request(p)))
    rewrite_preview_metadata(preview['jobId'], lambda result: result['report']['comparison'][field].update(id='0'*64, sha256='0'*64))
    assert queue(client, p, 'apply_follow', {'previewJobId': preview['jobId']}).status_code == 424
    assert s.get_project(p['projectId']) == p


def test_preview_source_coordinates_must_equal_rendered_baseline(client):
    p = make_project(client); preview = run(queue(client, p))
    def corrupt(result): result['source']['anchors'][0]['x'] += 1
    rewrite_preview_metadata(preview['jobId'], corrupt)
    assert queue(client, p, 'apply_follow', {'previewJobId': preview['jobId']}).status_code == 424
    assert s.get_project(p['projectId']) == p


def test_no_change_cannot_be_promoted_by_mutating_approved_metadata(client, tmp_path):
    p = native_project(client, tmp_path)
    for _ in range(2):
        preview = run(queue(client, p, 'preview_restore', request(p, p['clips'][-1])))
        run(queue(client, p, 'apply_follow', {'previewJobId': preview['jobId']})); p = s.get_project(p['projectId'])
    preview = run(queue(client, p, 'preview_restore', request(p, p['clips'][-1])))
    assert preview['result']['report']['verdict'] == 'non_regressing' and not preview['result']['report']['canApply']
    original = copy.deepcopy(preview['result'])
    for field in ('verdict', 'axes', 'settings', 'source'):
        with s.transaction() as db:
            stored = s.get_job(preview['jobId'], db); stored['result'] = copy.deepcopy(original)
            report = stored['result']['report']; report.update(verdict='improved', canApply=True)
            report['comparison']['verdict'] = 'improved'
            if field == 'axes': report['axes'] = {'pretend': {'status': 'improved'}}
            elif field == 'settings': stored['result']['settings']['unapproved'] = True
            elif field == 'source': stored['result']['source']['stripSha256'] = '0'*64
            s.write_job(db, stored)
        assert queue(client, p, 'apply_follow', {'previewJobId': preview['jobId']}).status_code == 424
        assert s.get_project(p['projectId']) == p
    with s.transaction() as db:
        stored = s.get_job(preview['jobId'], db); stored['result'] = copy.deepcopy(original); s.write_job(db, stored)
    def promote(result):
        result['report'].update(verdict='improved', canApply=True)
        result['report']['comparison']['verdict'] = 'improved'
    rewrite_preview_metadata(preview['jobId'], promote)
    assert queue(client, p, 'apply_follow', {'previewJobId': preview['jobId']}).status_code == 424
    assert s.get_project(p['projectId']) == p


def test_zero_gain_follow_preserves_verified_source_for_comparison_and_restoration(client, tmp_path):
    p = native_project(client, tmp_path); original = p['clips'][0]
    preview = run(queue(client, p, settings={**request(p), 'region': [32, 36, 16, 18], 'gain': 0}))
    assert preview['result']['report']['unchanged'] is True
    applied = run(queue(client, p, 'apply_follow', {'previewJobId': preview['jobId']})); p = s.get_project(p['projectId'])
    copied = next(c for c in p['clips'] if c['clipId'] == applied['result']['clipId'])
    for field in ('source', 'origin', 'applied', 'unsupported'):
        assert copied['comparisonEvidence'][field] == original['comparisonEvidence'][field]
    compared = run(queue(client, p, 'compare_clips', request(p, original, candidateClipId=copied['clipId'], candidateClipRevisionId=copied['clipRevisionId'])))
    assert compared['result']['report']['verdict'] == 'non_regressing'
    restored = run(queue(client, p, 'preview_restore', request(p, copied)))
    assert restored['result']['report']['verdict'] == 'improved' and restored['result']['report']['canApply']
    assert restored['result']['report']['origin'] == original['comparisonEvidence']['origin']


@pytest.mark.parametrize('field', ['geometry', 'sample'])
def test_zero_gain_follow_cannot_revalidate_an_invalid_parent_receipt(client, tmp_path, field):
    p = native_project(client, tmp_path); clip = p['clips'][0]
    if field == 'geometry': clip['comparisonEvidence']['geometry'] = '0'*64
    else: p['frames'][0]['sourceFrameIndex'] = 999
    with s.transaction() as db: s.write_project(db, p, '무효 부모 증거 fixture')
    p = s.get_project(p['projectId'])
    preview = run(queue(client, p, settings={**request(p), 'region': [32, 36, 16, 18], 'gain': 0}))
    applied = run(queue(client, p, 'apply_follow', {'previewJobId': preview['jobId']})); p = s.get_project(p['projectId'])
    copied = next(c for c in p['clips'] if c['clipId'] == applied['result']['clipId'])
    assert copied['comparisonEvidence']['unsupported'] == 'parent-source-evidence-unverified'
    compared = run(queue(client, p, 'compare_clips', request(p, copied, candidateClipId=copied['clipId'], candidateClipRevisionId=copied['clipRevisionId'])))
    restored = run(queue(client, p, 'preview_restore', request(p, copied)))
    assert compared['result']['report']['verdict'] == restored['result']['report']['verdict'] == 'unknown'


@pytest.mark.parametrize('transported', [False, True])
def test_nonzero_follow_comparison_save_and_cacheless_backup_preserve_provenance(client, tmp_path, transported):
    p = native_project(client, tmp_path / 'origin')
    if transported: p = native_project(client, tmp_path / 'rotated', existing=p, phase=3)
    original = p['clips'][-1]; source = p['clips'][0]
    settings = {**request(p, original), 'region': [18, 36, 12, 25], 'gain': 3}
    if transported: settings.update(readOnClipId=source['clipId'], readOnClipRevisionId=source['clipRevisionId'])
    preview = run(queue(client, p, settings=settings))
    assert not preview['result']['report']['unchanged']
    run(queue(client, p, 'apply_follow', {'previewJobId': preview['jobId']})); p = s.get_project(p['projectId'])
    followed = p['clips'][-1]
    assert followed['comparisonEvidence']['unsupported'] == 'follow-source-warp-unverified'
    for key in ('source', 'origin'): assert followed['comparisonEvidence'][key] == original['comparisonEvidence'][key]
    # Real warped pixels are measured against their actual same-sample parent, in both directions.
    reports = []
    for a, b in ((original, followed), (followed, original)):
        compared = run(queue(client, p, 'compare_clips', request(p, a, candidateClipId=b['clipId'], candidateClipRevisionId=b['clipRevisionId'])))
        report = compared['result']['report']; reports.append(report)
        assert report['verdict'] in ('improved', 'non_regressing', 'regressed'), report
        assert report['axes'] and report['metric_version'] == 'same-sample-defects-v1'
    assert 'regressed' in [r['verdict'] for r in reports]
    # Saving the selected warp itself keeps its derivation proof, with a new clip/group/slot identity.
    selected = run(queue(client, p, 'compare_clips', request(p, followed, candidateClipId=followed['clipId'], candidateClipRevisionId=followed['clipRevisionId'])))
    assert selected['result']['report']['verdict'] == 'non_regressing'
    applied = run(queue(client, p, 'apply_follow', {'previewJobId': selected['jobId']})); p = s.get_project(p['projectId'])
    clone = p['clips'][-1]
    assert clone['clipId'] == applied['result']['clipId']
    assert clone['comparisonEvidence']['followProof'] == followed['comparisonEvidence']['followProof']
    assert len({o['frameVersionId'] for o in clone['occurrences']}) == 12
    with s.project_scope(p['projectId']):
        for i, slot in enumerate(clone['occurrences']):
            actual = render_occurrence(p, clone, slot, s.asset_path, include_outline=False)[0]
            assert actual.tobytes() == Image.open(io.BytesIO(artifact(client, selected, f'after/{i:03d}.png'))).convert('RGBA').tobytes()
    with sqlite3.connect(s.project_folder(p['projectId']) / 'project.sqlite3') as db:
        folder = json.loads(db.execute('SELECT snapshot FROM projects WHERE id=?', (p['projectId'],)).fetchone()[0])
    assert folder['clips'][-1] == clone
    assert [o['durationMs'] for o in clone['occurrences']] == [o['durationMs'] for o in original['occurrences']]
    restored = run(queue(client, p, 'preview_restore', request(p, clone)))
    assert restored['result']['report']['verdict'] == 'unknown'
    assert restored['result']['report']['reasons'] == ['follow-source-warp-unverified']
    backup = run(client.post(f"/v1/projects/{p['projectId']}/backup", json={'savedRevision': p['revision']}))
    recovered = run(client.post('/v1/projects/restore', files={'backupZip': ('follow.zip', artifact(client, backup, 'project-backup.zip'), 'application/zip')}, data={'idempotencyKey': s.uid()}))
    q = s.get_project(recovered['result']['projectId']); clone = q['clips'][-1]
    # The ZIP has no jobs/cache; all proof uses remapped project assets and saved render inputs.
    compare = run(queue(client, q, 'compare_clips', request(q, clone, candidateClipId=clone['clipId'], candidateClipRevisionId=clone['clipRevisionId'])))
    assert compare['result']['report']['verdict'] == 'non_regressing', compare['result']['report']
    assert compare['result']['report']['source'] == original['comparisonEvidence']['source']
    restored = run(queue(client, q, 'preview_restore', request(q, clone)))
    assert restored['result']['report']['verdict'] == 'unknown'


@pytest.mark.parametrize('change', ['missing-proof', 'parent-geometry', 'parent-policy', 'parent-time', 'parent-sample', 'settings', 'settings-range', 'reading', 'interpolation'])
def test_warped_comparison_requires_reproducible_approved_follow_lineage(client, tmp_path, change):
    p = native_project(client, tmp_path)
    preview = run(queue(client, p, settings={**request(p), 'region': [18, 36, 12, 25], 'gain': 3}))
    run(queue(client, p, 'apply_follow', {'previewJobId': preview['jobId']})); p = s.get_project(p['projectId'])
    clip = p['clips'][-1]; e = clip['comparisonEvidence']; proof = e['followProof']
    if change == 'missing-proof': del e['followProof']
    elif change == 'parent-geometry': proof['parent']['clip']['comparisonEvidence']['geometry'] = '0'*64
    elif change == 'parent-policy': proof['parent']['clip']['comparisonEvidence']['policy']['metric_version'] = 'future'
    elif change == 'parent-time': proof['parent']['clip']['occurrences'][0]['durationMs'] += 1
    elif change == 'parent-sample': proof['parent']['frames'][0]['sourceFrameIndex'] = 999
    elif change == 'settings': proof['settings']['gain'] = 0
    elif change == 'settings-range': proof['settings']['region'][0] = -1
    elif change == 'reading': proof['settings']['readOn'] = '0'*64
    else: e['unsupported'] = 'interpolated-source-sample'
    with s.transaction() as db: s.write_project(db, p, '잘못된 follow 계보 fixture')
    p = s.get_project(p['projectId'])
    compared = run(queue(client, p, 'compare_clips', request(p, clip, candidateClipId=clip['clipId'], candidateClipRevisionId=clip['clipRevisionId'])))
    assert compared['result']['report']['verdict'] == 'unknown'
    assert queue(client, p, 'apply_follow', {'previewJobId': compared['jobId']}).status_code == 409


def test_transported_subset_reading_hash_keeps_original_strip_columns_after_save_and_backup(client, tmp_path):
    p = native_project(client, tmp_path / 'origin')
    p = native_project(client, tmp_path / 'subset', existing=p, phase=3, frame_count=8)
    reading, target = p['clips'][0], p['clips'][-1]
    settings = {**request(p, target), 'region': [18, 36, 12, 25], 'gain': 3,
                'readOnClipId': reading['clipId'], 'readOnClipRevisionId': reading['clipRevisionId']}
    implicit = run(queue(client, p, settings=settings))
    report = implicit['result']['report']
    assert report['readOn']['relation'] == 'transported' and report['readOn']['sourceCells'] == list(range(3, 11))
    assert not report['unchanged']
    settings['readOn'] = report['readOn']['sha256']
    bad = run(queue(client, p, settings={**settings, 'readOn': '0'*64}))
    assert bad['result']['report']['readOn']['relation'] == 'uncertain'
    assert queue(client, p, 'apply_follow', {'previewJobId': bad['jobId']}).status_code == 409
    preview = run(queue(client, p, settings=settings))
    run(queue(client, p, 'apply_follow', {'previewJobId': preview['jobId']})); p = s.get_project(p['projectId'])
    followed = p['clips'][-1]
    assert len(followed['occurrences']) == 8
    selected = run(queue(client, p, 'compare_clips', request(p, followed, candidateClipId=followed['clipId'], candidateClipRevisionId=followed['clipRevisionId'])))
    assert selected['result']['report']['verdict'] == 'non_regressing', selected['result']['report']
    saved = run(queue(client, p, 'apply_follow', {'previewJobId': selected['jobId']})); p = s.get_project(p['projectId'])
    clone = p['clips'][-1]
    assert clone['clipId'] == saved['result']['clipId']
    for key in ('source', 'origin'): assert clone['comparisonEvidence'][key] == target['comparisonEvidence'][key]
    assert [o['durationMs'] for o in clone['occurrences']] == [o['durationMs'] for o in target['occurrences']]
    backup = run(client.post(f"/v1/projects/{p['projectId']}/backup", json={'savedRevision': p['revision']}))
    recovered = run(client.post('/v1/projects/restore', files={'backupZip': ('subset.zip', artifact(client, backup, 'project-backup.zip'), 'application/zip')}, data={'idempotencyKey': s.uid()}))
    q = s.get_project(recovered['result']['projectId']); clone = q['clips'][-1]
    compare = run(queue(client, q, 'compare_clips', request(q, clone, candidateClipId=clone['clipId'], candidateClipRevisionId=clone['clipRevisionId'])))
    assert compare['result']['report']['verdict'] == 'non_regressing', compare['result']['report']
    restored = run(queue(client, q, 'preview_restore', request(q, clone)))
    assert restored['result']['report']['verdict'] == 'unknown'
    # A damaged parent interpolation receipt cannot be laundered by a valid subset/hash.
    clone['comparisonEvidence']['followProof']['parent']['clip']['comparisonEvidence']['unsupported'] = 'interpolated-source-sample'
    with s.transaction() as db: s.write_project(db, q, '미증명 보간 subset fixture')
    q = s.get_project(q['projectId'])
    compared = run(queue(client, q, 'compare_clips', request(q, clone, candidateClipId=clone['clipId'], candidateClipRevisionId=clone['clipRevisionId'])))
    assert compared['result']['report']['verdict'] == 'unknown'
    assert queue(client, q, 'apply_follow', {'previewJobId': compared['jobId']}).status_code == 409
