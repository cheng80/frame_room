from __future__ import annotations
import asyncio, copy, json, mimetypes, time
from pathlib import Path
from contextlib import asynccontextmanager, nullcontext
from typing import Literal
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware
from . import store as s
from . import desktop
from .edits import Strict, EditRequest, apply, find, number

@asynccontextmanager
async def lifespan(app):
    s.init(); yield
app=FastAPI(title='프레임 공방 API',version='1.0.0',lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver','[::1]'])

@app.exception_handler(s.AppError)
async def app_error(request,exc): return JSONResponse(exc.payload(),status_code=exc.status)
@app.exception_handler(RequestValidationError)
async def validation_error(request,exc):
    errors=[{'field':'.'.join(str(x) for x in e['loc']),'message':e['msg']} for e in exc.errors()]
    return JSONResponse(dict(code='VALIDATION_ERROR',stage='validation',message='입력값을 확인하세요.',fieldErrors=errors,retryable=False),422)
@app.middleware('http')
async def protect(request,call_next):
    origin=request.headers.get('origin')
    allowed={'http://127.0.0.1:8765','http://localhost:8765','http://127.0.0.1:5173','http://localhost:5173'}
    if origin and origin not in allowed:
        return JSONResponse({'code':'ORIGIN_FORBIDDEN','message':'로컬 앱에서만 요청할 수 있습니다.'},403)
    if request.method in ('POST','PATCH','PUT','DELETE') and request.url.path.startswith('/v1'):
        with s.connect() as c: row=c.execute("SELECT value FROM meta WHERE key='session_token'").fetchone()
        if not row or request.headers.get('x-session-token')!=row[0]: return JSONResponse({'code':'SESSION_REQUIRED','message':'연결을 다시 확인한 뒤 재시도하세요.'},403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    return response

@app.get('/v1/health')
def health():
    with s.connect() as c:
        token=c.execute("SELECT value FROM meta WHERE key='session_token'").fetchone()[0]
        row=c.execute("SELECT value FROM meta WHERE key='worker_heartbeat'").fetchone()
    return dict(limits={'maxUploadBytes':32*1024*1024,'maxBatchFiles':128},api='ready',worker='ready' if row and time.time()-float(row[0])<8 else 'offline',engine=dict(version='2.12.1',commit=s.COMMIT,available=(s.ROOT/'engine/sprite-gen/sprite_gen').exists()),sessionToken=token,desktop={'fileManager':desktop.file_manager()},projectStorage={'layout':'project-folder','defaultParent':str(s.DATA/'projects')})

class NewProject(Strict):
    name:str=Field(min_length=1,max_length=200); characterName:str='캐릭터'; cell:dict|None=None
    parentDirectory:str|None=Field(default=None,strict=True,min_length=1,max_length=4096)
    @field_validator('parentDirectory')
    @classmethod
    def valid_parent(cls,value):
        if value is not None and (not value.strip() or '\x00' in value): raise ValueError('정상 폴더 경로를 입력하세요.')
        return value
@app.get('/v1/projects')
def projects():
    with s.connect() as c: rows=c.execute('SELECT snapshot FROM projects ORDER BY updated DESC').fetchall()
    return {'projects':[s.public_project(json.loads(r[0])) for r in rows]}
@app.post('/v1/projects',status_code=201)
def create(body:NewProject):
    if body.cell:
        for k in ('width','height'): number(body.cell.get(k),1,4096,'셀 크기',True)
    return s.public_project(s.create_project(body.name,body.characterName,body.cell,parent_directory=body.parentDirectory))

class ProjectFolderPath(Strict):
    path:str=Field(strict=True,min_length=1,max_length=4096)
    @field_validator('path')
    @classmethod
    def valid_path(cls,value):
        if not value.strip() or '\x00' in value: raise ValueError('정상 폴더 경로를 입력하세요.')
        return value
class PickProjectFolder(Strict):
    purpose:Literal['open','parent']
class PickedProjectFolder(Strict):
    path:str|None
class MissingProjectFolder(Strict):
    projectId:str
    name:str
    path:str
    revision:int=Field(strict=True,ge=1)
class MissingProjectFolders(Strict):
    projects:list[MissingProjectFolder]
class CleanupProjectFolder(ProjectFolderPath):
    projectId:str=Field(strict=True,min_length=1)
    expectedRevision:int=Field(strict=True,ge=1)
class CleanupProjectFolders(Strict):
    projects:list[CleanupProjectFolder]
class CleanedProjectFolders(Strict):
    removedProjectIds:list[str]
    removedCount:int=Field(strict=True,ge=0)

@app.post('/v1/project-folders/open',description='프로젝트 폴더 또는 그 안의 project.json/project.sqlite3 경로를 검증하고 목록에 등록합니다. 생성 작업을 자동 실행하지 않습니다.')
def open_project_folder(body:ProjectFolderPath):
    from . import project_folders as folders
    return s.public_project(folders.open_project(body.path))
@app.post('/v1/project-folders/pick',response_model=PickedProjectFolder,
    description='사용자가 호출할 때만 로컬 OS의 폴더 선택창을 엽니다. 취소하면 path는 null입니다.',
    responses={501:{'description':'FOLDER_PICKER_UNSUPPORTED'},503:{'description':'FOLDER_PICKER_UNAVAILABLE'}})
def pick_project_folder(body:PickProjectFolder):
    return {'path':desktop.pick_folder(body.purpose)}
@app.get('/v1/project-folders/missing',response_model=MissingProjectFolders)
def missing_project_folders():
    from . import project_folders as folders
    return folders.missing_projects()
@app.post('/v1/project-folders/cleanup',response_model=CleanedProjectFolders,
    description='미리 확인한 ID·버전·경로와 폴더 부재를 다시 검증한 뒤 목록만 정리합니다. 물리 파일은 삭제하지 않습니다.')
def cleanup_project_folders(body:CleanupProjectFolders):
    from . import project_folders as folders
    return folders.cleanup_missing([item.model_dump() for item in body.projects])
@app.get('/v1/projects/{pid}')
def project(pid:str):
    p=s.public_project(s.get_project(pid)); return JSONResponse(p,headers={'ETag':str(p['revision'])})
class RevealProject(Strict):
    pass
class RevealedProject(Strict):
    projectId:str
    path:str
    fileManager:Literal['finder','explorer']
    storageLayout:Literal['project-folder']
@app.post('/v1/projects/{pid}/reveal',response_model=RevealedProject,
    description='로컬 서버 OS의 Finder 또는 탐색기로 해당 프로젝트 폴더를 엽니다. 프로젝트 및 원본 자료는 변경하지 않습니다. 임의 경로는 받지 않습니다.',
    responses={403:{'description':'SESSION_REQUIRED 또는 ORIGIN_FORBIDDEN'},404:{'description':'PROJECT_NOT_FOUND'},
               501:{'description':'FILE_MANAGER_UNSUPPORTED'},503:{'description':'FILE_MANAGER_UNAVAILABLE'}})
def reveal_project(pid:str,body:RevealProject):
    return desktop.reveal_project(pid)
class DeleteProject(Strict):
    expectedRevision:int=Field(strict=True,ge=1)
class DeletedProject(Strict):
    deletedProjectId:str
@app.delete('/v1/projects/{pid}',response_model=DeletedProject,
    description='프로젝트를 앱 목록에서 제거합니다. 프로젝트 폴더의 편집 상태·이력·원본·출력 파일을 보존하여 다시 열 수 있습니다. X-Session-Token과 로컬 Origin 보호를 적용합니다.',
    responses={403:{'description':'SESSION_REQUIRED 또는 ORIGIN_FORBIDDEN'},
               404:{'description':'PROJECT_NOT_FOUND'},
               409:{'description':'REVISION_CONFLICT 또는 PROJECT_BUSY (queued/running/cancel_requested 작업 존재)'}})
def delete_project(pid:str,body:DeleteProject):
    from . import project_folders as folders
    folders.detach_project(pid,body.expectedRevision)
    return {'deletedProjectId':pid}
class Duplicate(Strict): expectedRevision:int; name:str=Field(min_length=1,max_length=200)
@app.post('/v1/projects/{pid}/duplicate',status_code=201)
def duplicate(pid:str,body:Duplicate):
    with s.transaction() as c:
        p=s.get_project(pid,c); s.check_revision(p,body.expectedRevision)
        p=s.remap_reference_ids(p)
        p.update(projectId=s.uid(),name=body.name,revision=1,createdAt=s.now(),journal=[])
        s.write_project(c,p,'프로젝트 복제',True)
    return s.public_project(p)

@app.post('/v1/projects/{pid}/assets',status_code=201)
async def upload(pid:str,files:list[UploadFile]=File(...),role:str=Form('source'),importMode:str=Form('whole')):
    s.get_project(pid)
    if len(files)>128: raise s.AppError('BATCH_LIMIT','한 번에 최대 128개 파일을 선택하세요.',413)
    if role not in ('source','identity','style','pose'): raise s.AppError('ASSET_ROLE','지원하지 않는 자료 역할입니다.')
    pending=[]; total_bytes=0
    for f in files:
        data=await f.read(32*1024*1024+1)
        total_bytes+=len(data)
        if total_bytes>256*1024*1024: raise s.AppError('BATCH_LIMIT','한 번의 업로드는 총 256 MiB 이하로 선택하세요.',413)
        pending.append((data,f.filename or 'image.png',s.validate_image(data,f.filename or 'image.png')))
    with s.project_scope(pid), s.transaction() as c:
        p=s.get_project(pid,c); assets=[]
        for data,name,meta in pending:
            assets.append(s.register_asset(data,name,role,{'kind':'imported','importMode':importMode},meta,c))
        p['assets'].extend(assets); s.write_project(c,p,'원본 이미지 등록')
    return dict(assets=assets,savedRevision=p['revision'])
@app.get('/v1/assets/{aid}/content')
def content(aid:str):
    path=s.asset_path(aid)
    with s.connect() as c: meta=json.loads(c.execute('SELECT metadata FROM assets WHERE id=?',(aid,)).fetchone()[0])
    return FileResponse(path,media_type=meta['mediaType'],headers={'Cache-Control':'private,max-age=31536000,immutable'})

@app.post('/v1/projects/{pid}/videos',status_code=201)
async def upload_video(pid:str,file:UploadFile=File(...),expectedRevision:int=Form(...)):
    from . import videos
    s.check_revision(s.get_project(pid),expectedRevision)
    data=await file.read(videos.MAX_BYTES+1)
    meta=await asyncio.to_thread(videos.validate,data,file.filename or 'video.mp4')
    with s.project_scope(pid), s.transaction() as c:
        p=s.get_project(pid,c);s.check_revision(p,expectedRevision)
        video=videos.register(data,file.filename or 'video.mp4',metadata=meta,c=c)
        p.setdefault('videos',[]).append(video);s.write_project(c,p,'원본 영상 등록')
    return dict(snapshot=s.public_project(p),video=video)

@app.get('/v1/videos/{vid}/content')
def video_content(vid:str):
    from .videos import path_for
    return FileResponse(path_for(vid),media_type='video/mp4',headers={'Cache-Control':'private,max-age=31536000,immutable'})

class RefBody(Strict): expectedRevision:int; reference:dict
@app.post('/v1/projects/{pid}/reference-revisions',status_code=201)
def reference(pid:str,body:RefBody):
    with s.transaction() as c:
        p=s.get_project(pid,c); s.check_revision(p,body.expectedRevision)
        d=body.reference; allowed={'identityAssetId','styleAssetIds','poseAssetIds','fixedTraits','allowedChanges','forbiddenTransfers','facing','bodyMeasurement'}
        if set(d)-allowed: raise s.AppError('REFERENCE_FIELDS','지원하지 않는 기준 설정입니다.')
        for aid in [d.get('identityAssetId')]+d.get('styleAssetIds',[])+d.get('poseAssetIds',[]): find(p['assets'],'assetId',aid)
        ref=dict(referenceRevisionId=s.uid(),styleAssetIds=[],poseAssetIds=[],fixedTraits='',allowedChanges='',forbiddenTransfers='',facing='right',bodyMeasurement=None,approval='draft')
        ref.update(d); p['references'].append(ref); s.write_project(c,p,'기준 초안 저장')
    return dict(referenceRevisionId=ref['referenceRevisionId'],savedRevision=p['revision'])
class Approval(Strict): expectedRevision:int; reviewChecks:dict
@app.post('/v1/reference-revisions/{rid}/approve')
def approve(rid:str,body:Approval):
    with s.transaction() as c:
        rows=c.execute('SELECT snapshot FROM projects ORDER BY updated DESC').fetchall()
        p=next((json.loads(r[0]) for r in rows if any(x['referenceRevisionId']==rid for x in json.loads(r[0])['references'])),None)
        if not p: raise s.AppError('REFERENCE_NOT_FOUND','기준을 찾을 수 없습니다.',404)
        s.check_revision(p,body.expectedRevision); ref=find(p['references'],'referenceRevisionId',rid)
        if ref['approval']=='approved': return dict(referenceRevisionId=rid,savedRevision=p['revision'])
        if not body.reviewChecks.get('identity'): raise s.AppError('REFERENCE_REVIEW','외형 기준을 확인하고 승인하세요.')
        s.asset_path(ref['identityAssetId']); ref.update(approval='approved',approvedAt=s.now(),reviewChecks=body.reviewChecks)
        p['activeReferenceRevisionId']=rid; s.write_project(c,p,'기준 승인')
    return dict(referenceRevisionId=rid,savedRevision=p['revision'])
@app.patch('/v1/projects/{pid}/edits')
def edits(pid:str,body:EditRequest):
    with s.transaction() as c:
        p=s.get_project(pid,c); s.check_revision(p,body.expectedRevision)
        p=apply(p,body.operations); s.write_project(c,p,'편집: '+', '.join(o.type for o in body.operations))
    return dict(savedRevision=p['revision'],snapshot=s.public_project(p))
@app.get('/v1/projects/{pid}/revisions')
def revisions(pid:str):
    s.get_project(pid)
    with s.connect() as c: rows=c.execute('SELECT revision,created,reason FROM revisions WHERE project_id=? ORDER BY revision DESC',(pid,)).fetchall()
    return {'revisions':[dict(revision=r['revision'],createdAt=r['created'],reason=r['reason']) for r in rows]}
class RestoreRevision(Strict): expectedRevision:int; targetRevision:int
@app.post('/v1/projects/{pid}/restore-revision')
def restore_revision(pid:str,body:RestoreRevision):
    with s.transaction() as c:
        current=s.get_project(pid,c); s.check_revision(current,body.expectedRevision)
        row=c.execute('SELECT snapshot FROM revisions WHERE project_id=? AND revision=?',(pid,body.targetRevision)).fetchone()
        if not row: raise s.AppError('REVISION_MISSING','이력 버전을 찾을 수 없습니다.',404)
        p=json.loads(row[0]); p['revision']=current['revision']; p['journal']=current['journal']; s.write_project(c,p,f'이력 {body.targetRevision} 복원')
    return dict(savedRevision=p['revision'],snapshot=s.public_project(p))
@app.get('/v1/providers')
def providers():
    from adapters.spritegen.provider import providers as get_providers
    result=get_providers()
    from adapters.spritegen.video_provider import capability
    result.append(capability())
    with s.connect() as c:
        rows=c.execute("SELECT body FROM jobs WHERE operation IN ('generate','generate_video') ORDER BY updated DESC").fetchall()
    for provider in result:
        matching=[json.loads(r[0]) for r in rows if ('grok-video' if json.loads(r[0])['operation']=='generate_video' else json.loads(r[0]).get('request',{}).get('params',{}).get('providerId'))==provider['providerId']]
        successful=next((j for j in matching if j['status'] in ('needs_review','succeeded') and j.get('result',{}).get('receipt')),None)
        if successful:
            provider['lastSuccess']={'jobId':successful['jobId'],'at':successful['updatedAt'],'receipt':successful['result']['receipt']}
            provider['generationVerified']=True
        if matching: provider['lastJobStatus']=matching[0]['status']
    return {'providers':result}

class JobRequest(Strict):
    operation:Literal['generate','generate_video','process_video','cutout','extract','align','inspect','bake','preview_follow','apply_follow','check_handed']; inputRevision:int; assetIds:list[str]=[]; params:dict={}; idempotencyKey:str=Field(min_length=1,max_length=200)
def enqueue(pid,operation,request,idem,expected=None,connection=None):
    try: rh=s.digest(s.dumps(request).encode())
    except (ValueError,TypeError) as exc:
        raise s.AppError('JOB_REQUEST_INVALID','작업 요청에는 유한한 숫자와 JSON 값만 사용할 수 있습니다.') from exc
    with (s.transaction() if connection is None else nullcontext(connection)) as c:
        row=c.execute('SELECT body,request_hash FROM jobs WHERE project_id=? AND operation=? AND idem=?',(pid,operation,idem)).fetchone()
        if row:
            if row['request_hash']!=rh: raise s.AppError('IDEMPOTENCY_CONFLICT','같은 제출 키에 다른 내용이 있습니다.',409)
            return s.public_job(json.loads(row['body']))
        p=s.get_project(pid,c) if pid else None
        if p is not None and expected is not None: s.check_revision(p,expected)
        if p:
            for aid in request.get('assetIds',[]): find(p['assets'],'assetId',aid)
        if operation in ('preview_follow','apply_follow','check_handed'):
            if request.get('assetIds'): raise s.AppError('CLIP_TOOLS_INPUT','선택 동작 도구에는 별도 이미지 목록을 전달할 수 없습니다.')
            if operation=='apply_follow':
                from services.worker.clip_tools_task import validate_apply
                validate_apply(p,request.get('params',{}),c)
            else:
                from adapters.spritegen.clip_tools import validate_params
                validate_params(p,operation,request.get('params',{}))
        if operation=='generate':
            ref=find(p['references'],'referenceRevisionId',request['params'].get('referenceRevisionId',p['activeReferenceRevisionId']))
            if ref['approval']!='approved': raise s.AppError('REFERENCE_REQUIRED','승인된 기준이 필요합니다.',424)
            if request['params'].get('providerId') not in ('codex','grok','openai'): raise s.AppError('PROVIDER_REQUIRED','생성 연결을 명시적으로 선택하세요.')
            number(request['params'].get('frameCount',1),1,24,'요청 프레임 수',True)
        if operation in ('generate_video','process_video'):
            from adapters.spritegen.video_provider import validate_params
            settings=validate_params(request.get('params',{}),generation=operation=='generate_video')
            if settings.get('matchClipId'):
                match=find(p['clips'],'clipId',settings['matchClipId'])
                count=len(match.get('occurrences',[]))
                duration=sum(o['durationMs'] for o in match.get('occurrences',[]))
                if not match.get('loop') or not 4<=count<=64 or not count<=duration<=60000:
                    raise s.AppError('VIDEO_MATCH_CLIP','주기 기준은 4~64프레임·60초 이하의 반복 동작이어야 합니다.')
                if settings['loopMode']=='full' or settings['state']=='attack' and settings['loopMode']=='auto':
                    raise s.AppError('VIDEO_MATCH_CLIP','전체 영상이나 단발 동작에는 주기 맞춤을 사용할 수 없습니다.')
            if operation=='generate_video':
                if len(request.get('assetIds',[]))!=1: raise s.AppError('VIDEO_BASE_REQUIRED','영상에 사용할 기준 그림 하나를 선택하세요.')
                if settings.get('referenceRevisionId'):
                    ref=find(p['references'],'referenceRevisionId',settings['referenceRevisionId'])
                    if ref['approval']!='approved': raise s.AppError('REFERENCE_REQUIRED','선택한 기준을 먼저 승인하세요.',424)
                    if ref['identityAssetId']!=request['assetIds'][0]: raise s.AppError('VIDEO_REFERENCE_MISMATCH','승인 기준과 선택한 그림이 다릅니다.')
            else:
                if request.get('assetIds'): raise s.AppError('VIDEO_INPUT','영상 후처리에는 영상만 선택하세요.')
                video=find(p.get('videos',[]),'videoId',settings.get('videoId'))
                if settings.get('spillReferenceAssetId'): find(p['assets'],'assetId',settings['spillReferenceAssetId'])
                if settings['loopMode']=='manual' and settings['endFrame']>video['frameCount']: raise s.AppError('VIDEO_RANGE','선택 구간이 영상 끝을 넘습니다.')
        jid=s.uid(); j=dict(jobId=jid,projectId=pid,operation=operation,status='queued',attemptId=s.uid(),attempts=[],inputRevision=expected,request=request,snapshot=p,requestHash=rh,idempotencyKey=idem,eventSeq=0,step='queued',progress={},artifacts=[],errors=[],createdAt=s.now(),updatedAt=s.now(),engineCommit=s.COMMIT)
        if operation=='process_video': j['resumable']=True
        c.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)',(jid,pid,operation,'queued',rh,idem,s.dumps(j),j['createdAt'],j['updatedAt']))
        s.write_job(c,j)
    return s.public_job(j)|{'eventUrl':f'/v1/jobs/{jid}/events'}
@app.post('/v1/projects/{pid}/jobs',status_code=202)
def jobs_create(pid:str,body:JobRequest):
    if len(body.assetIds)>128: raise s.AppError('BATCH_LIMIT','한 번에 최대 128개 이미지를 처리하세요.',413)
    if body.operation=='extract':
        params=body.params
        if params.get('mode')=='grid':
            number(params.get('rows',1),1,1024,'격자 행',True); number(params.get('columns',1),1,1024,'격자 열',True)
            if params.get('rows',1)*params.get('columns',1)>1024: raise s.AppError('GRID_LIMIT','격자는 최대 1024칸까지 지원합니다.')
        if len(params.get('regions',[]))>1024: raise s.AppError('REGION_LIMIT','영역은 최대 1024개까지 지원합니다.')
    return enqueue(pid,body.operation,body.model_dump(exclude={'idempotencyKey'}),body.idempotencyKey,body.inputRevision)

class VideoBatchItem(Strict):
    assetId:str=Field(min_length=1)
    params:dict={}

class VideoBatchRequest(Strict):
    inputRevision:int
    items:list[VideoBatchItem]=Field(min_length=1,max_length=16)
    idempotencyKey:str=Field(min_length=1,max_length=160)

@app.post('/v1/projects/{pid}/video-batches',status_code=202)
def video_batches_create(pid:str,body:VideoBatchRequest):
    """All-or-nothing queueing; a lost response cannot multiply paid requests."""
    payload=body.model_dump(exclude={'idempotencyKey'})
    request_hash=s.digest(s.dumps(payload).encode())
    key='video_batch:'+pid+':'+s.digest(body.idempotencyKey.encode())
    with s.transaction() as c:
        project=s.get_project(pid,c)
        saved=c.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
        if saved:
            record=json.loads(saved[0])
            if record['requestHash']!=request_hash:
                raise s.AppError('IDEMPOTENCY_CONFLICT','같은 묶음 제출 키에 다른 내용이 있습니다.',409)
            return dict(batchId=record['batchId'],jobs=[s.public_job(s.get_job(jid,c)) for jid in record['jobIds']])
        s.check_revision(project,body.inputRevision)
        batch_id=s.uid();jobs=[]
        for index,item in enumerate(body.items):
            request=dict(operation='generate_video',inputRevision=body.inputRevision,
                         assetIds=[item.assetId],params=item.params)
            # Namespace independent of ordinary single-job idempotency keys.
            idem='batch:'+s.digest((pid+':'+body.idempotencyKey+':'+str(index)).encode())
            result=enqueue(pid,'generate_video',request,idem,body.inputRevision,connection=c)
            job=s.get_job(result['jobId'],c)
            job.update(batchId=batch_id,batchIndex=index,batchSize=len(body.items))
            s.write_job(c,job);jobs.append(s.public_job(job))
        record=dict(batchId=batch_id,requestHash=request_hash,jobIds=[j['jobId'] for j in jobs])
        c.execute('INSERT INTO meta(key,value) VALUES (?,?)',(key,s.dumps(record)))
    return dict(batchId=batch_id,jobs=jobs)

@app.get('/v1/projects/{pid}/jobs')
def jobs_list(pid:str):
    with s.connect() as c:
        s.get_project(pid,c)
        rows=c.execute('SELECT body FROM jobs WHERE project_id=? ORDER BY created DESC',(pid,)).fetchall()
    return {'jobs':[s.public_job(json.loads(r[0])) for r in rows]}
@app.get('/v1/jobs/{jid}')
def job_get(jid:str): return s.public_job(s.get_job(jid))
@app.get('/v1/jobs/{jid}/events')
async def events(jid:str,request:Request):
    s.get_job(jid)
    try: seq=int(request.headers.get('last-event-id','0'))
    except ValueError: seq=0
    async def stream():
        nonlocal seq
        while not await request.is_disconnected():
            with s.connect() as c: rows=c.execute('SELECT seq,body FROM events WHERE job_id=? AND seq>? ORDER BY seq',(jid,seq)).fetchall()
            for row in rows:
                seq=row['seq']; yield f'id: {seq}\nevent: job\ndata: {row["body"]}\n\n'
            if not rows: yield ': heartbeat\n\n'
            await asyncio.sleep(1)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache'})
class Cancel(Strict): expectedStatus:str
@app.post('/v1/jobs/{jid}/cancel')
def cancel(jid:str,body:Cancel):
    with s.transaction() as c:
        j=s.get_job(jid,c)
        if j['status'] not in ('queued','running','cancel_requested'): return dict(status='already_terminal',job=s.public_job(j))
        if body.expectedStatus!=j['status']: raise s.AppError('JOB_STALE','작업 상태가 변경되었습니다. 다시 확인하세요.',409)
        j['status']='canceled' if j['status']=='queued' else 'cancel_requested'; s.write_job(c,j)
    return JSONResponse(s.public_job(j),202)
class Retry(Strict): failedStep:str=''; reuseCheckpoint:bool=True; idempotencyKey:str
@app.post('/v1/jobs/{jid}/retry')
def retry(jid:str,body:Retry):
    with s.transaction() as c:
        j=s.get_job(jid,c)
        if body.idempotencyKey in j.get('retryKeys',[]): return s.public_job(j)
        if j['status']=='provider_outcome_unknown': raise s.AppError('PROVIDER_OUTCOME_UNKNOWN','외부 결과가 불명확합니다. 자동 재전송할 수 없습니다. 제공자 결과를 확인하세요.',409)
        if j['status'] not in ('failed','interrupted','canceled'): raise s.AppError('RETRY_STATE','이 상태의 작업은 재시도할 수 없습니다.',409)
        result_path=s.resolve_work_path(jid,s.job_directory(jid)/j['attemptId']/'result.json')
        completed_result=json.loads(result_path.read_text()) if result_path.exists() else {}
        if j['operation']=='generate_video' and not completed_result.get('ok'):
            from adapters.spritegen.video_provider import checkpoint_state,read_checkpoint
            state=checkpoint_state(j)
            try: checkpoint=read_checkpoint(s.resolve_work_path(jid,s.job_directory(jid)/'video-checkpoint.json'))
            except (OSError,ValueError): raise s.AppError('VIDEO_CHECKPOINT_INVALID','영상 접수 기록을 읽지 못했습니다. 자동 재전송하지 않습니다.',409)
            if state['outcomeUnknown'] or checkpoint and checkpoint.get('postCount') and not state['resumable']:
                raise s.AppError('PROVIDER_RETRY_BLOCKED','접수 여부가 불명확하거나 거절된 생성은 재전송하지 않습니다.',409)
        if j['operation']=='generate' and j.get('externalStarted') and not j.get('providerCheckpoint') and not completed_result.get('ok'): raise s.AppError('PROVIDER_RETRY_BLOCKED','외부 생성 호출을 재전송하지 않습니다. 원인을 확인한 뒤 새 생성을 명시적으로 요청하세요.',409)
        j['attempts'].append({'attemptId':j['attemptId'],'status':j['status'],'errors':j['errors']}); j.setdefault('retryKeys',[]).append(body.idempotencyKey)
        if completed_result.get('ok'): j['reuseResultAttemptId']=j['attemptId']
        elif j.get('providerCheckpoint'): j['reuseProviderAttemptId']=j['attemptId']
        j.update(attemptId=s.uid(),status='queued',step='queued',errors=[]); s.write_job(c,j)
    return s.public_job(j)

class ExportRequest(Strict):
    savedRevision:int; clipRevisionIds:list[str]; formats:list[str]=['atlas','pngs','runtime','aseprite']; outlineMode:Literal['bake','preview-only']='bake'; idempotencyKey:str
@app.post('/v1/projects/{pid}/exports',status_code=202)
def export_create(pid:str,body:ExportRequest):
    p=s.get_project(pid); s.check_revision(p,body.savedRevision)
    if not body.clipRevisionIds: raise s.AppError('EMPTY_TIMELINE','출력할 동작을 선택하세요.')
    if len(set(body.clipRevisionIds))!=len(body.clipRevisionIds): raise s.AppError('INVALID_CLIP_SELECTION','같은 동작이 중복 선택되었습니다.')
    for rid in body.clipRevisionIds:
        cl=find(p['clips'],'clipRevisionId',rid)
        if not cl['occurrences']: raise s.AppError('EMPTY_TIMELINE','빈 동작은 출력할 수 없습니다.',422,{'affectedIds':[cl['clipId']]})
        from alignment.pipeline import _clip_gates
        gates=_clip_gates(p,cl)
        if gates: raise s.AppError(gates[0]['code'],gates[0]['message'],422,{'errors':gates})
        for occurrence in cl['occurrences']:
            frame=find(p['frames'],'frameVersionId',occurrence['frameVersionId'])
            if frame.get('review')!='approved': raise s.AppError('FRAME_UNAPPROVED','프레임 검수가 필요합니다.',422,{'affectedIds':[frame['frameVersionId']]})
            anchor=p['alignments'].get(frame['frameVersionId'],{})
            group=find(p['alignmentGroups'],'alignmentGroupId',frame['nativeScaleGroupId'])
            if anchor.get('approval')!='approved' or anchor.get('groupRevisionId')!=group['groupRevisionId']:
                raise s.AppError('ANCHOR_UNAPPROVED','현재 그룹 기준의 앵커 승인이 필요합니다.',422,{'affectedIds':[frame['frameVersionId']]})
            s.asset_path(frame['imageAssetId'])
    request=body.model_dump(exclude={'idempotencyKey'})
    j=enqueue(pid,'export',request,body.idempotencyKey,body.savedRevision)
    with s.transaction() as c:
        # An idempotent terminal job may be deleted after enqueue returns.
        s.get_project(pid,c); s.get_job(j['jobId'],c)
        existing=c.execute('SELECT id FROM exports WHERE job_id=?',(j['jobId'],)).fetchone()
        eid=existing[0] if existing else s.uid()
        if not existing:
            c.execute('INSERT INTO exports VALUES (?,?,?,?)',(eid,j['jobId'],pid,s.dumps({'exportId':eid})))
            s.mark_folder_dirty(c,pid)
    return dict(exportId=eid,jobId=j['jobId'])
@app.get('/v1/exports/{eid}')
def export_get(eid:str):
    with s.connect() as c: row=c.execute('SELECT * FROM exports WHERE id=?',(eid,)).fetchone()
    if not row: raise s.AppError('EXPORT_MISSING','출력 결과를 찾을 수 없습니다.',404)
    j=s.get_job(row['job_id']); return dict(exportId=eid,status=j['status'],jobId=j['jobId'],manifest=j.get('result',{}).get('manifest'),files=j.get('artifacts',[]),errors=j['errors'],projectRevision=j['inputRevision'])
@app.get('/v1/projects/{pid}/exports')
def exports_list(pid:str):
    with s.connect() as c:
        s.get_project(pid,c)
        rows=c.execute('SELECT id FROM exports WHERE project_id=?',(pid,)).fetchall()
    return {'exports':[export_get(r[0]) for r in rows]}
class Backup(Strict): savedRevision:int
@app.post('/v1/projects/{pid}/backup',status_code=202)
def backup(pid:str,body:Backup):
    j=enqueue(pid,'backup',body.model_dump(),s.uid(),body.savedRevision); return {'backupId':j['jobId'],**j}
@app.post('/v1/projects/restore',status_code=202)
async def restore(backupZip:UploadFile=File(...),idempotencyKey:str=Form(...)):
    data=await backupZip.read(256*1024*1024+1)
    if len(data)>256*1024*1024: raise s.AppError('BACKUP_LIMIT','백업은 256 MiB 이하로 선택하세요.',413)
    h=s.digest(data); path=s.DATA/'uploads'/h; s.atomic_bytes(path,data)
    return enqueue('','restore',{'backupHash':h},idempotencyKey)
@app.get('/v1/artifacts/{aid}/download')
def artifact(aid:str):
    with s.connect() as c: row=c.execute('SELECT * FROM artifacts WHERE id=?',(aid,)).fetchone()
    if not row: raise s.AppError('ARTIFACT_MISSING','게시된 결과를 찾을 수 없습니다.',404)
    path=s.managed_path(row['path'])
    if not path.is_file(): raise s.AppError('ARTIFACT_MISSING','결과 파일이 누락되었습니다.',424)
    if s.digest(path.read_bytes())!=row['sha256']: raise s.AppError('ARTIFACT_HASH','결과 파일 무결성 검사에 실패했습니다.',424)
    return FileResponse(path,media_type=row['media_type'],filename=row['name'])

web=s.ROOT/'apps/web/dist'
if web.exists(): app.mount('/',StaticFiles(directory=web,html=True),name='web')
