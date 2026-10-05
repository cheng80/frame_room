"""Synthetic local cells exercise the real adapter/engine; no paid generation."""
import copy
import io
import json
import socket
import zipfile

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from alignment.pipeline import render_occurrence
from services.api import store as s
from services.api.main import app
from services.worker.main import publish
from services.worker.task import execute


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(s, 'DATA', tmp_path / 'data')
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('Clip tools must stay local'))
    s.init()
    with TestClient(app) as c:
        c.headers['X-Session-Token'] = c.get('/v1/health').json()['sessionToken']
        yield c


def make_project(client, parent=None):
    response = client.post('/v1/projects', json={'name': '합성 동작 도구 시험', **({'parentDirectory': str(parent)} if parent else {})})
    assert response.status_code == 201, response.text
    p = response.json()
    image = Image.new('RGBA', (20, 24))
    draw = ImageDraw.Draw(image)
    draw.rectangle((5, 2, 14, 21), fill=(100, 90, 70, 255))
    draw.rectangle((14, 9, 17, 13), fill=(240, 30, 40, 255))
    image.putpixel((2, 4), (70, 90, 120, 15))
    image.putpixel((3, 5), (120, 30, 170, 128))
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    with s.project_scope(p['projectId']), s.transaction() as db:
        asset = s.register_asset(stream.getvalue(), 'synthetic-local.png', c=db)
        fid, gid, grid = s.uid(), s.uid(), s.uid()
        frame = dict(frameId=s.uid(), frameVersionId=fid, rawAssetId=asset['assetId'], imageAssetId=asset['assetId'],
                     sourceRect={'x': 0, 'y': 0, 'width': 20, 'height': 24},
                     sourceToFrameTransform={'scaleX': 1, 'scaleY': 1, 'offsetX': 0, 'offsetY': 0},
                     nativeScaleGroupId=gid, extractionVersion='synthetic-test', review='pending', hidden=False,
                     sourceProcessing={'kind': 'fixture', 'retained': {'metadata': [1, 2, 3]}})
        group = dict(alignmentGroupId=gid, groupRevisionId=grid, frameVersionIds=[fid],
                     mode='preserve-source-scale', sharedScale=1.25, cell={'width': 64, 'height': 64, 'edge': 0},
                     targetAnchor={'x': 32, 'y': 50}, bodyMeasurement=None, resampler='nearest', roundingVersion='js-round-v1')
        alignment = dict(frameVersionId=fid, groupRevisionId=grid, sourceAnchor={'x': 10, 'y': 22},
                         anchorSpace='crop', method='manual', contactMode='grounded', authoredOffsetPx={'x': 0, 'y': 0}, approval='pending')
        slots = [dict(occurrenceId=s.uid(), frameVersionId=fid, durationMs=duration, timingMode='explicit',
                      transform={'dx': index - 1, 'dy': (0, -2, 1, 0)[index], 'flipX': index == 1, 'rotationDeg': index * 3},
                      pixelEdits=[{'x': 29, 'y': 28, 'color': [20, 130, 80, 127]}])
                 for index, duration in enumerate((37, 83, 61, 119))]
        clip = dict(clipId=s.uid(), clipRevisionId=s.uid(), name='합성 걷기', stateId='walk', direction='front', facing='right',
                    defaultFps=10, loop=True, endBehavior='hold-last', review='pending', referenceRevisionId=None, occurrences=slots)
        p.update(assets=[asset], frames=[frame], alignmentGroups=[group], alignments={fid: alignment}, clips=[clip])
        p['outline'].update(enabled=True, mode='bake')
        s.write_project(db, p, '합성 자료 준비')
    return s.get_project(p['projectId'])


def params(p, op='preview_follow', **changes):
    clip = p['clips'][0]
    values = {'clipId': clip['clipId'], 'clipRevisionId': clip['clipRevisionId']}
    values.update({'region': [32, 36, 16, 18], 'gain': .5} if op == 'preview_follow' else
                  {'item': 'red watch', 'side': 'left', 'part': 'wrist', 'direction': 'front', 'facing': 'right', 'marker': '#F01E28'})
    return {**values, **changes}


