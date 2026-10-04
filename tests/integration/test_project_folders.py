"""Portable storage round trips and failure recovery; no external providers."""
import json
from pathlib import Path
import shutil
import sqlite3

import pytest
from services.api import store as s, project_folders as folders, videos
from test_api import client, approved, edit, upload, load, queue, run_job, png
from test_video_jobs import media


def raw_tables(path):
    with sqlite3.connect(path) as c:
        return {name:c.execute(f'SELECT * FROM {name} ORDER BY rowid').fetchall() for name in folders.TABLES}


def test_folder_only_roundtrip_new_index_all_history_video_outputs(client,media,tmp_path,monkeypatch):
    c=client;p,a=approved(c)
    r=c.post('/v1/projects/'+p['projectId']+'/videos',files={'file':('synthetic.mp4',media,'video/mp4')},data={'expectedRevision':p['revision']})
    assert r.status_code==201,r.text
    p=r.json()['snapshot'];v=r.json()['video']
    p=edit(c,p,[{'type':'updateClip','clipId':p['clips'][0]['clipId'],'changes':{'review':'approved'}}])
    j=run_job(queue(c,p,'bake')['jobId']);assert j['artifacts']
    saved=s.get_project(p['projectId']);root=s.project_folder(p['projectId'])
    expected=raw_tables(root/'project.sqlite3')
    moved=tmp_path/'옮긴 캐릭터';shutil.copytree(root,moved)
    old_data=s.DATA;old_data.rename(tmp_path/'old-index-unavailable')
    monkeypatch.setattr(s,'DATA',tmp_path/'fresh-index');s.init()
    opened=folders.open_project(str(moved/'project.sqlite3'))
    assert opened['storage']['path']==str(moved)
    assert s.get_project(p['projectId'])==saved
    assert raw_tables(moved/'project.sqlite3')==expected
    assert s.asset_path(a['assetId']).read_bytes()==png()
    assert videos.path_for(v['videoId']).read_bytes()==media
    with s.connect() as db:
        assert db.execute('SELECT count(*) FROM revisions').fetchone()[0]==len(expected['revisions'])
        assert db.execute('SELECT count(*) FROM events').fetchone()[0]==len(expected['events'])
        artifacts=db.execute('SELECT path,sha256 FROM artifacts').fetchall()
    for row in artifacts:
        path=s.managed_path(row['path']);assert path.is_relative_to(moved)
        assert s.digest(path.read_bytes())==row['sha256']
    c.headers['X-Session-Token']=c.get('/v1/health').json()['sessionToken']
    opened=edit(c,opened,[{'type':'updateCharacter','name':'옮긴 뒤 편집'}])
    assert opened['characterName']=='옮긴 뒤 편집'
    fresh=run_job(queue(c,opened,'bake')['jobId'])
    assert fresh['status'] in ('succeeded','needs_review') and fresh['artifacts']
    assert s.artifact_directory(fresh['jobId']).is_relative_to(moved)
    assert not (s.DATA/'assets').exists() and not list((s.DATA/'jobs').glob('*'))


def test_failed_save_keeps_outbox_and_previous_portable_revision(client,monkeypatch):
    p=client.post('/v1/projects',json={'name':'실패 복구'}).json();root=s.project_folder(p['projectId'])
    before=(root/'project.sqlite3').read_bytes()
    def fail(path,data):raise OSError('synthetic disk failure')
    with monkeypatch.context() as m:
        m.setattr(folders,'_atomic',fail)
        r=client.patch('/v1/projects/'+p['projectId']+'/edits',json={'expectedRevision':p['revision'],'operations':[{'type':'updateCharacter','name':'보류 편집'}]})
        assert r.status_code==503 and r.json()['code']=='PROJECT_FOLDER_SYNC_FAILED'
        # A database may already have reached disk before marker fsync failed; outbox must remain.
        assert folders.storage_info(p['projectId'])['syncPending']
        assert s.get_project(p['projectId'])['characterName']=='보류 편집'
    s.init()
    assert not folders.storage_info(p['projectId'])['syncPending']
    with sqlite3.connect(root/'project.sqlite3') as db:
        assert json.loads(db.execute('SELECT snapshot FROM projects').fetchone()[0])['characterName']=='보류 편집'
    assert (root/'project.sqlite3').read_bytes()!=before


