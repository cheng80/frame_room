"""Project-folder HTTP contract: mocked dialogs/services plus portable temporary stores."""
from __future__ import annotations

import io
import importlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from services.api import desktop, store as s
from services.api.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(s, 'DATA', tmp_path / 'isolated-app')
    s.init()
    with TestClient(app) as c:
        c.headers['X-Session-Token'] = c.get('/v1/health').json()['sessionToken']
        yield c


@pytest.fixture
def fake_folders(monkeypatch):
    folders = importlib.import_module('services.api.project_folders')
    fake = SimpleNamespace(open_project=Mock(), detach_project=Mock(), missing_projects=Mock(), cleanup_missing=Mock())
    for name, service in vars(fake).items():
        monkeypatch.setattr(folders, name, service)
    return fake


def create(client, **kwargs):
    r = client.post('/v1/projects', json={'name': '폴더 시험', **kwargs})
    assert r.status_code == 201, r.text
    return r.json()


def assert_storage(project, path):
    assert {key: project['storage'][key] for key in ('layout', 'path', 'available')} == {'layout': 'project-folder', 'path': str(path), 'available': True}
    assert not project['storage'].get('syncPending', False)


def test_folder_routes_delegate_with_exact_contract(client, fake_folders, monkeypatch):
    p = create(client)
    folder = p['storage']['path']
    fake_folders.open_project.return_value = s.get_project(p['projectId'])
    r = client.post('/v1/project-folders/open', json={'path': folder + '/project.json'})
    assert r.status_code == 200, r.text
    assert r.json() == p
    fake_folders.open_project.assert_called_once_with(folder + '/project.json')
    picker = Mock(return_value=folder)
    monkeypatch.setattr(desktop, 'pick_folder', picker)
    assert client.post('/v1/project-folders/pick', json={'purpose': 'parent'}).json() == {'path': folder}
    picker.assert_called_once_with('parent')
    picker.return_value = None
    assert client.post('/v1/project-folders/pick', json={'purpose': 'open'}).json() == {'path': None}
    missing = {'projects': [{'projectId': p['projectId'], 'name': p['name'], 'path': folder, 'revision': p['revision']}]}
    fake_folders.missing_projects.return_value = missing
    assert client.get('/v1/project-folders/missing').json() == missing
    fake_folders.missing_projects.assert_called_once_with()
    removed = {'removedProjectIds': [p['projectId']], 'removedCount': 1}
    fake_folders.cleanup_missing.return_value = removed
    items = [{'projectId': p['projectId'], 'expectedRevision': p['revision'], 'path': folder}]
    r = client.post('/v1/project-folders/cleanup', json={'projects': items})
    assert r.status_code == 200 and r.json() == removed
    fake_folders.cleanup_missing.assert_called_once_with(items)
    r = client.request('DELETE', f'/v1/projects/{p["projectId"]}', json={'expectedRevision': p['revision']})
    assert r.status_code == 200 and r.json() == {'deletedProjectId': p['projectId']}
    fake_folders.detach_project.assert_called_once_with(p['projectId'], p['revision'])


@pytest.mark.parametrize('route,body', [
    ('open', {}), ('open', {'path': ''}), ('open', {'path': '   '}), ('open', {'path': 'a\x00b'}),
    ('open', {'path': 42}), ('open', {'path': '/tmp', 'force': True}),
    ('pick', {}), ('pick', {'purpose': 'reveal'}), ('pick', {'purpose': 'open', 'path': '/tmp'}),
    ('cleanup', {}), ('cleanup', {'projects': None}), ('cleanup', {'projects': [{'projectId': '', 'expectedRevision': 1, 'path': '/tmp'}]}),
    ('cleanup', {'projects': [{'projectId': 'id', 'expectedRevision': True, 'path': '/tmp'}]}),
    ('cleanup', {'projects': [{'projectId': 'id', 'expectedRevision': '1', 'path': '/tmp'}]}),
    ('cleanup', {'projects': [{'projectId': 'id', 'expectedRevision': 0, 'path': '/tmp'}]}),
    ('cleanup', {'projects': [{'projectId': 'id', 'expectedRevision': 1, 'path': ''}]}),
    ('cleanup', {'projects': [{'projectId': 'id', 'expectedRevision': 1, 'path': '/tmp', 'force': True}]}),
])
def test_folder_routes_validate_before_side_effects(client, fake_folders, monkeypatch, route, body):
    picker = Mock()
    monkeypatch.setattr(desktop, 'pick_folder', picker)
    r = client.post('/v1/project-folders/' + route, json=body)
    assert r.status_code == 422 and r.json()['code'] == 'VALIDATION_ERROR'
    for service in vars(fake_folders).values():
        service.assert_not_called()
    picker.assert_not_called()


