"""Portable project folders; the shared SQLite is a rebuildable execution index.

Each acknowledged project/job transaction flushes its durable outbox to the
project's own SQLite. Bytes are copied before the portable database is replaced.
A failed flush stays pending and never reports a successful save to the caller.
"""
from __future__ import annotations

import json
import os
from contextlib import closing
from pathlib import Path, PurePosixPath
import re
import sqlite3
import tempfile

from . import store as s

FORMAT = 'frame-room-project'
VERSION = 1
TABLES = {
    'projects': ('id','snapshot','updated'),
    'revisions': ('project_id','revision','snapshot','created','reason'),
    'assets': ('id','metadata','path'),
    'videos': ('id','metadata','path'),
    'jobs': ('id','project_id','operation','status','request_hash','idem','body','created','updated'),
    'events': ('job_id','seq','body'),
    'artifacts': ('id','job_id','name','path','sha256','media_type'),
    'exports': ('id','job_id','project_id','body'),
    'meta': ('key','value'),
    'project_resources': ('project_id','kind','resource_id'),
}
ACTIVE = ('queued','running','cancel_requested')
MAX_DB_BYTES = 512 * 1024 * 1024


def safe_name(value):
    clean=re.sub(r'[\x00-\x1f<>:"/\\|?*]', '_',str(value)).strip(' .')
    return (clean or 'project')[:70]


def resource_name(kind, ident, metadata):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',ident):
        raise s.AppError('PROJECT_FOLDER_INVALID','리소스 ID 형식이 잘못되었습니다.')
    return f'{kind}/{ident}--{safe_name(metadata.get("originalFilename", "resource"))}'


