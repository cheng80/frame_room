"""Cleanup semantics against real portable folders and an isolated SQLite index.

Media is generated locally as a test fixture. No user data, HTTP server, worker,
AI provider, or native folder chooser is used.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import sqlite3
import subprocess

from PIL import Image
import pytest

from services.api import project_folders as folders, store as s, videos

TABLES = (
    'projects', 'revisions', 'jobs', 'events', 'artifacts', 'exports', 'assets',
    'videos', 'meta', 'project_folders', 'folder_sync', 'project_resources',
)


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(s, 'DATA', tmp_path / 'app-index')
    s.init()
    return tmp_path


@pytest.fixture(scope='module')
def local_video(tmp_path_factory):
    path = tmp_path_factory.mktemp('cleanup-video') / 'synthetic.mp4'
    subprocess.run([
        'ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=16x16:r=4',
        '-t', '0.5', '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(path),
    ], check=True, capture_output=True, timeout=30)
    data = path.read_bytes()
    return data, videos.validate(data, path.name)


def png(color):
    data = io.BytesIO()
    Image.new('RGBA', (3, 3), color).save(data, format='PNG')
    return data.getvalue()


def tree_bytes(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def index_state():
    with s.connect() as db:
        return {table: sorted([tuple(row) for row in db.execute(f'SELECT * FROM {table}')], key=repr) for table in TABLES}


def rows_for_project(pid):
    """All retained project metadata, including history-only and unpublished assets."""
    result = {}
    with s.connect() as db:
        for table, column in (
            ('projects', 'id'), ('revisions', 'project_id'), ('jobs', 'project_id'),
            ('exports', 'project_id'), ('project_folders', 'project_id'),
            ('folder_sync', 'project_id'), ('project_resources', 'project_id'),
        ):
            result[table] = sorted([tuple(row) for row in db.execute(f'SELECT * FROM {table} WHERE {column}=?', (pid,))], key=repr)
        for table in ('events', 'artifacts'):
            result[table] = sorted([tuple(row) for row in db.execute(f'SELECT * FROM {table} WHERE job_id IN (SELECT id FROM jobs WHERE project_id=?)', (pid,))], key=repr)
        prefix = 'video_batch:' + pid + ':'
        result['meta'] = sorted([tuple(row) for row in db.execute('SELECT * FROM meta WHERE substr(key,1,?)=?', (len(prefix), prefix))], key=repr)
        for kind in ('assets', 'videos'):
            result[kind] = sorted([tuple(row) for row in db.execute(f'SELECT * FROM {kind} WHERE id IN (SELECT resource_id FROM project_resources WHERE project_id=? AND kind=?)', (pid, kind))], key=repr)
    return result


def job_record(project, status='succeeded'):
    """A completed local output with events, export registration, and batch cache."""
    pid = project['projectId']
    jid, attempt, aid, eid = (s.uid() for _ in range(4))
    path = s.project_folder(pid) / 'outputs' / jid / attempt / 'inspection.json'
    payload = s.dumps({'fixture': 'local cleanup output', 'projectId': pid}).encode()
    s.atomic_bytes(path, payload)
    artifact = {'artifactId': aid, 'name': path.name, 'url': f'/v1/artifacts/{aid}/download', 'sha256': s.digest(payload)}
    with s.transaction() as db:
        snapshot = s.get_project(pid, db)
        job = dict(jobId=jid, projectId=pid, operation='inspect', status=status,
                   attemptId=attempt, attempts=[], inputRevision=snapshot['revision'],
                   request={'params': {}}, snapshot=snapshot, requestHash='local-fixture',
                   idempotencyKey=s.uid(), eventSeq=0, step='complete', progress={},
                   artifacts=[artifact], errors=[], createdAt=s.now(), updatedAt=s.now(), engineCommit=s.COMMIT)
        db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)', (jid, pid, job['operation'], status, job['requestHash'], job['idempotencyKey'], s.dumps(job), job['createdAt'], job['updatedAt']))
        db.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?)', (aid, jid, path.name, s.stored_path(path), artifact['sha256'], 'application/json'))
        db.execute('INSERT INTO exports VALUES (?,?,?,?)', (eid, jid, pid, s.dumps({'exportId': eid})))
        db.execute('INSERT INTO meta VALUES (?,?)', ('video_batch:' + pid + ':fixture', s.dumps({'batchId': s.uid(), 'jobIds': [jid]})))
        s.write_job(db, job)
        s.write_job(db, job)
    return jid


@pytest.fixture
def make_project(isolated_store, local_video):
    data, metadata = local_video

    def make(name):
        project = s.create_project(name, '테스트 캐릭터')
        pid = project['projectId']
        with s.project_scope(pid), s.transaction() as db:
            p = s.get_project(pid, db)
            visible = s.register_asset(png((20, 50, 90, 255)), name + '.png', c=db)
            historical = s.register_asset(png((80, 40, 10, 255)), name + '-old.png', c=db)
            current_video = videos.register(data, name + '.mp4', {'kind': 'local-test', 'baseAssetId': visible['assetId']}, metadata, db)
            historical_video = videos.register(data, name + '-old.mp4', {'kind': 'local-test'}, metadata, db)
            p['assets'].extend([visible, historical])
            p['videos'].extend([current_video, historical_video])
            s.write_project(db, p, '로컬 시험 원본과 과거 자료 등록')
        with s.project_scope(pid), s.transaction() as db:
            p = s.get_project(pid, db)
            p['assets'] = [visible]
            p['videos'] = [current_video]
            unpublished = s.register_asset(png((1, 2, 3, 255)), name + '-unpublished.png', provenance={'kind': 'local-test', 'parentAssetId': historical['assetId']}, c=db)
            s.write_project(db, p, '현재 목록에서 과거 자료 제외')
        jid = job_record(p)
        p = s.get_project(pid)
        return {'project': p, 'pid': pid, 'path': s.project_folder(pid), 'jobId': jid,
                'assetIds': {visible['assetId'], historical['assetId'], unpublished['assetId']},
                'videoIds': {current_video['videoId'], historical_video['videoId']},
                'visible': visible, 'historical': historical, 'historicalVideo': historical_video,
                'unpublished': unpublished}
    return make


def item_for(record):
    return {'projectId': record['pid'], 'expectedRevision': record['project']['revision'], 'path': str(record['path'])}


def move_away(record, parent):
    moved = parent / (record['pid'] + '-moved')
    record['path'].rename(moved)
    return moved


def test_missing_cleanup_removes_all_index_relations_and_preserves_other_project(make_project, isolated_store):
    removed, kept = make_project('제거 대상'), make_project('유지 대상')
    before_kept = rows_for_project(kept['pid']), tree_bytes(kept['path'])
    before_removed = rows_for_project(removed['pid'])
    assert all(before_removed[name] for name in ('projects', 'revisions', 'jobs', 'events', 'artifacts', 'exports', 'assets', 'videos', 'meta', 'project_folders', 'project_resources'))
    assert len(before_removed['assets']) == 3 and len(before_removed['videos']) == 2
    moved = move_away(removed, isolated_store)
    moved_bytes = tree_bytes(moved)
    # A missing folder may also leave a durable synchronization outbox entry.
    with s.connect() as db:
        db.execute('INSERT INTO folder_sync VALUES (?)', (removed['pid'],))
    assert rows_for_project(removed['pid'])['folder_sync']
    before_preview = index_state()
    assert folders.missing_projects() == {'projects': [{'projectId': removed['pid'], 'name': removed['project']['name'], 'path': str(removed['path']), 'revision': removed['project']['revision']}]}
    assert index_state() == before_preview  # Preview is read-only.
    assert folders.cleanup_missing([item_for(removed)]) == {'removedProjectIds': [removed['pid']], 'removedCount': 1}
    assert all(not rows for rows in rows_for_project(removed['pid']).values())
    with s.connect() as db:
        for kind, ids in (('assets', removed['assetIds']), ('videos', removed['videoIds'])):
            assert not ids.intersection(row[0] for row in db.execute(f'SELECT id FROM {kind}'))
    assert (rows_for_project(kept['pid']), tree_bytes(kept['path'])) == before_kept
    assert tree_bytes(moved) == moved_bytes
    assert not removed['path'].exists()
    assert folders.missing_projects() == {'projects': []}


@pytest.mark.parametrize('race,code', [
    ('revision', 'REVISION_CONFLICT'), ('path', 'PROJECT_CLEANUP_CHANGED'), ('exists', 'PROJECT_CLEANUP_CHANGED'),
])
def test_cleanup_rechecks_preview_and_atomically_rejects_changed_second_item(make_project, isolated_store, race, code):
    first, second = make_project('첫 대상'), make_project('둘째 대상')
    moved_first = move_away(first, isolated_store)
    moved_second = move_away(second, isolated_store)
    items = [item_for(first), item_for(second)]
    assert len(folders.missing_projects()['projects']) == 2
    # Simulate an actual index/filesystem change after the caller's preview.
    if race == 'revision':
        with s.connect() as db:
            p = s.get_project(second['pid'], db)
            p['revision'] += 1
            db.execute('UPDATE projects SET snapshot=? WHERE id=?', (s.dumps(p), second['pid']))
    elif race == 'path':
        with s.connect() as db:
            db.execute('UPDATE project_folders SET path=? WHERE project_id=?', (str(isolated_store / 'new-missing-location'), second['pid']))
    else:
        moved_second.rename(second['path'])
    before = index_state()
    files_before = tree_bytes(moved_first), tree_bytes(second['path'] if race == 'exists' else moved_second)
    with pytest.raises(s.AppError) as error:
        folders.cleanup_missing(items)
    assert error.value.code == code and error.value.status == 409
    assert index_state() == before  # The first valid target cannot be partially removed.
    assert (tree_bytes(moved_first), tree_bytes(second['path'] if race == 'exists' else moved_second)) == files_before


@pytest.mark.parametrize('status', ['queued', 'running', 'cancel_requested'])
@pytest.mark.parametrize('operation', ['cleanup', 'detach'])
def test_active_job_refuses_detach_or_cleanup_without_changes(make_project, isolated_store, status, operation):
    first, active = make_project('정상 대상'), make_project('진행 작업')
    with s.transaction() as db:
        job = s.get_job(active['jobId'], db)
        job['status'] = status
        s.write_job(db, job)
    roots = [first['path'], active['path']]
    if operation == 'cleanup':
        roots = [move_away(first, isolated_store), move_away(active, isolated_store)]
    before = index_state(), [tree_bytes(root) for root in roots]
    with pytest.raises(s.AppError) as error:
        if operation == 'cleanup':
            folders.cleanup_missing([item_for(first), item_for(active)])
        else:
            folders.detach_project(active['pid'], active['project']['revision'])
    assert error.value.code == 'PROJECT_BUSY' and error.value.status == 409
    assert (index_state(), [tree_bytes(root) for root in roots]) == before


def test_empty_cleanup_is_noop_with_real_missing_project(make_project, isolated_store):
    project = make_project('빈 선택')
    moved = move_away(project, isolated_store)
    before = index_state(), tree_bytes(moved)
    assert folders.missing_projects()['projects']
    assert folders.cleanup_missing([]) == {'removedProjectIds': [], 'removedCount': 0}
    assert (index_state(), tree_bytes(moved)) == before


def test_missing_preview_excludes_damaged_files_inside_existing_folder(make_project):
    project = make_project('내부 손상은 정리 제외')
    (project['path'] / 'project.sqlite3').unlink()
    before = index_state(), tree_bytes(project['path'])
    assert folders.missing_projects() == {'projects': []}
    with pytest.raises(s.AppError) as error:
        folders.cleanup_missing([item_for(project)])
    assert error.value.code == 'PROJECT_CLEANUP_CHANGED'
    assert (index_state(), tree_bytes(project['path'])) == before


def test_detach_preserves_complete_folder_and_reopen_restores_history_and_outputs(make_project, isolated_store):
    project = make_project('보관 후 재열기')
    original = project['project']
    folder = project['path']
    rows_before = rows_for_project(project['pid'])
    files_before = tree_bytes(folder)
    assert folders.detach_project(project['pid'], original['revision']) == {'deletedProjectId': project['pid']}
    assert tree_bytes(folder) == files_before
    assert all(not rows for rows in rows_for_project(project['pid']).values())
    assert index_state()['assets'] == [] and index_state()['videos'] == []
    moved = move_away(project, isolated_store)
    reopened = folders.open_project(str(moved / 'project.json'))
    assert {key: value for key, value in reopened.items() if key != 'storage'} == original
    assert reopened['storage']['path'] == str(moved)
    after = rows_for_project(project['pid'])
    for table in ('projects', 'revisions', 'jobs', 'events', 'exports', 'meta', 'project_resources'):
        assert after[table] == rows_before[table]
    for table in ('assets', 'videos'):
        assert [row[:2] for row in after[table]] == [row[:2] for row in rows_before[table]]
        for row in after[table]:
            resource = s.asset_path(row[0]) if table == 'assets' else videos.path_for(row[0])
            assert resource.is_relative_to(moved)
            assert s.digest(resource.read_bytes()) == json.loads(row[1])['sha256']
    with s.connect() as db:
        for row in db.execute('SELECT * FROM artifacts WHERE job_id=?', (project['jobId'],)):
            output = s.managed_path(row['path'])
            assert output.is_relative_to(moved) and s.digest(output.read_bytes()) == row['sha256']
    # Reopening can rebuild SQLite, but every actual media/output byte must stay unchanged.
    assert {name: data for name, data in tree_bytes(moved).items() if name not in ('project.json', 'project.sqlite3')} == {name: data for name, data in files_before.items() if name not in ('project.json', 'project.sqlite3')}
    assert s.get_job(project['jobId'])['status'] == 'succeeded'
    assert not folder.exists()


def test_cleanup_keeps_resources_referenced_only_by_retained_history_or_ownership(make_project, isolated_store):
    removed, kept = make_project('이력 공유 원본'), make_project('공유 자료 유지')
    with s.transaction() as db:
        p = s.get_project(kept['pid'], db)
        p['assets'].append(removed['historical'])
        p['videos'].append(removed['historicalVideo'])
        s.write_project(db, p, '다른 프로젝트 원본을 참조한 과거 이력')
    with s.transaction() as db:
        p = s.get_project(kept['pid'], db)
        p['assets'] = [a for a in p['assets'] if a['assetId'] != removed['historical']['assetId']]
        p['videos'] = [v for v in p['videos'] if v['videoId'] != removed['historicalVideo']['videoId']]
        s.own_resource(db, kept['pid'], 'assets', removed['unpublished']['assetId'])
        s.write_project(db, p, '현재에서는 제거하고 이력과 미게시 소유권 보존')
    before = rows_for_project(kept['pid']), tree_bytes(kept['path'])
    move_away(removed, isolated_store)
    folders.cleanup_missing([item_for(removed)])
    assert (rows_for_project(kept['pid']), tree_bytes(kept['path'])) == before
    with s.project_scope(kept['pid']):
        for asset in (removed['historical'], removed['unpublished']):
            assert s.asset_path(asset['assetId']).is_relative_to(kept['path'])
        assert videos.path_for(removed['historicalVideo']['videoId']).is_relative_to(kept['path'])
    with s.connect() as db:
        assert db.execute('SELECT 1 FROM assets WHERE id=?', (removed['visible']['assetId'],)).fetchone() is None


def test_other_active_job_preserves_unpublished_global_resources(make_project, isolated_store, local_video):
    removed, active = make_project('누락 대상'), make_project('다른 진행 작업')
    with s.transaction() as db:
        job = s.get_job(active['jobId'], db)
        job['status'] = 'running'
        s.write_job(db, job)
    # Legacy unowned work must also survive until the active attempt finishes.
    asset = s.register_asset(png((99, 88, 77, 255)), 'legacy-pending.png')
    video = videos.register(local_video[0], 'legacy-pending.mp4', metadata=local_video[1])
    paths = s.asset_path(asset['assetId']), videos.path_for(video['videoId'])
    bytes_before = [path.read_bytes() for path in paths]
    move_away(removed, isolated_store)
    result = folders.cleanup_missing([item_for(removed)])
    assert result['removedProjectIds'] == [removed['pid']]
    assert all(not rows for rows in rows_for_project(removed['pid']).values())
    assert [s.asset_path(asset['assetId']).read_bytes(), videos.path_for(video['videoId']).read_bytes()] == bytes_before
    assert s.get_job(active['jobId'])['status'] == 'running'


def test_cleanup_rolls_back_after_late_sql_failure(make_project, isolated_store):
    first, second = make_project('롤백 첫 대상'), make_project('롤백 둘째 대상')
    roots = [move_away(first, isolated_store), move_away(second, isolated_store)]
    with s.connect() as db:
        # Fail only while deleting the second target, after first-target SQL ran.
        db.execute(f"CREATE TRIGGER reject_second_cleanup BEFORE DELETE ON projects WHEN OLD.id='{second['pid']}' BEGIN SELECT RAISE(ABORT,'injected cleanup failure'); END")
    before = index_state(), [tree_bytes(root) for root in roots]
    with pytest.raises(sqlite3.IntegrityError, match='injected cleanup failure'):
        folders.cleanup_missing([item_for(first), item_for(second)])
    assert (index_state(), [tree_bytes(root) for root in roots]) == before