@pytest.mark.parametrize('route,body', [('open', {'path': '/tmp/project'}), ('pick', {'purpose': 'open'}), ('cleanup', {'projects': []})])
@pytest.mark.parametrize('headers', [{'X-Session-Token': ''}, {'X-Session-Token': 'wrong'}, {'Origin': 'https://evil.invalid'}])
def test_folder_mutations_require_local_session(client, fake_folders, monkeypatch, route, body, headers):
    picker = Mock()
    monkeypatch.setattr(desktop, 'pick_folder', picker)
    r = client.post('/v1/project-folders/' + route, json=body, headers=headers)
    assert r.status_code == 403
    for service in vars(fake_folders).values():
        service.assert_not_called()
    picker.assert_not_called()


def test_missing_list_keeps_existing_read_origin_protection(client, fake_folders):
    r = client.get('/v1/project-folders/missing', headers={'Origin': 'https://evil.invalid'})
    assert r.status_code == 403
    fake_folders.missing_projects.assert_not_called()


@pytest.mark.parametrize('route,body,service,code,status', [
    ('open', {'path': '/tmp/project'}, 'open_project', 'PROJECT_ALREADY_OPEN', 409),
    ('cleanup', {'projects': []}, 'cleanup_missing', 'REVISION_CONFLICT', 409),
    ('cleanup', {'projects': []}, 'cleanup_missing', 'PROJECT_BUSY', 409),
])
def test_folder_service_failures_are_preserved(client, fake_folders, route, body, service, code, status):
    getattr(fake_folders, service).side_effect = s.AppError(code, '시험 오류', status)
    r = client.post('/v1/project-folders/' + route, json=body)
    assert r.status_code == status and r.json()['code'] == code


@pytest.mark.parametrize('path', ['', ' ', '\x00', 5])
def test_create_rejects_invalid_parent_directory(client, monkeypatch, path):
    create_project = Mock()
    monkeypatch.setattr(s, 'create_project', create_project)
    r = client.post('/v1/projects', json={'name': '시험', 'parentDirectory': path})
    assert r.status_code == 422
    create_project.assert_not_called()


def test_empty_cleanup_is_explicit_noop(client):
    p = create(client)
    r = client.post('/v1/project-folders/cleanup', json={'projects': []})
    assert r.status_code == 200 and r.json() == {'removedProjectIds': [], 'removedCount': 0}
    assert client.get('/v1/projects/' + p['projectId']).json() == p


def test_snapshots_advertise_folder_after_create_edit_duplicate_restore(client, tmp_path):
    parent = tmp_path / '사용자 프로젝트 ; $(literal)'
    parent.mkdir()
    p = create(client, parentDirectory=str(parent))
    folder = Path(p['storage']['path'])
    assert folder.parent == parent and folder.is_dir()
    assert_storage(p, folder)
    pid = p['projectId']
    url = '/v1/projects/' + pid
    assert_storage(client.get(url).json(), folder)
    assert client.get(url).headers['etag'] == str(p['revision'])
    assert_storage(client.get('/v1/projects').json()['projects'][0], folder)
    r = client.patch(url + '/edits', json={'expectedRevision': p['revision'], 'operations': [{'type': 'updateCharacter', 'name': '이름 수정'}]})
    assert r.status_code == 200, r.text
    edited = r.json()['snapshot']
    assert_storage(edited, folder)
    r = client.post(url + '/restore-revision', json={'expectedRevision': edited['revision'], 'targetRevision': p['revision']})
    assert r.status_code == 200, r.text
    restored = r.json()['snapshot']
    assert_storage(restored, folder)
    assert restored['characterName'] == p['characterName']
    r = client.post(url + '/duplicate', json={'expectedRevision': restored['revision'], 'name': '새 폴더 사본'})
    assert r.status_code == 201, r.text
    duplicate = r.json()
    assert duplicate['projectId'] != pid
    duplicate_folder = Path(duplicate['storage']['path'])
    assert duplicate_folder != folder
    assert_storage(duplicate, duplicate_folder)
    assert (duplicate_folder / 'project.sqlite3').is_file()
    assert (folder / 'project.sqlite3').is_file()
    # Location is response decoration, not persisted portable project content.
    assert 'storage' not in s.get_project(pid)