def queue(c, p, op='preview_follow', settings=None, idem=None, **changes):
    return c.post(f"/v1/projects/{p['projectId']}/jobs", json={'operation': op, 'inputRevision': p['revision'],
                  'assetIds': [], 'params': settings if settings is not None else params(p, op), 'idempotencyKey': idem or s.uid(), **changes})


def run(response):
    assert response.status_code == 202, response.text
    j = s.get_job(response.json()['jobId'])
    out = s.job_directory(j['jobId']) / j['attemptId'] / 'staging'
    result = execute(j, out)
    # Mirror the isolated child's publication checkpoint (hash validation).
    result['publicationHashes'] = {name: s.digest((out / name).read_bytes()) for name in result.get('files', [])}
    publish(j, {'ok': True, 'result': result})
    return s.get_job(j['jobId'])


def artifact(c, job, name):
    record = next(a for a in job['artifacts'] if a['name'] == name)
    response = c.get(record['url'])
    assert response.status_code == 200, response.text
    assert s.digest(response.content) == record['sha256']
    return response.content


def db_count(table):
    with s.connect() as db:
        return db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]


def changed_project(p):
    with s.transaction() as db:
        p = s.get_project(p['projectId'], db)
        p['characterName'] = '다른 편집'
        s.write_project(db, p, '동시 편집')
    return p


@pytest.mark.parametrize('operation,changes', [
    ('preview_follow', {'gain': 9}), ('preview_follow', {'freq': 0}), ('preview_follow', {'damping': False}),
    ('preview_follow', {'region': [1, 1, 20, 20]}), ('preview_follow', {'region': [32, 32, 0, 2]}),
    ('preview_follow', {'onFold': 'unsafe'}), ('preview_follow', {'extra': True}),
    ('check_handed', {'marker': '#888888'}), ('check_handed', {'marker': 'red'}),
    ('check_handed', {'side': 'screen-left'}), ('check_handed', {'part': 'toe'}),
    ('check_handed', {'referenceAssetId': 'foreign'}), ('check_handed', {'state': 'run'}),
])
def test_validation_rejects_before_job_creation(client, operation, changes):
    p = make_project(client)
    response = queue(client, p, operation, params(p, operation, **changes))
    assert response.status_code in (422, 404), response.text
    assert db_count('jobs') == 0 and s.get_project(p['projectId']) == p


def test_revision_scope_empty_assets_and_idempotency(client):
    p = make_project(client)
    assert queue(client, p, inputRevision=1).status_code == 409
    assert queue(client, p, settings=params(p, clipRevisionId='old')).status_code == 409
    assert queue(client, p, assetIds=[p['assets'][0]['assetId']]).status_code == 422
    other = make_project(client)
    assert queue(client, p, settings=params(other)).status_code == 422
    submitted = queue(client, p, idem='preview-once')
    duplicate = queue(client, p, idem='preview-once')
    assert duplicate.json()['jobId'] == submitted.json()['jobId']
    assert queue(client, p, settings=params(p, gain=0), idem='preview-once').status_code == 409
    assert db_count('jobs') == 1


@pytest.mark.parametrize('size,count,loop', [(1025, 4, True), (1024, 17, True), (64, 3, True), (64, 4, False), (64, 65, True)])
def test_limits_validated_without_rendering(client, size, count, loop):
    p = make_project(client)
    with s.transaction() as db:
        p['alignmentGroups'][0]['cell'].update(width=size, height=size)
        original = p['clips'][0]['occurrences'][0]
        p['clips'][0].update(loop=loop, occurrences=[{**original, 'occurrenceId': s.uid()} for _ in range(count)])
        s.write_project(db, p, '한도 시험')
    response = queue(client, p)
    assert response.status_code == 422, response.text
    assert db_count('jobs') == 0


