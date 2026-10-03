"""Transactional local state. Published bytes and revision snapshots are immutable."""
from __future__ import annotations
import contextlib, hashlib, io, json, os, sqlite3, tempfile, uuid
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get('SPRITE_DATA_DIR', str(ROOT / '.data'))).resolve()
COMMIT = 'b058341f7543f3adcbea227bd4e6b7587895b1bc'
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
    c=sqlite3.connect(DATA/'app.sqlite3',timeout=30,isolation_level=None)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA synchronous=FULL')
    return c

def init():
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,snapshot TEXT NOT NULL,updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS revisions(project_id TEXT,revision INTEGER,snapshot TEXT,created TEXT,reason TEXT,PRIMARY KEY(project_id,revision));
        CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,metadata TEXT NOT NULL,path TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,project_id TEXT,operation TEXT,status TEXT,request_hash TEXT,idem TEXT,body TEXT NOT NULL,created TEXT,updated TEXT,UNIQUE(project_id,operation,idem));
        CREATE TABLE IF NOT EXISTS events(job_id TEXT,seq INTEGER,body TEXT,PRIMARY KEY(job_id,seq));
        CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY,job_id TEXT,name TEXT,path TEXT,sha256 TEXT,media_type TEXT);
        CREATE TABLE IF NOT EXISTS exports(id TEXT PRIMARY KEY,job_id TEXT,project_id TEXT,body TEXT);
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
        ''')
        c.execute('INSERT OR IGNORE INTO meta VALUES (?,?)',('session_token',uid()+uid()))

@contextlib.contextmanager
def transaction():
    c=connect()
    try:
        c.execute('BEGIN IMMEDIATE'); yield c; c.commit()
    except BaseException: c.rollback(); raise
    finally: c.close()

def get_project(pid,c=None):
    if c is None:
        with connect() as cc: return get_project(pid,cc)
    row=c.execute('SELECT snapshot FROM projects WHERE id=?',(pid,)).fetchone()
    if not row: raise AppError('PROJECT_NOT_FOUND','프로젝트를 찾을 수 없습니다.',404)
    p=json.loads(row[0])
    if p.get('schemaVersion') != 1: raise AppError('SCHEMA_UNSUPPORTED','지원하지 않는 프로젝트 버전입니다.',422)
    return p

def check_revision(p,expected):
    if type(expected) is not int or expected!=p['revision']:
        raise AppError('REVISION_CONFLICT','다른 변경이 저장되었습니다. 초안을 유지한 채 최신 버전을 확인하세요.',409,{'expectedRevision':expected,'savedRevision':p['revision']})

def write_project(c,p,reason,initial=False):
    if not initial: p['revision']+=1
    p['updatedAt']=now()
    p.setdefault('journal',[]).append({'revision':p['revision'],'parentRevision':p['revision']-1,'reason':reason,'createdAt':now()})
    value=dumps(p)
    c.execute('INSERT INTO projects VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot,updated=excluded.updated',(p['projectId'],value,p['updatedAt']))
    c.execute('INSERT INTO revisions VALUES (?,?,?,?,?)',(p['projectId'],p['revision'],value,now(),reason))
    return p

def create_project(name,character_name,cell=None):
    if not name.strip(): raise AppError('NAME_REQUIRED','프로젝트 이름을 입력하세요.')
    p=dict(projectId=uid(),schemaVersion=1,revision=1,name=name.strip()[:200],characterName=character_name[:200],createdAt=now(),updatedAt=now(),assets=[],references=[],activeReferenceRevisionId=None,frames=[],alignmentGroups=[],alignments={},clips=[],outline=dict(enabled=False,mode='preview-only',teamLabel='청팀',colorRGBA=[66,190,255,255],thicknessPx=2,directions=8,opacityPerCopy=.8,rendererVersion='outline-v1'),generationSettings={},journal=[],generations=[],defaultCell=cell or {'width':512,'height':512})
    with transaction() as c: return write_project(c,p,'프로젝트 생성',True)

def atomic_bytes(path,data):
    path=Path(path)
    if not path.resolve().is_relative_to(DATA.resolve()): raise AppError('STORAGE_ESCAPE','관리 저장소 밖에 파일을 쓸 수 없습니다.')
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.parent.resolve().is_relative_to(DATA.resolve()): raise AppError('STORAGE_ESCAPE','관리 저장소 밖에 파일을 쓸 수 없습니다.')
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

def register_asset(data,filename,role='source',provenance=None,metadata=None,c=None):
    meta=dict(metadata or validate_image(data,filename))
    aid=uid(); path=DATA/'assets'/meta['sha256'][:2]/meta['sha256']
    if not path.resolve().is_relative_to(DATA.resolve()): raise AppError('STORAGE_ESCAPE','관리 저장소 밖에 원본을 쓸 수 없습니다.')
    if not path.exists(): atomic_bytes(path,data)
    elif digest(path.read_bytes())!=meta['sha256']: raise AppError('ASSET_HASH','기존 원본의 해시가 일치하지 않습니다.',424)
    meta.update(assetId=aid,role=role,url=f'/v1/assets/{aid}/content',provenance=provenance or {'kind':'imported'})
    if c is None:
        with transaction() as cc: cc.execute('INSERT INTO assets VALUES (?,?,?)',(aid,dumps(meta),str(path.relative_to(DATA))))
    else: c.execute('INSERT INTO assets VALUES (?,?,?)',(aid,dumps(meta),str(path.relative_to(DATA))))
    return meta

def asset_path(aid):
    with connect() as c: row=c.execute('SELECT path,metadata FROM assets WHERE id=?',(aid,)).fetchone()
    if not row: raise AppError('ASSET_MISSING','원본 자료가 없습니다.',424,{'assetId':aid})
    path=(DATA/row['path']).resolve()
    if not path.is_relative_to(DATA) or not path.is_file(): raise AppError('ASSET_MISSING','원본 파일을 찾을 수 없습니다.',424,{'assetId':aid})
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
    for key in ('assets','references','frames','alignmentGroups','clips','generations','journal'):
        if not isinstance(p.get(key),list): raise AppError('SNAPSHOT_INVALID',f'백업의 {key} 목록이 잘못되었습니다.')
    if not isinstance(p.get('alignments'),dict) or not isinstance(p.get('name'),str): raise AppError('SNAPSHOT_INVALID','백업 프로젝트 형식이 잘못되었습니다.')
    def ids(key,field):
        values=[x.get(field) for x in p[key] if isinstance(x,dict)]
        if len(values)!=len(p[key]) or any(not isinstance(v,str) or not v for v in values) or len(values)!=len(set(values)): raise AppError('SNAPSHOT_IDS','백업 ID가 없거나 중복됩니다.')
        return set(values)
    assets=ids('assets','assetId'); refs=ids('references','referenceRevisionId'); frames=ids('frames','frameVersionId'); groups=ids('alignmentGroups','alignmentGroupId'); ids('clips','clipId')
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
        for o in cl.get('occurrences',[]):
            require(o.get('frameVersionId'),frames)
            if not isinstance(o.get('occurrenceId'),str) or o['occurrenceId'] in occurrences: raise AppError('SNAPSHOT_IDS','재생 슬롯 ID가 잘못되었습니다.')
            occurrences.add(o['occurrenceId'])
            if type(o.get('durationMs')) is not int or not 1<=o['durationMs']<=60000: raise AppError('SNAPSHOT_TIMING','프레임 시간이 잘못되었습니다.')
    for fid in p['alignments']: require(fid,frames)
    return p

def remap_reference_ids(p):
    mapping={r['referenceRevisionId']:uid() for r in p['references']}
    def visit(v):
        if isinstance(v,dict): return {k:visit(x) for k,x in v.items()}
        if isinstance(v,list): return [visit(x) for x in v]
        if isinstance(v,str): return mapping.get(v,v)
        return v
    return visit(p)