@pytest.mark.parametrize('suffix', ['', '/project.json', '/project.sqlite3'])
def test_detach_preserves_folder_then_reopens_after_move(client, tmp_path, suffix):
    p = create(client)
    pid = p['projectId']
    url = '/v1/projects/' + pid
    png = io.BytesIO()
    Image.new('RGBA', (2, 2), (32, 64, 96, 255)).save(png, format='PNG')
    uploaded = client.post(url + '/assets', files=[('files', ('test.png', png.getvalue(), 'image/png'))])
    assert uploaded.status_code == 201, uploaded.text
    p = client.get(url).json()
    folder = Path(p['storage']['path'])
    history = client.get(url + '/revisions').json()
    persisted = {name: (folder / name).read_bytes() for name in ('project.json', 'project.sqlite3')}
    removed = client.request('DELETE', url, json={'expectedRevision': p['revision']})
    assert removed.status_code == 200, removed.text
    assert client.get(url).status_code == 404
    assert client.get('/v1/projects').json()['projects'] == []
    assert {name: (folder / name).read_bytes() for name in persisted} == persisted
    moved = tmp_path / '옮겨 둔 프로젝트'
    folder.rename(moved)
    r = client.post('/v1/project-folders/open', json={'path': str(moved) + suffix})
    assert r.status_code == 200, r.text
    reopened = r.json()
    assert_storage(reopened, moved)
    assert reopened['revision'] == p['revision']
    assert reopened['assets'] == p['assets']
    assert client.get(url + '/revisions').json() == history
    assert client.get(reopened['assets'][0]['url']).content == png.getvalue()
    assert client.post('/v1/project-folders/open', json={'path': str(moved)}).json() == reopened
    assert not folder.exists()


def test_missing_cleanup_removes_only_confirmed_missing_registration(client, tmp_path):
    missing = create(client, name='옮긴 프로젝트')
    keep = create(client, name='남길 프로젝트')
    source = Path(missing['storage']['path'])
    moved = tmp_path / '다른 위치'
    source.rename(moved)
    r = client.get('/v1/project-folders/missing')
    assert r.status_code == 200, r.text
    assert r.json() == {'projects': [{'projectId': missing['projectId'], 'name': missing['name'], 'path': str(source), 'revision': missing['revision']}]}
    items = [{'projectId': missing['projectId'], 'expectedRevision': missing['revision'], 'path': str(source)}]
    r = client.post('/v1/project-folders/cleanup', json={'projects': items})
    assert r.status_code == 200, r.text
    assert r.json() == {'removedProjectIds': [missing['projectId']], 'removedCount': 1}
    assert client.get('/v1/project-folders/missing').json() == {'projects': []}
    assert [p['projectId'] for p in client.get('/v1/projects').json()['projects']] == [keep['projectId']]
    assert (moved / 'project.sqlite3').is_file()
    assert client.post('/v1/project-folders/open', json={'path': str(moved)}).status_code == 200


