import io
import json
import zipfile
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from services.api import store as s
from services.api.main import app
from services.worker.main import publish
from services.worker.task import execute


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(s, 'DATA', tmp_path / 'data')
    s.init()
    with TestClient(app) as c:
        c.headers['X-Session-Token'] = c.get('/v1/health').json()['sessionToken']
        yield c


def new(c):
    return c.post('/v1/projects', json={'name': '자료 이름 시험', 'cell': {'width': 64, 'height': 64}}).json()


def load(c, p):
    return c.get('/v1/projects/' + p['projectId']).json()


def upload(c, p):
    image = Image.new('RGBA', (8, 8), (1, 2, 3, 255))
    data = io.BytesIO()
    image.save(data, format='PNG')
    response = c.post('/v1/projects/' + p['projectId'] + '/assets',
                      files=[('files', ('original.png', data.getvalue(), 'image/png'))])
    assert response.status_code == 201, response.text
    return load(c, p), response.json()['assets'][0]


def rename(c, p, asset_id, name):
    return c.patch('/v1/projects/' + p['projectId'] + '/edits', json={
        'expectedRevision': p['revision'],
        'operations': [{'type': 'renameAsset', 'assetId': asset_id, 'name': name}],
    })


def test_asset_name_is_project_snapshot_only_and_survives_reload_history_clone_and_backup(client):
    p, asset = upload(client, new(client))
    before = load(client, p)
    asset_id = asset['assetId']
    prior_revision = p['revision']
    with s.connect() as db:
        metadata_before = db.execute('SELECT metadata FROM assets WHERE id=?', (asset_id,)).fetchone()[0]

    response = rename(client, p, asset_id, '  새 표시 이름 🐉  ')
    assert response.status_code == 200, response.text
    renamed = response.json()['snapshot']
    named_asset = next(a for a in renamed['assets'] if a['assetId'] == asset_id)
    assert named_asset['name'] == '새 표시 이름 🐉'
    assert {k: v for k, v in named_asset.items() if k != 'name'} == {
        k: v for k, v in asset.items() if k != 'name'
    }
    assert {k: renamed[k] for k in ('references', 'frames', 'clips')} == {
        k: before[k] for k in ('references', 'frames', 'clips')
    }
    assert load(client, p) == renamed
    with s.connect() as db:
        assert db.execute('SELECT metadata FROM assets WHERE id=?', (asset_id,)).fetchone()[0] == metadata_before
    assert s.digest(s.asset_path(asset_id).read_bytes()) == asset['sha256']

    clone_response = client.post('/v1/projects/' + p['projectId'] + '/duplicate', json={
        'expectedRevision': renamed['revision'], 'name': '이름 복제 확인',
    })
    assert clone_response.status_code == 201, clone_response.text
    clone_asset = next(a for a in clone_response.json()['assets'] if a['assetId'] == asset_id)
    assert clone_asset['name'] == '새 표시 이름 🐉'

    backup_response = client.post('/v1/projects/' + p['projectId'] + '/backup', json={'savedRevision': renamed['revision']})
    assert backup_response.status_code == 202, backup_response.text
    job = s.get_job(backup_response.json()['jobId'])
    out = s.job_directory(job['jobId']) / job['attemptId'] / 'staging'
    out.mkdir(parents=True, exist_ok=True)
    result = execute(job, out)
    publish(job, {'ok': True, 'result': result})
    backup_bytes = client.get(s.get_job(job['jobId'])['artifacts'][0]['url']).content
    with zipfile.ZipFile(io.BytesIO(backup_bytes)) as archive:
        backup = json.loads(archive.read('project.json'))['snapshot']
    backup_asset = next(a for a in backup['assets'] if a['assetId'] == asset_id)
    assert backup_asset['name'] == '새 표시 이름 🐉'
    restored_response = client.post('/v1/projects/restore', files={
        'backupZip': ('backup.zip', backup_bytes, 'application/zip'),
    }, data={'idempotencyKey': s.uid()})
    assert restored_response.status_code == 202, restored_response.text
    restore_job = s.get_job(restored_response.json()['jobId'])
    restore_out = s.job_directory(restore_job['jobId']) / restore_job['attemptId'] / 'staging'
    restore_out.mkdir(parents=True, exist_ok=True)
    result = execute(restore_job, restore_out)
    restored_project_id = result['restoredProject']['projectId']
    publish(restore_job, {'ok': True, 'result': result})
    restored_project = load(client, {'projectId': restored_project_id})
    restored_asset = next(a for a in restored_project['assets'] if a['sha256'] == asset['sha256'])
    assert restored_asset['name'] == '새 표시 이름 🐉'
    assert restored_asset['assetId'] != asset_id
    with s.connect() as db:
        restored_metadata = json.loads(db.execute(
            'SELECT metadata FROM assets WHERE id=?', (restored_asset['assetId'],)
        ).fetchone()[0])
    assert 'name' not in restored_metadata
    assert load(client, p) == renamed
    with s.connect() as db:
        assert db.execute('SELECT metadata FROM assets WHERE id=?', (asset_id,)).fetchone()[0] == metadata_before
    assert s.digest(s.asset_path(asset_id).read_bytes()) == asset['sha256']

    history = client.post('/v1/projects/' + p['projectId'] + '/restore-revision', json={
        'expectedRevision': renamed['revision'], 'targetRevision': prior_revision,
    })
    assert history.status_code == 200, history.text
    assert 'name' not in next(a for a in history.json()['snapshot']['assets'] if a['assetId'] == asset_id)