def test_follow_preview_uses_final_cells_preserves_rgba_timing_without_mutation(client):
    p = make_project(client)
    before = copy.deepcopy(p)
    count = db_count('assets')
    job = run(queue(client, p))
    assert job['status'] == 'succeeded'
    assert s.get_project(p['projectId']) == before and db_count('assets') == count
    result = job['result']
    assert result['tool'] == 'follow' and result['version'] == 'clip-tools-v1'
    assert result['report']['timingMethod'] == 'time-weighted-periodic'
    assert result['report']['unchanged'] is False
    durations = [o['durationMs'] for o in p['clips'][0]['occurrences']]
    assert result['preview']['durationsMs'] == durations
    assert result['preview']['firstFrame'] == result['cellFiles']['before'][0]['name']
    direct = [render_occurrence(p, p['clips'][0], o, s.asset_path, include_outline=False)[0] for o in p['clips'][0]['occurrences']]
    for record, image in zip(result['cellFiles']['before'], direct):
        assert Image.open(io.BytesIO(artifact(client, job, record['name']))).tobytes() == image.tobytes()
    for kind in ('before', 'after'):
        pngs = [Image.open(io.BytesIO(artifact(client, job, r['name']))).convert('RGBA') for r in result['cellFiles'][kind]]
        data = artifact(client, job, result['preview'][kind])
        with Image.open(io.BytesIO(data)) as animation:
            assert animation.n_frames == 4 and animation.info['loop'] == 0
            for index, png in enumerate(pngs):
                animation.seek(index)
                animation.load()
                assert animation.info['duration'] == durations[index]
                assert animation.convert('RGBA').tobytes() == png.tobytes()
        strip = Image.open(io.BytesIO(artifact(client, job, result['preview'][kind + 'Strip'])))
        assert strip.size == (256, 64)
        assert any(np.any((np.array(png)[..., 3] > 0) & (np.array(png)[..., 3] < 255)) for png in pngs)
        for index, png in enumerate(pngs):
            assert strip.crop((index * 64, 0, (index + 1) * 64, 64)).tobytes() == png.tobytes()
    # Pixels outside each body's moving ellipse remain byte-identical, including alpha.
    ys, xs = np.mgrid[:64, :64]
    for index, (image, record) in enumerate(zip(direct, result['cellFiles']['after'])):
        shifted = result['report']['regionShifts'][index]
        outside = ((xs - 32 - shifted['x']) / 16) ** 2 + ((ys - 36 - shifted['y']) / 18) ** 2 >= 1
        after = np.array(Image.open(io.BytesIO(artifact(client, job, record['name']))))
        assert np.array_equal(np.array(image)[outside], after[outside])