def test_cleanup_rechecks_restored_folder_without_partial_removal(client, tmp_path):
    first = create(client, name='첫 번째')
    second = create(client, name='두 번째')
    items = []
    for index, p in enumerate((first, second)):
        path = Path(p['storage']['path'])
        path.rename(tmp_path / f'moved-{index}')
        items.append({'projectId': p['projectId'], 'expectedRevision': p['revision'], 'path': str(path)})
    assert len(client.get('/v1/project-folders/missing').json()['projects']) == 2
    (tmp_path / 'moved-1').rename(Path(second['storage']['path']))
    r = client.post('/v1/project-folders/cleanup', json={'projects': items})
    assert r.status_code == 409, r.text
    assert {p['projectId'] for p in client.get('/v1/projects').json()['projects']} == {first['projectId'], second['projectId']}


def test_openapi_contains_folder_contract():
    schema = app.openapi()
    models = schema['components']['schemas']
    assert 'parentDirectory' in models['NewProject']['properties']
    assert models['RevealedProject']['properties']['storageLayout']['const'] == 'project-folder'
    assert models['PickProjectFolder']['properties']['purpose']['enum'] == ['open', 'parent']
    for route in ('open', 'pick', 'missing', 'cleanup'):
        assert '/v1/project-folders/' + route in schema['paths']


def test_artifact_download_from_external_project_folder(client, tmp_path):
    parent = tmp_path / '외부 저장 부모'
    parent.mkdir()
    p = create(client, parentDirectory=str(parent))
    r = client.post('/v1/projects/' + p['projectId'] + '/jobs', json={'operation': 'inspect', 'inputRevision': p['revision'], 'idempotencyKey': 'local-artifact-only'})
    assert r.status_code == 202, r.text
    jid = r.json()['jobId']
    path = s.artifact_directory(jid) / 'inspection.txt'
    data = b'local portable artifact'
    s.atomic_bytes(path, data)
    aid = s.uid()
    with s.transaction() as db:
        job = s.get_job(jid, db)
        job.update(status='succeeded', artifacts=[{'artifactId': aid, 'url': '/v1/artifacts/' + aid + '/download'}])
        db.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?)', (aid, jid, path.name, s.stored_path(path), s.digest(data), 'text/plain'))
        s.write_job(db, job)
    assert not path.is_relative_to(s.DATA)
    r = client.get('/v1/artifacts/' + aid + '/download')
    assert r.status_code == 200 and r.content == data
    path.write_bytes(b'changed after publish')
    r = client.get('/v1/artifacts/' + aid + '/download')
    assert r.status_code == 424 and r.json()['code'] == 'ARTIFACT_HASH'
    path.unlink()
    assert client.get('/v1/artifacts/' + aid + '/download').status_code == 424
    # An arbitrary external path in the index must never become downloadable.
    outside = tmp_path / 'unmanaged.txt'
    outside.write_bytes(data)
    with s.connect() as db:
        db.execute('UPDATE artifacts SET path=? WHERE id=?', (str(outside), aid))
    r = client.get('/v1/artifacts/' + aid + '/download')
    assert r.status_code == 422 and r.json()['code'] == 'STORAGE_ESCAPE'


def test_retry_reuses_completed_result_in_project_job_folder(client, tmp_path):
    parent = tmp_path / '외부 작업'
    parent.mkdir()
    p = create(client, parentDirectory=str(parent))
    r = client.post('/v1/projects/' + p['projectId'] + '/jobs', json={'operation': 'inspect', 'inputRevision': p['revision'], 'idempotencyKey': 'local-retry'})
    assert r.status_code == 202, r.text
    jid = r.json()['jobId']
    with s.transaction() as db:
        job = s.get_job(jid, db)
        job['status'] = 'failed'
        original_attempt = job['attemptId']
        s.write_job(db, job)
    result = s.job_directory(jid) / original_attempt / 'result.json'
    s.atomic_bytes(result, s.dumps({'ok': True, 'result': {'local': True}}).encode())
    assert not (s.DATA / 'jobs' / jid).exists()
    r = client.post('/v1/jobs/' + jid + '/retry', json={'idempotencyKey': 'retry-once'})
    assert r.status_code == 200, r.text
    assert r.json()['reuseResultAttemptId'] == original_attempt
    assert r.json()['status'] == 'queued'
    assert result.is_file()