def _atomic(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temporary=tempfile.mkstemp(prefix='.pending-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def _marker(folder):
    try:
        path=folder/'project.json'
        if path.is_symlink() or path.stat().st_size>65536:raise ValueError()
        value=json.loads(path.read_text())
        if value.get('format')!=FORMAT or value.get('formatVersion')!=VERSION or value.get('database')!='project.sqlite3':raise ValueError()
        return value
    except (OSError,ValueError,TypeError,AttributeError) as exc:
        raise s.AppError('PROJECT_FOLDER_INVALID','정상 프레임룸 프로젝트 폴더를 선택하세요.',422) from exc


def folder_for(pid,c=None):
    if c is None:
        with s.connect() as db:return folder_for(pid,db)
    row=c.execute('SELECT path,ready FROM project_folders WHERE project_id=?',(pid,)).fetchone()
    if not row:raise s.AppError('PROJECT_NOT_FOUND','프로젝트 폴더 등록을 찾을 수 없습니다.',404)
    path=Path(row['path'])
    if not row['ready']:
        raise s.AppError('PROJECT_FOLDER_PENDING','프로젝트 폴더 저장이 완료되지 않았습니다.',503)
    if not path.is_dir():
        raise s.AppError('PROJECT_FOLDER_MISSING','프로젝트 폴더가 없습니다. 이동했다면 새 위치에서 폴더 열기를 사용하세요.',424,{'path':str(path)})
    if _marker(path).get('projectId')!=pid:
        raise s.AppError('PROJECT_FOLDER_MISMATCH','등록된 위치의 프로젝트가 다릅니다.',409)
    return path


def storage_info(pid):
    with s.connect() as c:row=c.execute('SELECT path,ready FROM project_folders WHERE project_id=?',(pid,)).fetchone()
    if not row:return {'layout':'project-folder','path':'','available':False}
    available=bool(row['ready'] and Path(row['path']).is_dir() and (Path(row['path'])/'project.sqlite3').is_file())
    with s.connect() as c:pending=c.execute('SELECT 1 FROM folder_sync WHERE project_id=?',(pid,)).fetchone()
    return {'layout':'project-folder','path':row['path'],'available':available,'syncPending':bool(pending)}


def ensure_registered(c,p,parent_directory=None):
    row=c.execute('SELECT path,ready FROM project_folders WHERE project_id=?',(p['projectId'],)).fetchone()
    if row:
        if row['ready']:folder_for(p['projectId'],c)
        return Path(row['path'])
    if parent_directory:
        parent=Path(parent_directory).expanduser().resolve()
        if not parent.is_dir():raise s.AppError('PROJECT_PARENT_MISSING','프로젝트를 만들 부모 폴더가 없습니다.')
    else:
        parent=s.DATA/'projects';parent.mkdir(parents=True,exist_ok=True)
    path=parent/(safe_name(p['name'])+'--'+p['projectId'])
    if path.exists():raise s.AppError('PROJECT_FOLDER_EXISTS','같은 이름의 폴더가 이미 있습니다. 덮어쓰지 않았습니다.',409)
    c.execute('INSERT INTO project_folders VALUES (?,?,0)',(p['projectId'],str(path)))
    s.mark_folder_dirty(c,p['projectId'])
    return path


def _records(c,pid):
    rows={}
    for table,column in [('projects','id'),('revisions','project_id'),('jobs','project_id'),('exports','project_id')]:
        rows[table]=[dict(r) for r in c.execute(f'SELECT * FROM {table} WHERE {column}=?',(pid,))]
    for table in ('events','artifacts'):
        rows[table]=[dict(r) for r in c.execute(f'SELECT * FROM {table} WHERE job_id IN (SELECT id FROM jobs WHERE project_id=?)',(pid,))]
    prefix='video_batch:'+pid+':'
    rows['meta']=[dict(r) for r in c.execute('SELECT * FROM meta WHERE substr(key,1,?)=?',(len(prefix),prefix))]
    assets=set();videos=set()
    snapshots=[json.loads(r['snapshot']) for r in rows['projects']+rows['revisions']]
    snapshots += [json.loads(r['body']).get('snapshot') for r in rows['jobs']]
    for p in snapshots:
        if not p:continue
        assets.update(a['assetId'] for a in p.get('assets',[]));videos.update(v['videoId'] for v in p.get('videos',[]))
    found={'assets':{},'videos':{}}
    def collect(kind,ident):
        if not ident or ident in found[kind]:return
        row=c.execute(f'SELECT * FROM {kind} WHERE id=?',(ident,)).fetchone()
        if not row:raise s.AppError('PROJECT_RESOURCE_MISSING','프로젝트 이력에 필요한 원본 기록이 없습니다.',424,{'kind':kind,'id':ident})
        row=dict(row);found[kind][ident]=row;meta=json.loads(row['metadata']);provenance=meta.get('provenance') or {}
        for key in ('parentAssetId','baseAssetId','referenceAssetId','spillReferenceAssetId'):
            collect('assets',provenance.get(key))
        collect('videos',provenance.get('sourceVideoId'))
    for aid in assets:collect('assets',aid)
    for vid in videos:collect('videos',vid)
    for row in c.execute('SELECT kind,resource_id FROM project_resources WHERE project_id=?',(pid,)):
        collect(row['kind'],row['resource_id'])
    # Legacy completed attempts may not have been published into a snapshot yet.
    registration=c.execute('SELECT path,ready FROM project_folders WHERE project_id=?',(pid,)).fetchone()
    if registration and not registration['ready']:
        for job in rows['jobs']:
            for result in (s.DATA/'jobs'/job['id']).glob('*/result.json'):
                try:payload=json.loads(result.read_text()).get('result') or {}
                except (OSError,ValueError):continue
                for asset in payload.get('assets',[]):collect('assets',asset.get('assetId'))
                collect('videos',payload.get('videoId'))
    rows.update({kind:list(items.values()) for kind,items in found.items()})
    rows['project_resources']=[{'project_id':pid,'kind':kind,'resource_id':ident} for kind,items in found.items() for ident in items]
    return rows


def resource_path(kind,ident,row):
    meta=json.loads(row['metadata']);relative=resource_name(kind,ident,meta)
    pid=s._project_scope.get()
    if pid:
        target=folder_for(pid)/relative
        if target.is_file() and not target.is_symlink():return target
    candidate=(s.DATA/row['path']).resolve()
    with s.connect() as c:roots=[Path(r[0]) for r in c.execute('SELECT path FROM project_folders WHERE ready=1')]
    if candidate.is_file() and (candidate.is_relative_to(s.DATA) or any(candidate.is_relative_to(root) for root in roots)):
        return candidate
    for root in roots:
        target=root/relative
        if target.is_file() and not target.is_symlink():return target
    raise s.AppError('ASSET_MISSING' if kind=='assets' else 'VIDEO_MISSING','프로젝트 원본 파일을 찾을 수 없습니다.',424,{'id':ident})


def _copy_file(source,target,expected=None):
    if target.is_symlink() or source.is_symlink():raise s.AppError('PROJECT_FOLDER_PATH','프로젝트 리소스의 심볼릭 링크는 지원하지 않습니다.')
    if target.exists():
        if expected and s.digest(target.read_bytes())!=expected:raise s.AppError('PROJECT_RESOURCE_HASH','프로젝트 파일의 해시가 다릅니다.',424,{'file':str(target)})
        return
    if not source.is_file():raise s.AppError('PROJECT_RESOURCE_MISSING','프로젝트에 필요한 파일이 없습니다.',424,{'file':str(source)})
    target.parent.mkdir(parents=True,exist_ok=True)
    data=source.read_bytes()
    if expected and s.digest(data)!=expected:raise s.AppError('PROJECT_RESOURCE_HASH','원본 파일의 해시가 다릅니다.',424,{'file':str(source)})
    _atomic(target,data)


def _copy_tree(source,target):
    if not source.exists() or source.resolve()==target.resolve():return
    for path in source.rglob('*'):
        if path.is_symlink():raise s.AppError('PROJECT_FOLDER_PATH','프로젝트 작업 파일의 심볼릭 링크는 지원하지 않습니다.')
        if path.is_file():_copy_file(path,target/path.relative_to(source))


def _sync(c,pid):
    registration=c.execute('SELECT * FROM project_folders WHERE project_id=?',(pid,)).fetchone()
    if not registration:return
    folder=Path(registration['path'])
    if registration['ready']:folder_for(pid,c)
    else:
        if folder.exists():
            if _marker(folder).get('projectId')!=pid:raise s.AppError('PROJECT_FOLDER_EXISTS','다른 프로젝트 폴더를 덮어쓰지 않았습니다.',409)
        else:folder.mkdir()
        _atomic(folder/'project.json',s.dumps({'format':FORMAT,'formatVersion':VERSION,'projectId':pid,'database':'project.sqlite3'}).encode())
    rows=_records(c,pid)
    if not rows['projects']:return
    snapshot=json.loads(rows['projects'][0]['snapshot'])
    c.executemany('INSERT OR IGNORE INTO project_resources VALUES (?,?,?)',[(pid,r['kind'],r['resource_id']) for r in rows['project_resources']])
    for kind in ('assets','videos'):
        for row in rows[kind]:
            meta=json.loads(row['metadata']);relative=resource_name(kind,row['id'],meta);target=folder/relative
            source=(s.DATA/row['path']).resolve()
            if not target.exists() and not source.is_file():source=resource_path(kind,row['id'],row)
            _copy_file(source,target,meta['sha256']);row['path']=relative
            c.execute(f'UPDATE {kind} SET path=? WHERE id=?',(s.stored_path(target),row['id']))
    for row in rows['jobs'] if not registration['ready'] else []:
        jid=row['id']
        _copy_tree(s.DATA/'jobs'/jid,folder/'jobs'/jid)
        _copy_tree(s.DATA/'artifacts'/jid,folder/'outputs'/jid)
    for row in rows['artifacts']:
        parts=Path(row['path']).parts;relative=None
        for kind in ('artifacts','outputs'):
            for i in range(len(parts)-1):
                if parts[i:i+2]==(kind,row['job_id']):relative=Path('outputs').joinpath(*parts[i+1:]);break
            if relative is not None:break
        if relative is None:raise s.AppError('PROJECT_FOLDER_PATH','출력 파일의 작업 경로를 확인할 수 없습니다.')
        source=(s.DATA/row['path']).resolve();target=folder/relative
        _copy_file(source,target,row['sha256']);row['path']=relative.as_posix()
        c.execute('UPDATE artifacts SET path=? WHERE id=?',(s.stored_path(target),row['id']))
    for name in ('assets','videos','jobs','outputs'):(folder/name).mkdir(exist_ok=True)
    temporary=folder/('.project-'+s.uid()+'.sqlite3')
    try:
        with closing(sqlite3.connect(temporary)) as portable:
            for table,columns in TABLES.items():
                schema=c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()[0]
                portable.execute(schema)
                if rows[table]:portable.executemany(f'INSERT INTO {table} ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})',[tuple(row[col] for col in columns) for row in rows[table]])
            portable.commit()
        with temporary.open('rb') as f:os.fsync(f.fileno())
        os.replace(temporary,folder/'project.sqlite3')
        _atomic(folder/'project.json',s.dumps({'format':FORMAT,'formatVersion':VERSION,'projectId':pid,'name':snapshot['name'],'database':'project.sqlite3','revision':snapshot['revision'],'updatedAt':snapshot['updatedAt']}).encode())
        c.execute('UPDATE project_folders SET ready=1 WHERE project_id=?',(pid,))
    finally:
        temporary.unlink(missing_ok=True)


def flush(project_ids,*,strict=True):
    errors=[]
    for pid in sorted(set(project_ids)):
        with s.connect() as c:
            try:
                c.execute('BEGIN IMMEDIATE')
                if c.execute('SELECT 1 FROM folder_sync WHERE project_id=?',(pid,)).fetchone():
                    _sync(c,pid);c.execute('DELETE FROM folder_sync WHERE project_id=?',(pid,))
                c.commit()
            except Exception as exc:
                c.rollback();errors.append(exc)
    if errors and strict:
        raise s.AppError('PROJECT_FOLDER_SYNC_FAILED','프로젝트 폴더에 저장을 완료하지 못했습니다. 폴더 위치·권한·여유 공간을 확인하세요. 앱 인덱스의 보류 데이터는 유지됩니다.',503,{'reason':getattr(errors[0],'code',type(errors[0]).__name__)}) from errors[0]


def migrate_legacy():
    with s.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        for row in c.execute('SELECT snapshot FROM projects').fetchall():
            p=json.loads(row[0])
            if not c.execute('SELECT 1 FROM project_folders WHERE project_id=?',(p['projectId'],)).fetchone():ensure_registered(c,p)
        pending=[r[0] for r in c.execute('SELECT project_id FROM folder_sync')]
        c.commit()
    flush(pending,strict=False)


def _safe_relative(folder,value):
    p=PurePosixPath(value)
    if p.is_absolute() or '..' in p.parts or '\\' in value or ':' in value:raise s.AppError('PROJECT_FOLDER_PATH','프로젝트 경로가 폴더 밖을 참조합니다.')
    target=folder.joinpath(*p.parts)
    descendants=[target,*[parent for parent in target.parents if parent.is_relative_to(folder)]]
    if not target.resolve().is_relative_to(folder) or any(parent.is_symlink() for parent in descendants):
        raise s.AppError('PROJECT_FOLDER_PATH','프로젝트 리소스는 폴더 안의 실제 파일이어야 합니다.')
    return target


def _read(folder):
    marker=_marker(folder);database=folder/'project.sqlite3'
    if database.is_symlink() or not database.is_file() or database.stat().st_size>MAX_DB_BYTES:
        raise s.AppError('PROJECT_FOLDER_INVALID','프로젝트 SQLite가 없거나 지원 크기를 넘었습니다.')
    try:
        with closing(sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1',uri=True)) as db:
            db.row_factory=sqlite3.Row;db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA query_only=ON')
            if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError()
            rows={}
            for table,columns in TABLES.items():
                if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():raise ValueError()
                result=db.execute(f'SELECT {",".join(columns)} FROM {table}').fetchmany(200001)
                if len(result)>200000:raise ValueError()
                rows[table]=[dict(row) for row in result]
        if len(rows['projects'])!=1:raise ValueError()
        project=rows['projects'][0];pid=project['id'];snapshot=s.validate_snapshot(json.loads(project['snapshot']))
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',pid):raise ValueError()
        if snapshot['projectId']!=pid or marker.get('projectId')!=pid:raise ValueError()
        for row in rows['revisions']:
            if row['project_id']!=pid or json.loads(row['snapshot']).get('projectId')!=pid:raise ValueError()
            s.validate_snapshot(json.loads(row['snapshot']))
        jobs={r['id'] for r in rows['jobs']}
        for row in rows['jobs']:
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',row['id']):raise ValueError()
            body=json.loads(row['body'])
            if row['project_id']!=pid or body.get('projectId')!=pid or body.get('jobId')!=row['id']:raise ValueError()
            if body.get('snapshot'):
                if body['snapshot'].get('projectId')!=pid:raise ValueError()
                s.validate_snapshot(body['snapshot'])
        for table in ('events','artifacts','exports'):
            for row in rows[table]:
                if row['job_id'] not in jobs:raise ValueError()
                if table=='exports' and row['project_id']!=pid:raise ValueError()
        for row in rows['meta']:
            if not row['key'].startswith('video_batch:'+pid+':'):raise ValueError()
        for kind in ('assets','videos'):
            for row in rows[kind]:
                meta=json.loads(row['metadata']);key='assetId' if kind=='assets' else 'videoId'
                if meta.get(key)!=row['id'] or not row['path'].startswith(kind+'/'):raise ValueError()
                resource_name(kind,row['id'],meta)
                path=_safe_relative(folder,row['path'])
                if not path.is_file() or s.digest(path.read_bytes())!=meta['sha256']:raise s.AppError('PROJECT_RESOURCE_HASH','폴더의 원본 파일이 없거나 해시가 다릅니다.',424,{'file':row['path']})
        for row in rows['artifacts']:
            path=_safe_relative(folder,row['path'])
            if not row['path'].startswith('outputs/'+row['job_id']+'/') or not path.is_file() or s.digest(path.read_bytes())!=row['sha256']:
                raise s.AppError('PROJECT_RESOURCE_HASH','폴더의 출력 파일이 없거나 해시가 다릅니다.',424,{'file':row['path']})
        for directory in ('assets','videos','jobs','outputs'):
            if (folder/directory).is_symlink():raise s.AppError('PROJECT_FOLDER_PATH','프로젝트 폴더의 심볼릭 링크는 지원하지 않습니다.')
            for path in (folder/directory).rglob('*'):
                if path.is_symlink():raise s.AppError('PROJECT_FOLDER_PATH','프로젝트 폴더의 심볼릭 링크는 지원하지 않습니다.')
        indexed_assets={r['id'] for r in rows['assets']};indexed_videos={r['id'] for r in rows['videos']}
        for row in rows['project_resources']:
            if row['project_id']!=pid or row['kind'] not in ('assets','videos') or row['resource_id'] not in (indexed_assets if row['kind']=='assets' else indexed_videos):raise ValueError()
        for p in [snapshot,*[json.loads(r['snapshot']) for r in rows['revisions']],*[json.loads(r['body']).get('snapshot') for r in rows['jobs']]]:
            if not p:continue
            if any(a['assetId'] not in indexed_assets for a in p['assets']) or any(v['videoId'] not in indexed_videos for v in p.get('videos',[])):raise ValueError()
        for kind in ('assets','videos'):
            for row in rows[kind]:
                provenance=json.loads(row['metadata']).get('provenance') or {}
                if any(provenance.get(key) and provenance[key] not in indexed_assets for key in ('parentAssetId','baseAssetId','referenceAssetId','spillReferenceAssetId')):raise ValueError()
                if provenance.get('sourceVideoId') and provenance['sourceVideoId'] not in indexed_videos:raise ValueError()
        return rows,snapshot
    except (sqlite3.Error,ValueError,KeyError,TypeError,OSError) as exc:
        raise s.AppError('PROJECT_FOLDER_INVALID','프로젝트 SQLite 또는 폴더 데이터가 손상되었습니다.') from exc


def _remove_index(c,pid):
    for table in ('events','artifacts'):
        c.execute(f'DELETE FROM {table} WHERE job_id IN (SELECT id FROM jobs WHERE project_id=?)',(pid,))
    for table,column in [('exports','project_id'),('jobs','project_id'),('revisions','project_id'),('projects','id'),('project_folders','project_id'),('folder_sync','project_id'),('project_resources','project_id')]:
        c.execute(f'DELETE FROM {table} WHERE {column}=?',(pid,))
    prefix='video_batch:'+pid+':'
    c.execute('DELETE FROM meta WHERE substr(key,1,?)=?',(len(prefix),prefix))


def _prune(c):
    if c.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running','cancel_requested') LIMIT 1").fetchone():return
    keep={'assets':set(),'videos':set()}
    for row in c.execute('SELECT id FROM projects').fetchall():
        records=_records(c,row['id'])
        for kind in keep:keep[kind].update(r['id'] for r in records[kind])
    for kind,ids in keep.items():
        for row in c.execute(f'SELECT id FROM {kind}').fetchall():
            if row[0] not in ids:c.execute(f'DELETE FROM {kind} WHERE id=?',(row[0],))


def _busy(c,pid):
    if c.execute("SELECT 1 FROM jobs WHERE project_id=? AND status IN ('queued','running','cancel_requested') LIMIT 1",(pid,)).fetchone():
        raise s.AppError('PROJECT_BUSY','작업이 끝나거나 취소된 후 목록에서 제거하세요.',409)


def detach_project(pid,expected_revision):
    # A prior failed save must reach the existing folder before its cache is removed.
    flush([pid])
    with s.transaction() as c:
        p=s.get_project(pid,c);s.check_revision(p,expected_revision);_busy(c,pid)
        folder_for(pid,c)
        _remove_index(c,pid);_prune(c)
    return {'deletedProjectId':pid}


def missing_projects():
    with s.connect() as c:
        rows=c.execute('SELECT f.project_id,f.path,p.snapshot FROM project_folders f JOIN projects p ON p.id=f.project_id').fetchall()
    return {'projects':[{'projectId':r['project_id'],'name':json.loads(r['snapshot'])['name'],'path':r['path'],'revision':json.loads(r['snapshot'])['revision']} for r in rows if not Path(r['path']).is_dir()]}


def cleanup_missing(items):
    if len(items)>1000 or len({i['projectId'] for i in items})!=len(items):raise s.AppError('PROJECT_CLEANUP_INVALID','정리 대상이 중복되거나 너무 많습니다.')
    if not items:return {'removedProjectIds':[],'removedCount':0}
    with s.transaction() as c:
        for item in items:
            pid=item['projectId'];p=s.get_project(pid,c);s.check_revision(p,item['expectedRevision']);_busy(c,pid)
            row=c.execute('SELECT path FROM project_folders WHERE project_id=?',(pid,)).fetchone()
            if not row or row['path']!=item['path'] or Path(row['path']).is_dir():
                raise s.AppError('PROJECT_CLEANUP_CHANGED','폴더 위치나 존재 여부가 바뀌었습니다. 정리 대상을 다시 확인하세요.',409)
        for item in items:_remove_index(c,item['projectId'])
        _prune(c)
    return {'removedProjectIds':[item['projectId'] for item in items],'removedCount':len(items)}


def open_project(value):
    folder=Path(value).expanduser().resolve()
    if folder.name in ('project.json','project.sqlite3'):folder=folder.parent
    if not folder.is_dir():raise s.AppError('PROJECT_FOLDER_MISSING','선택한 프로젝트 폴더가 없습니다.',404)
    rows,p=_read(folder);pid=p['projectId']
    # Recover an acknowledged-in-index but unflushed save after its folder was
    # moved or its disk became available again. Never replace it with old disk data.
    with s.transaction() as c:
        old=c.execute('SELECT path FROM project_folders WHERE project_id=?',(pid,)).fetchone()
        pending=old and c.execute('SELECT 1 FROM folder_sync WHERE project_id=?',(pid,)).fetchone()
        if pending:
            if Path(old['path']).resolve()!=folder and Path(old['path']).is_dir():raise s.AppError('PROJECT_ALREADY_OPEN','같은 프로젝트가 다른 폴더에서 열려 있습니다.',409)
            _busy(c,pid)
            cached=s.get_project(pid,c)
            if p['revision']>cached['revision']:raise s.AppError('PROJECT_FOLDER_CONFLICT','폴더와 앱에 각각 다른 보류 편집이 있습니다. 두 데이터를 보존했습니다.',409)
            c.execute('UPDATE project_folders SET path=?,ready=1 WHERE project_id=?',(str(folder),pid))
            s.mark_folder_dirty(c,pid)
    if pending:return s.public_project(s.get_project(pid))
    with s.transaction() as c:
        old=c.execute('SELECT path FROM project_folders WHERE project_id=?',(pid,)).fetchone()
        if old and Path(old['path']).resolve()==folder:return s.public_project(s.get_project(pid,c))
        if old and Path(old['path']).is_dir():raise s.AppError('PROJECT_ALREADY_OPEN','같은 프로젝트가 다른 폴더에서 열려 있습니다. 먼저 목록에서 제거하거나 프로젝트 복제를 사용하세요.',409,{'path':old['path']})
        _busy(c,pid)
        # Resource IDs can be shared by a genuine project duplicate, but their bytes must agree.
        for kind in ('assets','videos'):
            for row in rows[kind]:
                existing=c.execute(f'SELECT metadata FROM {kind} WHERE id=?',(row['id'],)).fetchone()
                if existing and json.loads(existing[0])['sha256']!=json.loads(row['metadata'])['sha256']:
                    raise s.AppError('PROJECT_ID_CONFLICT','이미 등록된 원본 ID와 파일이 다릅니다.',409)
        for table,key in [('jobs','id'),('artifacts','id'),('exports','id')]:
            for row in rows[table]:
                if table=='artifacts':existing=c.execute('SELECT j.project_id FROM artifacts a JOIN jobs j ON j.id=a.job_id WHERE a.id=?',(row[key],)).fetchone()
                else:existing=c.execute(f'SELECT project_id FROM {table} WHERE id=?',(row[key],)).fetchone()
                if existing and existing[0]!=pid:raise s.AppError('PROJECT_ID_CONFLICT','다른 프로젝트의 작업 기록 ID와 충돌합니다.',409)
        if old:_remove_index(c,pid)
        for table,columns in TABLES.items():
            for original in rows[table]:
                row=dict(original)
                if table in ('assets','videos','artifacts'):row['path']=s.stored_path(_safe_relative(folder,row['path']))
                if table=='jobs' and row['status'] in ACTIVE:
                    body=json.loads(row['body']);body.update(status='interrupted',step='stopped',errors=[{'code':'PROJECT_REOPENED','message':'폴더를 다시 열었습니다. 기존 작업 상태를 확인한 후 명시적으로 재개하세요.'}]);body.pop('childPid',None)
                    row.update(status='interrupted',body=s.dumps(body))
                c.execute(f'INSERT OR REPLACE INTO {table} ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})',tuple(row[col] for col in columns))
        c.execute('INSERT INTO project_folders VALUES (?,?,1)',(pid,str(folder)))
        s.mark_folder_dirty(c,pid)
    return s.public_project(s.get_project(pid))