@pytest.mark.parametrize('contact', ['grounded', 'airborne'])
def test_apply_exact_preview_identity_anchors_pending_lineage_and_idempotency(client, monkeypatch, contact):
    from adapters.spritegen import clip_tools
    p = make_project(client)
    with s.transaction() as db:
        for entity in (p['frames'][0], p['clips'][0]):
            entity.update(review='approved', reviewChecks={'accepted': True}, reviewReferenceRevisionId='old-ref',
                          reviewReason='이전 그림 승인', reviewInvalidatedReason='이전 이력')
        alignment = next(iter(p['alignments'].values()))
        alignment['contactMode'] = contact
        if contact == 'airborne':
            alignment['rootAnchor'] = {'x': 8.5, 'y': 18.5}
        s.write_project(db, p, '이전 승인 이력')
    original = copy.deepcopy(p)
    source_bytes = s.asset_path(p['assets'][0]['assetId']).read_bytes()
    preview = run(queue(client, p))
    # Publication must consume the preview; never run the effect again.
    monkeypatch.setattr(clip_tools, 'follow_frames', lambda *a, **k: pytest.fail('Do not recompute approved preview'))
    response = queue(client, p, 'apply_follow', {'previewJobId': preview['jobId']}, idem='apply-once')
    job = run(response)
    q = s.get_project(p['projectId'])
    s.validate_snapshot(q)
    assert job['status'] == 'needs_review' and q['revision'] == p['revision'] + 1
    assert len(q['assets']) == 5 and len(q['frames']) == 5 and len(q['clips']) == 2
    assert q['clips'][0] == original['clips'][0] and q['frames'][0] == original['frames'][0]
    assert q['alignmentGroups'][0] == original['alignmentGroups'][0] and q['alignments'][p['frames'][0]['frameVersionId']] == next(iter(original['alignments'].values()))
    assert s.asset_path(p['assets'][0]['assetId']).read_bytes() == source_bytes
    created = q['clips'][1]
    assert created['clipId'] == job['result']['clipId'] and created['review'] == 'pending'
    assert {key for key in created if key.startswith('review')} == {'review'}
    assert created['sourceProcessing']['sourceClip'] == original['clips'][0]
    for index, slot in enumerate(created['occurrences']):
        frame = next(f for f in q['frames'] if f['frameVersionId'] == slot['frameVersionId'])
        asset = next(a for a in q['assets'] if a['assetId'] == frame['imageAssetId'])
        record = preview['result']['cellFiles']['after'][index]
        png = artifact(client, preview, record['name'])
        assert s.asset_path(asset['assetId']).read_bytes() == png
        assert asset['provenance']['parentAssetId'] == original['assets'][0]['assetId']
        assert asset['provenance']['sourceFrame'] == original['frames'][0]
        assert asset['provenance']['sourceOccurrence'] == original['clips'][0]['occurrences'][index]
        assert asset['provenance']['previewJobId'] == preview['jobId']
        assert asset['provenance']['settings'] == preview['result']['settings']
        assert frame['review'] == q['alignments'][frame['frameVersionId']]['approval'] == 'pending'
        assert q['alignments'][frame['frameVersionId']]['contactMode'] == contact
        assert {key for key in frame if key.startswith('review')} == {'review'}
        assert slot['pixelEdits'] == [] and slot['durationMs'] == record['durationMs']
        cell, qa = render_occurrence(q, created, slot, s.asset_path, include_outline=False)
        assert cell.tobytes() == Image.open(io.BytesIO(png)).tobytes()
        assert qa['anchor'] == pytest.approx(list(preview['result']['source']['anchors'][index].values()))
    replay = queue(client, p, 'apply_follow', {'previewJobId': preview['jobId']}, idem='apply-once')
    assert replay.json()['jobId'] == job['jobId'] and db_count('jobs') == 2
    # Retrying publication itself is safe too.
    checkpoint = {'ok': True, 'result': {'files': []}}
    publish(s.get_job(job['jobId']), checkpoint)
    assert s.get_project(p['projectId']) == q and db_count('assets') == 5


@pytest.mark.parametrize('phase', ['enqueue', 'execute', 'publish'])
def test_stale_apply_rejected_without_assets_or_project_write(client, phase):
    p = make_project(client)
    preview = run(queue(client, p))
    settings = {'previewJobId': preview['jobId']}
    if phase == 'enqueue':
        changed = changed_project(p)
        response = queue(client, changed, 'apply_follow', settings)
        assert response.status_code == 409, response.text
    else:
        response = queue(client, p, 'apply_follow', settings)
        job = s.get_job(response.json()['jobId'])
        out = s.job_directory(job['jobId']) / job['attemptId'] / 'staging'
        if phase == 'publish':
            result = execute(job, out)
        changed = changed_project(p)
        with pytest.raises(s.AppError) as err:
            if phase == 'execute':
                execute(job, out)
            else:
                publish(job, {'ok': True, 'result': result})
        assert err.value.code == 'REVISION_CONFLICT'
    assert db_count('assets') == 1 and s.get_project(p['projectId']) == changed