@pytest.mark.parametrize('name', [None, False, 0, 201, [], {}, 'x' * 201])
def test_invalid_asset_name_rejected_atomically(client, name):
    p, asset = upload(client, new(client))
    before = load(client, p)
    response = rename(client, p, asset['assetId'], name)
    assert response.status_code == 422, response.text
    assert load(client, p) == before


@pytest.mark.parametrize('name', ['', '   ', '중복 이름'])
def test_asset_names_allow_empty_and_duplicates(client, name):
    p, first = upload(client, new(client))
    p, second = upload(client, p)
    response = client.patch('/v1/projects/' + p['projectId'] + '/edits', json={
        'expectedRevision': p['revision'],
        'operations': [
            {'type': 'renameAsset', 'assetId': first['assetId'], 'name': name},
            {'type': 'renameAsset', 'assetId': second['assetId'], 'name': name.strip()},
        ],
    })
    assert response.status_code == 200, response.text
    assert [asset['name'] for asset in response.json()['snapshot']['assets']] == [name.strip(), name.strip()]


@pytest.mark.parametrize('operation', [
    {'type': 'renameAsset', 'assetId': 'asset', 'name': 'valid', 'extra': True},
    {'type': 'otherAssetEdit', 'assetId': 'asset', 'name': 'valid'},
])
def test_invalid_rename_operation_in_batch_is_atomic(client, operation):
    p, asset = upload(client, new(client))
    before = load(client, p)
    operation = {**operation, 'assetId': asset['assetId']}
    response = client.patch('/v1/projects/' + p['projectId'] + '/edits', json={
        'expectedRevision': p['revision'],
        'operations': [{'type': 'updateCharacter', 'name': '저장되면 안 됨'}, operation],
    })
    assert response.status_code == 422, response.text
    assert load(client, p) == before


def test_unknown_or_other_project_asset_and_stale_revision_are_rejected(client):
    p, asset = upload(client, new(client))
    other, foreign_asset = upload(client, new(client))
    before = load(client, p)
    url = '/v1/projects/' + p['projectId'] + '/edits'
    for asset_id in ('unknown', foreign_asset['assetId']):
        response = client.patch(url, json={
            'expectedRevision': p['revision'],
            'operations': [
                {'type': 'updateCharacter', 'name': '저장되면 안 됨'},
                {'type': 'renameAsset', 'assetId': asset_id, 'name': '침범'},
            ],
        })
        assert response.status_code == 404, response.text
        assert load(client, p) == before

    stale = rename(client, p, asset['assetId'], '오래된 이름')
    assert stale.status_code == 200
    current = load(client, p)
    conflict = client.patch(url, json={
        'expectedRevision': before['revision'],
        'operations': [{'type': 'renameAsset', 'assetId': asset['assetId'], 'name': '덮어쓰기'}],
    })
    assert conflict.status_code == 409, conflict.text
    assert load(client, p) == current
    assert load(client, other) == other
