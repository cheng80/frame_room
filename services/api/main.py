from __future__ import annotations
import asyncio, copy, json, mimetypes, time
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from . import store as s
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
    return dict(limits={'maxUploadBytes':32*1024*1024,'maxBatchFiles':128},api='ready',worker='ready' if row and time.time()-float(row[0])<8 else 'offline',engine=dict(version='2.12.1',commit=s.COMMIT,available=(s.ROOT/'engine/sprite-gen/sprite_gen').exists()),sessionToken=token)

class NewProject(Strict):
    name:str=Field(min_length=1,max_length=200); characterName:str='캐릭터'; cell:dict|None=None
@app.get('/v1/projects')
def projects():
    with s.connect() as c: rows=c.execute('SELECT snapshot FROM projects ORDER BY updated DESC').fetchall()
    return {'projects':[json.loads(r[0]) for r in rows]}
@app.post('/v1/projects',status_code=201)
def create(body:NewProject):
    if body.cell:
        for k in ('width','height'): number(body.cell.get(k),1,4096,'셀 크기',True)
    return s.create_project(body.name,body.characterName,body.cell)
@app.get('/v1/projects/{pid}')
def project(pid:str):
    p=s.get_project(pid); return JSONResponse(p,headers={'ETag':str(p['revision'])})
class Duplicate(Strict): expectedRevision:int; name:str=Field(min_length=1,max_length=200)
@app.post('/v1/projects/{pid}/duplicate',status_code=201)
def duplicate(pid:str,body:Duplicate):
    with s.transaction() as c:
        p=s.get_project(pid,c); s.check_revision(p,body.expectedRevision)
        p=s.remap_reference_ids(p)
        p.update(projectId=s.uid(),name=body.name,revision=1,createdAt=s.now(),journal=[])
        return s.write_project(c,p,'프로젝트 복제',True)

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
    with s.transaction() as c:
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
    return dict(savedRevision=p['revision'],snapshot=p)
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
    return dict(savedRevision=p['revision'],snapshot=p)
@app.get('/v1/providers')
def providers():
    from adapters.spritegen.provider import providers as get_providers
    result=get_providers()
    with s.connect() as c:
        rows=c.execute("SELECT body FROM jobs WHERE operation='generate' ORDER BY updated DESC").fetchall()
    for provider in result:
        matching=[json.loads(r[0]) for r in rows if json.loads(r[0]).get('request',{}).get('params',{}).get('providerId')==provider['providerId']]
        successful=next((j for j in matching if j['status'] in ('needs_review','succeeded') and j.get('result',{}).get('receipt')),None)
        if successful:
            provider['lastSuccess']={'jobId':successful['jobId'],'at':successful['updatedAt'],'receipt':successful['result']['receipt']}
            provider['generationVerified']=True
        if matching: provider['lastJobStatus']=matching[0]['status']
    return {'providers':result}

class JobRequest(Strict):
    operation:Literal['generate','cutout','extract','align','inspect','bake']; inputRevision:int; assetIds:list[str]=[]; params:dict={}; idempotencyKey:str=Field(min_length=1,max_length=200)
def enqueue(pid,operation,request,idem,expected=None):
    rh=s.digest(s.dumps(request).encode())
    with s.transaction() as c:
        row=c.execute('SELECT body,request_hash FROM jobs WHERE project_id=? AND operation=? AND idem=?',(pid,operation,idem)).fetchone()
        if row:
            if row['request_hash']!=rh: raise s.AppError('IDEMPOTENCY_CONFLICT','같은 제출 키에 다른 내용이 있습니다.',409)
            return s.public_job(json.loads(row['body']))
        p=s.get_project(pid,c) if pid else None
        if p is not None and expected is not None: s.check_revision(p,expected)
        if p:
            for aid in request.get('assetIds',[]): find(p['assets'],'assetId',aid)
        if operation=='generate':
            ref=find(p['references'],'referenceRevisionId',request['params'].get('referenceRevisionId',p['activeReferenceRevisionId']))
            if ref['approval']!='approved': raise s.AppError('REFERENCE_REQUIRED','승인된 기준이 필요합니다.',424)
            if request['params'].get('providerId') not in ('codex','grok','openai'): raise s.AppError('PROVIDER_REQUIRED','생성 연결을 명시적으로 선택하세요.')
            number(request['params'].get('frameCount',1),1,24,'요청 프레임 수',True)
        jid=s.uid(); j=dict(jobId=jid,projectId=pid,operation=operation,status='queued',attemptId=s.uid(),attempts=[],inputRevision=expected,request=request,snapshot=p,requestHash=rh,idempotencyKey=idem,eventSeq=0,step='queued',progress={},artifacts=[],errors=[],createdAt=s.now(),updatedAt=s.now(),engineCommit=s.COMMIT)
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
@app.get('/v1/projects/{pid}/jobs')
def jobs_list(pid:str):
    with s.connect() as c: rows=c.execute('SELECT body FROM jobs WHERE project_id=? ORDER BY created DESC',(pid,)).fetchall()
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
        result_path=s.DATA/'jobs'/jid/j['attemptId']/'result.json'
        completed_result=json.loads(result_path.read_text()) if result_path.exists() else {}
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
        existing=c.execute('SELECT id FROM exports WHERE job_id=?',(j['jobId'],)).fetchone()
        eid=existing[0] if existing else s.uid()
        if not existing: c.execute('INSERT INTO exports VALUES (?,?,?,?)',(eid,j['jobId'],pid,s.dumps({'exportId':eid})))
    return dict(exportId=eid,jobId=j['jobId'])
@app.get('/v1/exports/{eid}')
def export_get(eid:str):
    with s.connect() as c: row=c.execute('SELECT * FROM exports WHERE id=?',(eid,)).fetchone()
    if not row: raise s.AppError('EXPORT_MISSING','출력 결과를 찾을 수 없습니다.',404)
    j=s.get_job(row['job_id']); return dict(exportId=eid,status=j['status'],jobId=j['jobId'],manifest=j.get('result',{}).get('manifest'),files=j.get('artifacts',[]),errors=j['errors'],projectRevision=j['inputRevision'])
@app.get('/v1/projects/{pid}/exports')
def exports_list(pid:str):
    with s.connect() as c: rows=c.execute('SELECT id FROM exports WHERE project_id=?',(pid,)).fetchall()
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
    path=(s.DATA/row['path']).resolve()
    if not path.is_relative_to(s.DATA) or not path.is_file(): raise s.AppError('ARTIFACT_MISSING','결과 파일이 누락되었습니다.',424)
    if s.digest(path.read_bytes())!=row['sha256']: raise s.AppError('ARTIFACT_HASH','결과 파일 무결성 검사에 실패했습니다.',424)
    return FileResponse(path,media_type=row['media_type'],filename=row['name'])

web=s.ROOT/'apps/web/dist'
if web.exists(): app.mount('/',StaticFiles(directory=web,html=True),name='web')