@pytest.mark.parametrize('phase', ['preview-file', 'apply-staging'])
def test_tampered_cells_fail_before_registration(client, phase):
    p = make_project(client)
    preview = run(queue(client, p))
    job = s.get_job(queue(client, p, 'apply_follow', {'previewJobId': preview['jobId']}).json()['jobId'])
    out = s.job_directory(job['jobId']) / job['attemptId'] / 'staging'
    name = preview['result']['cellFiles']['after'][-1]['name']
    if phase == 'preview-file':
        path = s.artifact_directory(preview['jobId']) / preview['attemptId'] / name
    else:
        result = execute(job, out)
        path = out / name
    path.write_bytes(b'tampered-preview')
    with pytest.raises(s.AppError) as err:
        if phase == 'preview-file':
            execute(job, out)
        else:
            publish(job, {'ok': True, 'result': result})
    assert err.value.code in ('FOLLOW_PREVIEW_HASH', 'ARTIFACT_HASH')
    assert s.get_project(p['projectId']) == p and db_count('assets') == 1


def test_apply_requires_successful_same_project_preview(client):
    p = make_project(client)
    assert queue(client, p, 'apply_follow', {}).status_code == 422
    assert queue(client, p, 'apply_follow', {'previewJobId': 'missing'}).status_code == 404
    preview_response = queue(client, p)
    assert queue(client, p, 'apply_follow', {'previewJobId': preview_response.json()['jobId']}).status_code == 409
    preview = run(preview_response)
    other = make_project(client)
    assert queue(client, other, 'apply_follow', {'previewJobId': preview['jobId']}).status_code == 404
    check = run(queue(client, p, 'check_handed'))
    assert queue(client, p, 'apply_follow', {'previewJobId': check['jobId']}).status_code == 409


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity'])
def test_nonfinite_request_returns_validation_error(client, value):
    p = make_project(client)
    body = {'operation': 'preview_follow', 'inputRevision': p['revision'], 'assetIds': [],
            'params': params(p, gain='NONFINITE'), 'idempotencyKey': 'nonfinite'}
    encoded = json.dumps(body).replace('"NONFINITE"', value)
    response = client.post(f"/v1/projects/{p['projectId']}/jobs", content=encoded, headers={'Content-Type': 'application/json'})
    assert response.status_code == 422 and response.json()['code'] == 'JOB_REQUEST_INVALID'
    assert db_count('jobs') == 0


def test_handed_raw_request_hash_retry_and_reference_scope(client):
    p = make_project(client)
    other = make_project(client)
    settings = params(p, 'check_handed', referenceAssetId=other['assets'][0]['assetId'])
    assert queue(client, p, 'check_handed', settings).status_code == 422
    settings['referenceAssetId'] = p['assets'][0]['assetId']
    queued = queue(client, p, 'check_handed', settings, idem='handed-raw')
    assert queued.status_code == 202, queued.text
    job = s.get_job(queued.json()['jobId'])
    assert job['request']['params'] == settings and 'state' not in job['request']['params']
    assert job['requestHash'] == s.digest(s.dumps(job['request']).encode())
    with s.transaction() as db:
        job['status'] = 'failed'
        s.write_job(db, job)
    response = client.post(f"/v1/jobs/{job['jobId']}/retry", json={'idempotencyKey': 'retry-handed'})
    assert response.status_code == 200, response.text
    result = run(queue(client, p, 'check_handed', settings, idem='handed-raw'))
    assert result['status'] == 'succeeded' and result['result']['settings']['state'] == 'walk'
    assert s.get_project(p['projectId']) == p and db_count('jobs') == 1