def test_missing_folder_never_recreated_by_save_or_startup(client,tmp_path):
    p=client.post('/v1/projects',json={'name':'위치 이동'}).json();root=s.project_folder(p['projectId'])
    relocated=tmp_path/'moved';root.rename(relocated)
    r=client.patch('/v1/projects/'+p['projectId']+'/edits',json={'expectedRevision':p['revision'],'operations':[{'type':'updateCharacter','name':'저장 금지'}]})
    assert r.status_code==424 and r.json()['code']=='PROJECT_FOLDER_MISSING'
    s.init();assert not root.exists()
    assert s.get_project(p['projectId'])['revision']==p['revision']
    opened=folders.open_project(str(relocated))
    assert opened['storage']['path']==str(relocated)
    assert opened['revision']==p['revision']


@pytest.mark.parametrize('damage',['asset-bytes','escape','symlink','database','foreign-project','job-path'])
def test_bad_folder_does_not_change_index(client,tmp_path,damage):
    p,a=approved(client);original=s.project_folder(p['projectId'])
    copy=tmp_path/'bad';shutil.copytree(original,copy)
    dbpath=copy/'project.sqlite3'
    with sqlite3.connect(dbpath) as db:
        relative=db.execute('SELECT path FROM assets LIMIT 1').fetchone()[0]
        if damage=='escape':db.execute("UPDATE assets SET path='../outside.png'")
        if damage=='foreign-project':db.execute("UPDATE projects SET id='foreign'")
        if damage=='job-path':db.execute("UPDATE jobs SET id='../outside'")
    if damage=='asset-bytes':(copy/relative).write_bytes(b'corrupt')
    if damage=='symlink':
        (copy/relative).unlink();(copy/relative).symlink_to(original/relative)
    if damage=='database':dbpath.write_bytes(b'not sqlite')
    before=raw_tables(s.DATA/'app.sqlite3')
    with pytest.raises(s.AppError):folders.open_project(str(copy))
    assert raw_tables(s.DATA/'app.sqlite3')==before


def test_duplicate_owns_independent_files_even_when_source_removed(client,tmp_path):
    p,a=approved(client);root=s.project_folder(p['projectId'])
    duplicate=client.post('/v1/projects/'+p['projectId']+'/duplicate',json={'name':'복제','expectedRevision':p['revision']}).json()
    other=s.project_folder(duplicate['projectId']);asset=other/folders.resource_name('assets',a['assetId'],a)
    assert asset.read_bytes()==png()
    assert asset.stat().st_ino!=(root/folders.resource_name('assets',a['assetId'],a)).stat().st_ino
    folders.detach_project(p['projectId'],p['revision']);root.rename(tmp_path/'detached')
    with s.project_scope(duplicate['projectId']):assert s.asset_path(a['assetId'])==asset
    assert run_job(queue(client,duplicate,'inspect')['jobId'])['status'] in ('succeeded','needs_review')


def test_moved_folder_recovers_pending_index_save(client,monkeypatch,tmp_path):
    p=client.post('/v1/projects',json={'name':'보류 이동'}).json();root=s.project_folder(p['projectId'])
    with monkeypatch.context() as m:
        m.setattr(folders,'_sync',lambda *args: (_ for _ in ()).throw(OSError('synthetic disk failure')))
        r=client.patch('/v1/projects/'+p['projectId']+'/edits',json={'expectedRevision':p['revision'],'operations':[{'type':'updateCharacter','name':'잃지 않을 편집'}]})
        assert r.status_code==503
    moved=tmp_path/'pending-moved';root.rename(moved)
    result=folders.open_project(str(moved))
    assert result['characterName']=='잃지 않을 편집' and result['revision']==p['revision']+1
    assert not result['storage']['syncPending']
    with sqlite3.connect(moved/'project.sqlite3') as db:
        assert json.loads(db.execute('SELECT snapshot FROM projects').fetchone()[0])['characterName']=='잃지 않을 편집'


def test_pending_save_same_path_reopen_flushes_without_losing_changes(client,monkeypatch):
    p=client.post('/v1/projects',json={'name':'보류 재열기'}).json();root=s.project_folder(p['projectId'])
    with monkeypatch.context() as m:
        m.setattr(folders,'_sync',lambda *args: (_ for _ in ()).throw(OSError('synthetic failure')))
        r=client.patch('/v1/projects/'+p['projectId']+'/edits',json={'expectedRevision':p['revision'],'operations':[{'type':'updateCharacter','name':'보존'}]})
        assert r.status_code==503
    recovered=folders.open_project(str(root));assert recovered['characterName']=='보존'
    assert not recovered['storage']['syncPending']