def test_project_copy_opens_in_new_app_store_without_shared_db(client, tmp_path, monkeypatch):
    p = create(client)
    original = Path(p['storage']['path'])
    copied = tmp_path / '프로젝트만 복사'
    shutil.copytree(original, copied)
    # Same ID and an existing live path are a conflict before changing stores.
    conflict = client.post('/v1/project-folders/open', json={'path': str(copied)})
    assert conflict.status_code == 409 and conflict.json()['code'] == 'PROJECT_ALREADY_OPEN'
    monkeypatch.setattr(s, 'DATA', tmp_path / '새 앱 인덱스')
    s.init()
    client.headers['X-Session-Token'] = client.get('/v1/health').json()['sessionToken']
    assert client.get('/v1/projects').json()['projects'] == []
    r = client.post('/v1/project-folders/open', json={'path': str(copied)})
    assert r.status_code == 200, r.text
    reopened = r.json()
    assert reopened['projectId'] == p['projectId'] and reopened['revision'] == p['revision']
    assert_storage(reopened, copied)
    r = client.patch('/v1/projects/' + p['projectId'] + '/edits', json={'expectedRevision': reopened['revision'], 'operations': [{'type': 'updateCharacter', 'name': '독립 폴더 편집'}]})
    assert r.status_code == 200, r.text
    assert r.json()['snapshot']['characterName'] == '독립 폴더 편집'
    assert (original / 'project.sqlite3').read_bytes() != (copied / 'project.sqlite3').read_bytes()
    assert json.loads((original / 'project.json').read_text())['projectId'] == p['projectId']


def test_retry_reads_video_submission_checkpoint_without_generation(client, tmp_path):
    parent = tmp_path / '영상 재개 외부 폴더'
    parent.mkdir()
    p = create(client, parentDirectory=str(parent))
    png = io.BytesIO()
    Image.new('RGBA', (2, 2), (16, 24, 32, 255)).save(png, format='PNG')
    url = '/v1/projects/' + p['projectId']
    uploaded = client.post(url + '/assets', files=[('files', ('local-test.png', png.getvalue(), 'image/png'))])
    assert uploaded.status_code == 201, uploaded.text
    p = client.get(url).json()
    r = client.post(url + '/jobs', json={'operation': 'generate_video', 'inputRevision': p['revision'], 'assetIds': [p['assets'][0]['assetId']], 'params': {}, 'idempotencyKey': 'checkpoint-fixture'})
    assert r.status_code == 202, r.text
    jid = r.json()['jobId']
    with s.transaction() as db:
        job = s.get_job(jid, db)
        job.update(status='failed', externalStarted=True)
        s.write_job(db, job)
    checkpoint = s.job_directory(jid) / 'video-checkpoint.json'
    # Only an already-submitted local fixture: no worker/provider is executed.
    s.atomic_bytes(checkpoint, s.dumps({'phase': 'submitted', 'postCount': 1, 'requestId': 'fixture-request'}).encode())
    r = client.post('/v1/jobs/' + jid + '/retry', json={'idempotencyKey': 'resume-fixture'})
    assert r.status_code == 200, r.text
    assert r.json()['status'] == 'queued'
    assert json.loads(checkpoint.read_text())['postCount'] == 1
    assert not (s.DATA / 'jobs' / jid).exists()


def test_failed_folder_sync_is_not_a_successful_edit(client, monkeypatch):
    folders = importlib.import_module('services.api.project_folders')
    p = create(client)
    failed = Mock(side_effect=s.AppError('PROJECT_FOLDER_SYNC_FAILED', '폴더 저장 실패', 503))
    monkeypatch.setattr(folders, 'flush', failed)
    r = client.patch('/v1/projects/' + p['projectId'] + '/edits', json={'expectedRevision': p['revision'], 'operations': [{'type': 'updateCharacter', 'name': '보류 편집'}]})
    assert r.status_code == 503 and r.json()['code'] == 'PROJECT_FOLDER_SYNC_FAILED'
    failed.assert_called_once()
    saved = client.get('/v1/projects/' + p['projectId']).json()
    assert saved['storage']['syncPending'] is True
