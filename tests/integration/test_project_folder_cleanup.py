"""Cleanup semantics against real portable folders and an isolated SQLite index.

Media is generated locally as a test fixture. No user data, HTTP server, worker,
AI provider, or native folder chooser is used.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
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
@pytest.mark.parametrize('operation', ['cleanup', 'delete'])
def test_active_job_refuses_delete_or_cleanup_without_changes(make_project, isolated_store, status, operation):
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
            folders.delete_project(active['pid'], active['project']['revision'])
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


def test_moved_folder_reopens_at_new_location_with_history_and_outputs(make_project, isolated_store):
    project = make_project('이동 후 재열기')
    original = project['project']
    folder = project['path']
    rows_before = rows_for_project(project['pid'])
    files_before = tree_bytes(folder)
    # Safe move: no delete. Opening the moved folder replaces the missing registration.
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


def leftovers(record):
    return [x.name for x in record['path'].parent.iterdir() if x.name.startswith('.' + record['path'].name)]


def test_delete_removes_own_folder_and_index_preserves_other_project_and_moved_copy(make_project, isolated_store):
    removed, kept = make_project('삭제 대상'), make_project('다른 프로젝트')
    backup = isolated_store / 'user-backup-copy'
    shutil.copytree(removed['path'], backup)
    before_kept, backup_bytes = (rows_for_project(kept['pid']), tree_bytes(kept['path'])), tree_bytes(backup)
    assert folders.delete_project(removed['pid'], removed['project']['revision']) == {'deletedProjectId': removed['pid'], 'folderDeleted': True}
    assert not removed['path'].exists() and leftovers(removed) == []
    assert all(not rows for rows in rows_for_project(removed['pid']).values())
    assert (rows_for_project(kept['pid']), tree_bytes(kept['path'])) == before_kept
    assert tree_bytes(backup) == backup_bytes


@pytest.mark.parametrize('ready', [1, 0])
def test_delete_missing_folder_with_pending_outbox_never_recreates_it(make_project, isolated_store, ready):
    project = make_project('이미 없는 폴더')
    moved = move_away(project, isolated_store)
    moved_bytes = tree_bytes(moved)
    with s.connect() as db:
        db.execute('INSERT INTO folder_sync VALUES (?)', (project['pid'],))
        db.execute('UPDATE project_folders SET ready=? WHERE project_id=?', (ready, project['pid']))
    assert folders.delete_project(project['pid'], project['project']['revision'])['folderDeleted'] is False
    assert not project['path'].exists() and leftovers(project) == []
    assert all(not rows for rows in rows_for_project(project['pid']).values())
    assert tree_bytes(moved) == moved_bytes


@pytest.mark.parametrize('change,code', [
    ('symlink-root', 'PROJECT_DELETE_UNSAFE'), ('symlink-ancestor', 'PROJECT_DELETE_UNSAFE'),
    ('other-marker', 'PROJECT_FOLDER_MISMATCH'), ('no-marker', 'PROJECT_DELETE_UNSAFE'),
    ('file', 'PROJECT_DELETE_UNSAFE'), ('nested-registered', 'PROJECT_DELETE_UNSAFE'),
    ('nested-copy', 'PROJECT_DELETE_UNSAFE'), ('read-only', 'PROJECT_DELETE_UNSAFE'),
])
def test_delete_refuses_unrelated_or_unsafe_folder_without_changes(make_project, isolated_store, change, code):
    target, other = make_project('검증 대상'), make_project('다른 대상')
    root, watched = target['path'], isolated_store
    if change == 'symlink-root':
        real = move_away(target, isolated_store)
        root.symlink_to(real, target_is_directory=True)
    elif change == 'symlink-ancestor':
        parent = root.parent
        parent.rename(parent.with_name('projects-real'))
        parent.symlink_to(parent.with_name('projects-real'), target_is_directory=True)
    elif change == 'other-marker':
        marker = json.loads((root / 'project.json').read_text())
        (root / 'project.json').write_text(json.dumps({**marker, 'projectId': other['pid']}))
    elif change == 'no-marker':
        (root / 'project.json').unlink()
    elif change == 'file':
        move_away(target, isolated_store)
        root.write_bytes(b'not a project folder')
    elif change == 'nested-registered':
        nested = root / 'kept-inside'
        other['path'].rename(nested)
        folders.open_project(str(nested))
    elif change == 'nested-copy':
        shutil.copytree(other['path'], root / 'outputs' / 'backup-copy')
    else:
        (root / 'videos').chmod(0o555)
    before = index_state(), {p.relative_to(watched).as_posix(): (p.is_symlink(), None if p.is_symlink() or not p.is_file() else p.read_bytes()) for p in watched.rglob('*') if 'app-index/app.sqlite3' not in p.as_posix()}
    try:
        with pytest.raises(s.AppError) as error:
            folders.delete_project(target['pid'], target['project']['revision'])
        assert error.value.code == code and error.value.status == 409
        after = index_state(), {p.relative_to(watched).as_posix(): (p.is_symlink(), None if p.is_symlink() or not p.is_file() else p.read_bytes()) for p in watched.rglob('*') if 'app-index/app.sqlite3' not in p.as_posix()}
        assert after == before
    finally:
        if change == 'read-only':
            (root / 'videos').chmod(0o755)


def test_commit_failure_leaves_folder_bytes_and_index_unchanged(make_project, isolated_store, monkeypatch):
    project = make_project('커밋 실패')
    before = index_state(), tree_bytes(project['path'])
    def failing_commit(self):
        raise sqlite3.OperationalError('injected commit failure')
    # A scoped patch: monkeypatch.undo() would also restore the isolated s.DATA.
    with monkeypatch.context() as patch:
        patch.setattr(s.StoreConnection, 'commit', failing_commit)
        with pytest.raises(sqlite3.OperationalError, match='injected commit failure'):
            folders.delete_project(project['pid'], project['project']['revision'])
    # Before commit the folder was only renamed aside, so nothing was deleted.
    assert (index_state(), tree_bytes(project['path'])) == before and leftovers(project) == []
    assert folders.delete_project(project['pid'], project['project']['revision'])['folderDeleted']
    assert not project['path'].exists()


@pytest.mark.parametrize('retry', ['delete', 'startup'])
def test_post_commit_removal_failure_is_reported_and_retried_only_on_quarantine(make_project, isolated_store, monkeypatch, retry):
    project = make_project('삭제 후 실패')
    original = shutil.rmtree
    def flaky(path, *args, **kwargs):
        original(Path(path) / 'videos')  # Some bytes are really gone before the failure.
        raise PermissionError('injected removal failure')
    monkeypatch.setattr(folders.shutil, 'rmtree', flaky)
    with pytest.raises(s.AppError) as error:
        folders.delete_project(project['pid'], project['project']['revision'])
    assert error.value.code == 'PROJECT_DELETE_INCOMPLETE' and error.value.status == 503
    staged = Path(error.value.details['leftoverPath'])
    assert staged.parent == project['path'].parent and staged.name.startswith('.' + project['path'].name + '.deleting-')
    assert staged.is_dir() and not (staged / 'videos').exists() and not project['path'].exists()
    assert all(not rows for rows in rows_for_project(project['pid']).values())  # No false "still listed".
    with s.connect() as db:
        record = json.loads(db.execute('SELECT value FROM meta WHERE key=?', ('project_delete:' + project['pid'],)).fetchone()[0])
    assert record == {'path': str(staged), 'dev': staged.lstat().st_dev, 'ino': staged.lstat().st_ino}
    # A folder that reappears at the original path is never a retry target.
    shutil.copytree(project['path'].parent / staged.name, project['path'])
    reappeared = tree_bytes(project['path'])
    monkeypatch.setattr(folders.shutil, 'rmtree', original)
    if retry == 'delete':
        assert folders.delete_project(project['pid'], project['project']['revision']) == {'deletedProjectId': project['pid'], 'folderDeleted': True}
    else:
        s.init()
    assert not staged.exists() and tree_bytes(project['path']) == reappeared
    with s.connect() as db:
        assert db.execute("SELECT 1 FROM meta WHERE key LIKE 'project_delete:%'").fetchone() is None


@pytest.mark.parametrize('registered', [True, False])
def test_retry_preserves_project_moved_into_quarantine(make_project, isolated_store, monkeypatch, registered):
    project, other = make_project('대기 폴더 재시도'), make_project('대기 폴더 안 프로젝트')
    with monkeypatch.context() as patch:
        patch.setattr(folders.shutil, 'rmtree', lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError('injected removal failure')))
        with pytest.raises(s.AppError) as error:
            folders.delete_project(project['pid'], project['project']['revision'])
    staged = Path(error.value.details['leftoverPath'])
    nested = staged / 'moved-in'
    other['path'].rename(nested)
    if registered:
        folders.open_project(str(nested))
    before, record = tree_bytes(nested), json.dumps(index_state(), default=str)
    for retry in (lambda: folders.delete_project(project['pid'], project['project']['revision']), folders.finish_pending_deletions):
        try:
            retry()
        except s.AppError as exc:
            assert exc.code == 'PROJECT_DELETE_UNSAFE'
        assert tree_bytes(nested) == before and json.dumps(index_state(), default=str) == record
    if registered:
        assert s.project_folder(other['pid']) == nested


@pytest.mark.parametrize('replacement', ['other-folder', 'symlink', 'file', 'symlink-ancestor'])
@pytest.mark.parametrize('retry', ['delete', 'startup'])
def test_retry_never_deletes_replaced_quarantine(make_project, isolated_store, monkeypatch, replacement, retry):
    project = make_project('대기 폴더 교체')
    original = shutil.rmtree
    def flaky(path, *args, **kwargs):
        original(Path(path) / 'videos')
        (Path(path) / 'project.json').unlink(missing_ok=True)  # Partial removal can take the marker too.
        raise PermissionError('injected removal failure')
    with monkeypatch.context() as patch:
        patch.setattr(folders.shutil, 'rmtree', flaky)
        with pytest.raises(s.AppError) as error:
            folders.delete_project(project['pid'], project['project']['revision'])
    staged = Path(error.value.details['leftoverPath'])
    parent = staged.parent
    unrelated = isolated_store / 'unrelated-user-folder'
    unrelated.mkdir()
    (unrelated / 'keep.txt').write_bytes(b'unrelated bytes')
    if replacement == 'other-folder':
        staged.rename(isolated_store / 'real-quarantine')
        unrelated.rename(staged)
        watched = staged
    elif replacement == 'symlink':
        original(staged)
        staged.symlink_to(unrelated, target_is_directory=True)
        watched = unrelated
    elif replacement == 'file':
        original(staged)
        staged.write_bytes(b'unrelated file')
        watched = unrelated
    else:
        parent.rename(parent.with_name('projects-real'))
        parent.symlink_to(parent.with_name('projects-real'), target_is_directory=True)
        watched = parent.with_name('projects-real')
    before = tree_bytes(watched), staged.read_bytes() if replacement == 'file' else None
    with s.connect() as db:
        record = db.execute('SELECT value FROM meta WHERE key=?', ('project_delete:' + project['pid'],)).fetchone()
    if retry == 'delete':
        with pytest.raises(s.AppError) as refused:
            folders.delete_project(project['pid'], project['project']['revision'])
        assert refused.value.code == 'PROJECT_DELETE_UNSAFE' and refused.value.status == 409
    else:
        s.init()
    assert (tree_bytes(watched), staged.read_bytes() if replacement == 'file' else None) == before
    assert os.path.lexists(staged)
    with s.connect() as db:  # The owner record stays so nothing is silently forgotten.
        assert db.execute('SELECT value FROM meta WHERE key=?', ('project_delete:' + project['pid'],)).fetchone() == record


@pytest.mark.parametrize('other_copy', [True, False, 'linked-root'])
def test_delete_repoints_or_protects_resource_still_needed_by_other_project(make_project, isolated_store, other_copy):
    removed, kept = make_project('공유 원본 삭제'), make_project('공유 원본 사용')
    shared = removed['historical']
    with s.transaction() as db:
        p = s.get_project(kept['pid'], db)
        p['assets'].append(shared)
        s.write_project(db, p, '다른 프로젝트 원본 참조')
    copy = kept['path'] / folders.resource_name('assets', shared['assetId'], shared)
    assert copy.is_file()
    with s.connect() as db:  # The shared index row may still point at the removed project's copy.
        db.execute('UPDATE assets SET path=? WHERE id=?', (s.stored_path(removed['path'] / folders.resource_name('assets', shared['assetId'], shared)), shared['assetId']))
    if other_copy is not True:
        copy.unlink()
        if other_copy == 'linked-root':  # Another registered root is itself an alias of the removed root.
            with s.connect() as db:
                db.execute('UPDATE project_folders SET path=? WHERE project_id=?', (str(isolated_store / 'alias'), kept['pid']))
            (isolated_store / 'alias').symlink_to(removed['path'], target_is_directory=True)
        before = index_state(), tree_bytes(removed['path'])
        with pytest.raises(s.AppError) as error:
            folders.delete_project(removed['pid'], removed['project']['revision'])
        assert error.value.code == 'PROJECT_RESOURCE_SHARED'
        assert (index_state(), tree_bytes(removed['path'])) == before
        return
    folders.delete_project(removed['pid'], removed['project']['revision'])
    assert not removed['path'].exists()
    with s.project_scope(kept['pid']):
        assert s.asset_path(shared['assetId']) == copy
    assert s.asset_path(shared['assetId']) == copy


def test_delete_refuses_copy_reached_through_linked_folder_of_other_project(isolated_store):
    removed, kept = s.create_project('공유 원본 삭제', '테스트'), s.create_project('링크 폴더', '테스트')
    with s.project_scope(removed['projectId']), s.transaction() as db:
        p = s.get_project(removed['projectId'], db)
        shared = s.register_asset(png((10, 20, 30, 255)), 'shared.png', c=db)
        p['assets'].append(shared)
        s.write_project(db, p, '원본')
    with s.project_scope(kept['projectId']), s.transaction() as db:
        p = s.get_project(kept['projectId'], db)
        p['assets'].append(shared)
        s.write_project(db, p, '다른 프로젝트 원본 참조')
    removed_root, kept_root = s.project_folder(removed['projectId']), s.project_folder(kept['projectId'])
    # The other folder's assets directory is a link back to the only original.
    shutil.rmtree(kept_root / 'assets')
    (kept_root / 'assets').symlink_to(removed_root / 'assets', target_is_directory=True)
    with s.connect() as db:
        db.execute('UPDATE assets SET path=? WHERE id=?', (s.stored_path(removed_root / folders.resource_name('assets', shared['assetId'], shared)), shared['assetId']))
    before = index_state(), tree_bytes(removed_root)
    with pytest.raises(s.AppError) as error:
        folders.delete_project(removed['projectId'], s.get_project(removed['projectId'])['revision'])
    assert error.value.code == 'PROJECT_RESOURCE_SHARED'
    assert (index_state(), tree_bytes(removed_root)) == before
