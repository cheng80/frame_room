"""Transactional local state. Published bytes and revision snapshots are immutable."""
from __future__ import annotations
import contextlib, hashlib, io, json, os, sqlite3, tempfile, uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get('SPRITE_DATA_DIR', str(ROOT / '.data'))).resolve()
COMMIT = 'b058341f7543f3adcbea227bd4e6b7587895b1bc'
_project_scope = ContextVar('frame_room_project_scope', default=None)
class StoreConnection(sqlite3.Connection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dirty_projects = set()
def uid(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc).isoformat()
def dumps(x): return json.dumps(x, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
def digest(x): return hashlib.sha256(x).hexdigest()
class AppError(Exception):
    def __init__(self, code, message, status=422, details=None, stage='validation'):
        self.code, self.message, self.status, self.details, self.stage = code, message, status, details or {}, stage
    def payload(self): return dict(code=self.code,message=self.message,stage=self.stage,details=self.details,retryable=False,affectedIds=self.details.get('affectedIds',[]),nextActions=[])

def connect():
    DATA.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DATA/'app.sqlite3',timeout=30,isolation_level=None,factory=StoreConnection)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA synchronous=FULL')
    return c

def init():
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,snapshot TEXT NOT NULL,updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS revisions(project_id TEXT,revision INTEGER,snapshot TEXT,created TEXT,reason TEXT,PRIMARY KEY(project_id,revision));
        CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,metadata TEXT NOT NULL,path TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS videos(id TEXT PRIMARY KEY,metadata TEXT NOT NULL,path TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,project_id TEXT,operation TEXT,status TEXT,request_hash TEXT,idem TEXT,body TEXT NOT NULL,created TEXT,updated TEXT,UNIQUE(project_id,operation,idem));
        CREATE TABLE IF NOT EXISTS events(job_id TEXT,seq INTEGER,body TEXT,PRIMARY KEY(job_id,seq));
        CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY,job_id TEXT,name TEXT,path TEXT,sha256 TEXT,media_type TEXT);
        CREATE TABLE IF NOT EXISTS exports(id TEXT PRIMARY KEY,job_id TEXT,project_id TEXT,body TEXT);
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS project_folders(project_id TEXT PRIMARY KEY,path TEXT UNIQUE NOT NULL,ready INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS folder_sync(project_id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS project_resources(project_id TEXT,kind TEXT,resource_id TEXT,PRIMARY KEY(project_id,kind,resource_id));
        ''')
        c.execute('INSERT OR IGNORE INTO meta VALUES (?,?)',('session_token',uid()+uid()))
    from . import project_folders
    project_folders.migrate_legacy()

@contextlib.contextmanager
def transaction():
    c=connect()
    try:
        c.execute('BEGIN IMMEDIATE'); yield c; c.commit()
    except BaseException: c.rollback(); raise
    finally: c.close()
    if c.dirty_projects:
        from .project_folders import flush
        flush(c.dirty_projects)

def mark_folder_dirty(c, pid):
    if pid:
        c.execute('INSERT OR IGNORE INTO folder_sync VALUES (?)',(pid,))
        c.dirty_projects.add(pid)

def own_resource(c,pid,kind,ident):
    if pid:
        c.execute('INSERT OR IGNORE INTO project_resources VALUES (?,?,?)',(pid,kind,ident))
        mark_folder_dirty(c,pid)

@contextlib.contextmanager
def project_scope(pid):
    token=_project_scope.set(pid or None)
    try: yield
    finally: _project_scope.reset(token)

def project_folder(pid,c=None):
    from .project_folders import folder_for
    return folder_for(pid,c)

def public_project(p):
    from .project_folders import storage_info
    return {**p,'storage':storage_info(p['projectId'])}

def stored_path(path):
    path=Path(path).resolve()
    return str(path.relative_to(DATA)) if path.is_relative_to(DATA) else str(path)

def managed_path(value):
    path=(DATA/str(value)).resolve()
    if path.is_relative_to(DATA): return path
    with connect() as c: roots=[Path(r[0]).resolve() for r in c.execute('SELECT path FROM project_folders')]
    if any(path.is_relative_to(root) for root in roots): return path
    raise AppError('STORAGE_ESCAPE','등록된 프로젝트 폴더 밖의 경로입니다.')

def job_directory(jid):
    job=get_job(jid)
    return (project_folder(job['projectId'])/'jobs' if job.get('projectId') else DATA/'jobs')/jid

def artifact_directory(jid):
    job=get_job(jid)
    return (project_folder(job['projectId'])/'outputs' if job.get('projectId') else DATA/'artifacts')/jid

def resolve_work_path(jid,value):
    path=Path(value)
    for family,root in [('jobs',job_directory(jid)),('artifacts',artifact_directory(jid)),('outputs',artifact_directory(jid))]:
        parts=path.parts
        for i in range(len(parts)-1):
            if parts[i:i+2]==(family,jid):
                target=root.joinpath(*parts[i+2:]).resolve()
                if target.is_relative_to(root.resolve()): return target
    if not path.is_absolute():
        root=job_directory(jid);target=(root/path).resolve()
        if target.is_relative_to(root.resolve()): return target
    raise AppError('CHECKPOINT_PATH','체크포인트 경로가 작업 폴더를 벗어났습니다.')

def get_project(pid,c=None):
    if c is None:
        with connect() as cc: return get_project(pid,cc)
    row=c.execute('SELECT snapshot FROM projects WHERE id=?',(pid,)).fetchone()
    if not row: raise AppError('PROJECT_NOT_FOUND','프로젝트를 찾을 수 없습니다.',404)
    p=json.loads(row[0])
    if p.get('schemaVersion') != 1: raise AppError('SCHEMA_UNSUPPORTED','지원하지 않는 프로젝트 버전입니다.',422)
    p.setdefault('videos',[])
    return p

def check_revision(p,expected):
    if type(expected) is not int or expected!=p['revision']:
        raise AppError('REVISION_CONFLICT','다른 변경이 저장되었습니다. 초안을 유지한 채 최신 버전을 확인하세요.',409,{'expectedRevision':expected,'savedRevision':p['revision']})

def write_project(c,p,reason,initial=False):
    from .project_folders import ensure_registered
    ensure_registered(c,p)
    p.pop('storage',None)
    if not initial: p['revision']+=1
    p['updatedAt']=now()
    p.setdefault('journal',[]).append({'revision':p['revision'],'parentRevision':p['revision']-1,'reason':reason,'createdAt':now()})
    value=dumps(p)
    c.execute('INSERT INTO projects VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot,updated=excluded.updated',(p['projectId'],value,p['updatedAt']))
    c.execute('INSERT INTO revisions VALUES (?,?,?,?,?)',(p['projectId'],p['revision'],value,now(),reason))
    mark_folder_dirty(c,p['projectId'])
    return p

def create_project(name,character_name,cell=None,parent_directory=None):
    if not name.strip(): raise AppError('NAME_REQUIRED','프로젝트 이름을 입력하세요.')
    p=dict(projectId=uid(),schemaVersion=1,revision=1,name=name.strip()[:200],characterName=character_name[:200],createdAt=now(),updatedAt=now(),assets=[],references=[],activeReferenceRevisionId=None,frames=[],alignmentGroups=[],alignments={},clips=[],outline=dict(enabled=False,mode='preview-only',teamLabel='청팀',colorRGBA=[66,190,255,255],thicknessPx=2,directions=8,opacityPerCopy=.8,rendererVersion='outline-v1'),generationSettings={},journal=[],generations=[],defaultCell=cell or {'width':512,'height':512})
    p['videos']=[]
    with transaction() as c:
        from .project_folders import ensure_registered
        ensure_registered(c,p,parent_directory)
        write_project(c,p,'프로젝트 생성',True)
    return public_project(p)

def atomic_bytes(path,data):
    path=Path(path)
    managed_path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    managed_path(path.parent)
    fd,tmp=tempfile.mkstemp(prefix='.pending-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def validate_image(data,filename):
    if len(data)>32*1024*1024: raise AppError('UPLOAD_LIMIT','이미지는 파일당 32 MiB 이하로 선택하세요.',413)
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.format not in ('PNG','WEBP'): raise AppError('IMAGE_FORMAT','PNG 또는 WebP만 지원합니다.')
            w,h=im.size
            if max(w,h)>8192 or w*h>64_000_000: raise AppError('IMAGE_DIMENSIONS','8192px·64M 픽셀 한도를 초과했습니다.',413)
            im.load(); rgba=im.convert('RGBA'); alpha=rgba.getchannel('A').histogram()
            return dict(sha256=digest(data),decodedHash=digest(rgba.tobytes()),originalFilename=Path(filename).name[:250],mediaType='image/png' if im.format=='PNG' else 'image/webp',width=w,height=h,alphaStats=dict(transparent=alpha[0],partial=sum(alpha[1:255]),opaque=alpha[255]))
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError) as e:
        raise AppError('IMAGE_DECODE','이미지를 읽을 수 없습니다. 정상 PNG/WebP 파일을 선택하세요.') from e

def register_asset(data,filename,role='source',provenance=None,metadata=None,c=None,project_id=None):
    meta=dict(metadata or validate_image(data,filename))
    aid=uid(); path=DATA/'assets'/meta['sha256'][:2]/meta['sha256']
    pid=project_id or _project_scope.get()
    if pid:
        from .project_folders import resource_name
        path=project_folder(pid,c)/resource_name('assets',aid,meta)
    if not path.exists(): atomic_bytes(path,data)
    elif digest(path.read_bytes())!=meta['sha256']: raise AppError('ASSET_HASH','기존 원본의 해시가 일치하지 않습니다.',424)
    meta.update(assetId=aid,role=role,url=f'/v1/assets/{aid}/content',provenance=provenance or {'kind':'imported'})
    if c is None:
        with transaction() as cc:
            cc.execute('INSERT INTO assets VALUES (?,?,?)',(aid,dumps(meta),stored_path(path)))
            own_resource(cc,pid,'assets',aid)
    else:
        c.execute('INSERT INTO assets VALUES (?,?,?)',(aid,dumps(meta),stored_path(path)))
        own_resource(c,pid,'assets',aid)
    return meta

def asset_path(aid):
    with connect() as c: row=c.execute('SELECT path,metadata FROM assets WHERE id=?',(aid,)).fetchone()
    if not row: raise AppError('ASSET_MISSING','원본 자료가 없습니다.',424,{'assetId':aid})
    from .project_folders import resource_path
    path=resource_path('assets',aid,row)
    if digest(path.read_bytes())!=json.loads(row['metadata'])['sha256']: raise AppError('ASSET_HASH','원본 파일의 해시가 변경되었습니다.',424,{'assetId':aid})
    return path

def get_job(jid,c=None):
    if c is None:
        with connect() as cc: return get_job(jid,cc)
    row=c.execute('SELECT body FROM jobs WHERE id=?',(jid,)).fetchone()
    if not row: raise AppError('JOB_NOT_FOUND','작업을 찾을 수 없습니다.',404)
    return json.loads(row[0])

def write_job(c,j):
    j['updatedAt']=now(); j['eventSeq']=j.get('eventSeq',0)+1
    c.execute('UPDATE jobs SET status=?,body=?,updated=? WHERE id=?',(j['status'],dumps(j),j['updatedAt'],j['jobId']))
    public=public_job(j)
    c.execute('INSERT INTO events VALUES (?,?,?)',(j['jobId'],j['eventSeq'],dumps(public)))
    mark_folder_dirty(c,j.get('projectId'))

def public_job(j):
    public={k:v for k,v in j.items() if k not in ('snapshot','request')}
    if j.get('operation') in ('inspect','bake','export'):
        request=j.get('request') or {}; params=request.get('params') or {}
        clips=(j.get('snapshot') or {}).get('clips',[])
        if 'clipIds' in params:
            selected=params['clipIds']
        else:
            revisions=request.get('clipRevisionIds',params.get('clipRevisionIds'))
            selected=[cl.get('clipId') for cl in clips if revisions is None or
                      isinstance(revisions,list) and cl.get('clipRevisionId') in revisions]
        # Computed on read from the immutable attempt input, including old jobs.
        # Only opaque clip IDs cross the public boundary; never request/snapshot.
        public['inspectionClipIds']=list(dict.fromkeys(
            cid for cid in selected if isinstance(cid,str) and cid
        )) if isinstance(selected,list) else []
    if j.get('operation')=='extract':
        result=j.get('result') or {}
        revision=result.get('savedRevision'); project_id=j.get('projectId')
        if 'frameVersionIds' not in result and type(revision) is int and revision>1 and isinstance(project_id,str):
            with connect() as c:
                rows=c.execute('SELECT revision,snapshot,reason FROM revisions WHERE project_id=? AND revision IN (?,?)',
                               (project_id,revision-1,revision)).fetchall()
            revisions={row['revision']:row for row in rows}
            if revision-1 in revisions and revision in revisions and revisions[revision]['reason']=='extract 결과 등록':
                before=json.loads(revisions[revision-1]['snapshot']); after=json.loads(revisions[revision]['snapshot'])
                if before.get('projectId')==project_id and after.get('projectId')==project_id:
                    prior_ids={f['frameVersionId'] for f in before.get('frames',[])}
                    added=[f['frameVersionId'] for f in after.get('frames',[]) if f['frameVersionId'] not in prior_ids]
                    public['result']={**result,'frameVersionIds':added}
    return public

def validate_snapshot(p):
    """Reject broken portable state before any restored project is published."""
    if not isinstance(p,dict) or p.get('schemaVersion')!=1: raise AppError('SCHEMA_UNSUPPORTED','지원하지 않는 프로젝트 버전입니다.')
    p.setdefault('videos',[])
    for key in ('assets','references','frames','alignmentGroups','clips','generations','journal','videos'):
        if not isinstance(p.get(key),list): raise AppError('SNAPSHOT_INVALID',f'백업의 {key} 목록이 잘못되었습니다.')
    if not isinstance(p.get('alignments'),dict) or not isinstance(p.get('name'),str): raise AppError('SNAPSHOT_INVALID','백업 프로젝트 형식이 잘못되었습니다.')
    def ids(key,field):
        values=[x.get(field) for x in p[key] if isinstance(x,dict)]
        if len(values)!=len(p[key]) or any(not isinstance(v,str) or not v for v in values) or len(values)!=len(set(values)): raise AppError('SNAPSHOT_IDS','백업 ID가 없거나 중복됩니다.')
        return set(values)
    assets=ids('assets','assetId'); refs=ids('references','referenceRevisionId'); frames=ids('frames','frameVersionId'); groups=ids('alignmentGroups','alignmentGroupId'); ids('clips','clipId')
    videos=ids('videos','videoId')
    def require(value,allowed):
        if value not in allowed: raise AppError('SNAPSHOT_REFERENCE','백업에서 참조하는 필수 항목이 없습니다.')
    for r in p['references']:
        require(r.get('identityAssetId'),assets)
        for a in r.get('styleAssetIds',[])+r.get('poseAssetIds',[]): require(a,assets)
    if p.get('activeReferenceRevisionId'): require(p['activeReferenceRevisionId'],refs)
    for f in p['frames']:
        require(f.get('imageAssetId'),assets); require(f.get('rawAssetId'),assets); require(f.get('nativeScaleGroupId'),groups)
    for g in p['alignmentGroups']:
        for fid in g.get('frameVersionIds',[]): require(fid,frames)
    occurrences=set()
    for cl in p['clips']:
        if cl.get('referenceRevisionId'): require(cl['referenceRevisionId'],refs)
        if cl.get('sourceVideoId'): require(cl['sourceVideoId'],videos)
        for o in cl.get('occurrences',[]):
            require(o.get('frameVersionId'),frames)
            if not isinstance(o.get('occurrenceId'),str) or o['occurrenceId'] in occurrences: raise AppError('SNAPSHOT_IDS','재생 슬롯 ID가 잘못되었습니다.')
            occurrences.add(o['occurrenceId'])
            if type(o.get('durationMs')) is not int or not 1<=o['durationMs']<=60000: raise AppError('SNAPSHOT_TIMING','프레임 시간이 잘못되었습니다.')
    for fid in p['alignments']: require(fid,frames)
    for item in p['assets']+p['frames']+p['generations']:
        if item.get('sourceVideoId'): require(item['sourceVideoId'],videos)
        provenance=item.get('provenance',{})
        if isinstance(provenance,dict) and provenance.get('sourceVideoId'): require(provenance['sourceVideoId'],videos)
        if isinstance(provenance,dict) and provenance.get('spillReferenceAssetId'): require(provenance['spillReferenceAssetId'],assets)
    for video in p['videos']:
        provenance=video.get('provenance',{})
        if not isinstance(provenance,dict): raise AppError('SNAPSHOT_INVALID','영상 출처 형식이 잘못되었습니다.')
        for key in ('baseAssetId','referenceAssetId'):
            if provenance.get(key): require(provenance[key],assets)
        if provenance.get('referenceRevisionId'): require(provenance['referenceRevisionId'],refs)
    return p

def remap_reference_ids(p):
    mapping={r['referenceRevisionId']:uid() for r in p['references']}
    def visit(v):
        if isinstance(v,dict): return {k:visit(x) for k,x in v.items()}
        if isinstance(v,list): return [visit(x) for x in v]
        if isinstance(v,str): return mapping.get(v,v)
        return v
    return visit(p)