@pytest.mark.parametrize('field', ['version', 'source', 'cellFiles', 'settings'])
def test_publication_rechecks_preview_manifest_before_registering(client, field):
    p = make_project(client)
    preview = run(queue(client, p))
    job = s.get_job(queue(client, p, 'apply_follow', {'previewJobId': preview['jobId']}).json()['jobId'])
    out = s.job_directory(job['jobId']) / job['attemptId'] / 'staging'
    result = execute(job, out)
    if field == 'version':
        result[field] = 'unknown-version'
    elif field == 'source':
        result[field]['anchors'][0]['x'] += 1
    elif field == 'settings':
        result[field]['gain'] += 1
    else:
        result[field]['after'][0]['sha256'] = '0' * 64
    with pytest.raises(s.AppError) as err:
        publish(job, {'ok': True, 'result': result})
    assert err.value.code == 'FOLLOW_PREVIEW_INVALID'
    assert db_count('assets') == 1 and s.get_project(p['projectId']) == p


@pytest.mark.parametrize('marker,verdict', [('#F01E28', 'suspect'), ('#0011ff', 'inconclusive')])
def test_handed_board_occurrences_and_readonly_state(client, marker, verdict):
    p = make_project(client)
    job = run(queue(client, p, 'check_handed', params(p, 'check_handed', marker=marker)))
    assert job['status'] == 'succeeded'
    result = job['result']
    assert result['tool'] == 'handed' and result['settings']['state'] == 'walk'
    assert result['report']['verdict'] == verdict
    for suspect in result['report']['suspectFrames']:
        assert suspect['occurrenceId'] == p['clips'][0]['occurrences'][suspect['index']]['occurrenceId']
    board = Image.open(io.BytesIO(artifact(client, job, result['preview']['board'])))
    assert board.format == 'PNG' and board.width >= 256
    assert s.get_project(p['projectId']) == p and db_count('assets') == 1


def test_missing_or_corrupt_source_cannot_publish_preview(client):
    p = make_project(client)
    response = queue(client, p)
    job = s.get_job(response.json()['jobId'])
    path = s.asset_path(p['assets'][0]['assetId'])
    path.write_bytes(b'broken-source')
    with pytest.raises(s.AppError) as err:
        execute(job, s.job_directory(job['jobId']) / job['attemptId'] / 'staging')
    assert err.value.code == 'ASSET_HASH'
    assert db_count('artifacts') == 0 and db_count('assets') == 1 and s.get_project(p['projectId']) == p


def test_external_folder_apply_backup_restore_retains_lineage_and_pixels(client, tmp_path):
    parent = tmp_path / 'user projects'
    parent.mkdir()
    p = make_project(client, parent)
    preview = run(queue(client, p, settings=params(p, gain=0)))
    applied = run(queue(client, p, 'apply_follow', {'previewJobId': preview['jobId']}))
    q = s.get_project(p['projectId'])
    root = s.project_folder(q['projectId'])
    assert root.is_relative_to(parent) and s.artifact_directory(preview['jobId']).is_relative_to(root)
    assert all(s.asset_path(a['assetId']).is_relative_to(root / 'assets') for a in q['assets'])
    portable = json.loads((root / 'project.json').read_bytes())
    assert portable  # The folder mirror was flushed after publication.
    backup = run(client.post(f"/v1/projects/{p['projectId']}/backup", json={'savedRevision': q['revision']}))
    archive = artifact(client, backup, 'project-backup.zip')
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        saved = json.loads(z.read('project.json'))['snapshot']
        assert saved['clips'][1]['sourceProcessing']['previewJobId'] == preview['jobId']
    restored = run(client.post('/v1/projects/restore', files={'backupZip': ('follow.zip', archive, 'application/zip')},
                               data={'idempotencyKey': 'follow-restore'}))
    copy_p = s.get_project(restored['result']['projectId'])
    s.validate_snapshot(copy_p)
    assert copy_p['clips'][1]['clipId'] == applied['result']['clipId']
    original_asset = copy_p['assets'][0]['assetId']
    assert original_asset != p['assets'][0]['assetId']
    for asset in copy_p['assets'][1:]:
        provenance = asset['provenance']
        assert provenance['parentAssetId'] == original_asset
        assert provenance['sourceFrame']['imageAssetId'] == original_asset
        png = artifact(client, preview, provenance['previewCell']['name'])
        assert s.asset_path(asset['assetId']).read_bytes() == png
