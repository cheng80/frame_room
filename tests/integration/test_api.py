import io,json,zipfile,subprocess,sys,time,os
from pathlib import Path
import pytest
from PIL import Image,ImageDraw
from fastapi.testclient import TestClient
from services.api import store as s
from services.api.main import app
from services.worker.task import execute
from services.worker.main import publish

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(s,'DATA',tmp_path/'data'); s.init()
    with TestClient(app) as c:
        c.headers['X-Session-Token']=c.get('/v1/health').json()['sessionToken']; yield c

def png(color=(220,80,40,255)):
    img=Image.new('RGBA',(64,64),(13,27,42,0)); ImageDraw.Draw(img).rectangle((20,10,42,50),fill=color)
    out=io.BytesIO();img.save(out,format='PNG');return out.getvalue()
def new(c): return c.post('/v1/projects',json={'name':'시험 캐릭터','cell':{'width':64,'height':64}}).json()
def load(c,p): return c.get('/v1/projects/'+p['projectId']).json()
def edit(c,p,ops):
    response=c.patch('/v1/projects/'+p['projectId']+'/edits',json={'expectedRevision':p['revision'],'operations':ops})
    assert response.status_code==200,response.text
    return response.json()['snapshot']
def upload(c,p,data=None):
    r=c.post('/v1/projects/'+p['projectId']+'/assets',files=[('files',('sprite.png',data or png(),'image/png'))]);assert r.status_code==201,r.text
    return load(c,p),r.json()['assets'][0]
def run_job(jid):
    j=s.get_job(jid);out=s.job_directory(jid)/j['attemptId']/'staging';out.mkdir(parents=True,exist_ok=True)
    result=execute(j,out);publish(j,{'ok':True,'result':result});return s.get_job(jid)
def queue(c,p,operation,asset_ids=[],params={}):
    r=c.post('/v1/projects/'+p['projectId']+'/jobs',json={'operation':operation,'inputRevision':p['revision'],'assetIds':asset_ids,'params':params,'idempotencyKey':s.uid()});assert r.status_code==202,r.text
    return r.json()
def approved(c):
    p=new(c);p,a=upload(c,p)
    r=c.post('/v1/projects/'+p['projectId']+'/reference-revisions',json={'expectedRevision':p['revision'],'reference':{'identityAssetId':a['assetId']}}).json()
    rr=c.post('/v1/reference-revisions/'+r['referenceRevisionId']+'/approve',json={'expectedRevision':r['savedRevision'],'reviewChecks':{'identity':True}});assert rr.status_code==200,rr.text
    p=load(c,p);run_job(queue(c,p,'extract',[a['assetId']],{'mode':'whole'})['jobId']);p=load(c,p)
    f=p['frames'][0];g=p['alignmentGroups'][0]
    p=edit(c,p,[{'type':'setAlignmentGroup','alignmentGroupId':g['alignmentGroupId'],'changes':{'targetAnchor':{'x':31,'y':51}}}])
    p=edit(c,p,[{'type':'setAlignment','frameVersionId':f['frameVersionId'],'alignment':{'sourceAnchor':{'x':31,'y':51},'method':'manual','approval':'approved'}},{'type':'setFrameReview','frameVersionId':f['frameVersionId'],'review':'approved'},{'type':'createClip','clip':{'name':'대기'}}])
    cl=p['clips'][0];p=edit(c,p,[{'type':'addOccurrence','clipId':cl['clipId'],'frameVersionId':f['frameVersionId']}])
    return p,a

def test_asset_generation_enqueues_without_reference_and_preserves_request(client):
    p=new(client);params={'scope':'asset','providerId':'codex','frameCount':1,'prompt':'  첫 원본 이미지  '}
    job=queue(client,p,'generate',params=params)
    saved=s.get_job(job['jobId'])
    assert saved['status']=='queued' and saved['request']['params']==params
    assert saved['snapshot']['references']==[] and saved['snapshot']['activeReferenceRevisionId'] is None
    assert load(client,p)==p

@pytest.mark.parametrize('change',[
    {'frameCount':2}, {'frameCount':True}, {'prompt':''}, {'prompt':'  '}, {'prompt':None},
    {'prompt':123}, {'prompt':'x'*20001}, {'providerId':'grok'}, {'providerId':'openai'},
    {'referenceRevisionId':None}, {'referenceRevisionId':''}, {'referenceRevisionId':'r'},
    {'frameVersionId':None}, {'frameVersionId':''}, {'frameVersionId':'f'},
    {'layoutGuide':True}, {'viewDirection':'side'}, {'unexpected':True},
])
def test_asset_generation_rejects_invalid_params_before_enqueue(client,change):
    p=new(client);params={'scope':'asset','providerId':'codex','frameCount':1,'prompt':'첫 이미지',**change}
    response=client.post('/v1/projects/'+p['projectId']+'/jobs',json={
        'operation':'generate','inputRevision':p['revision'],'params':params,'idempotencyKey':s.uid()})
    assert response.status_code==422,response.text
    assert response.json()['code'].startswith('provider.')
    assert client.get('/v1/projects/'+p['projectId']+'/jobs').json()['jobs']==[]
    assert load(client,p)==p

@pytest.mark.parametrize('existing',[False,True])
def test_asset_generation_rejects_asset_ids_before_enqueue(client,existing):
    p=new(client);aid='unknown'
    if existing: p,asset=upload(client,p);aid=asset['assetId']
    response=client.post('/v1/projects/'+p['projectId']+'/jobs',json={
        'operation':'generate','inputRevision':p['revision'],'assetIds':[aid],
        'params':{'scope':'asset','providerId':'codex','frameCount':1,'prompt':'첫 이미지'},'idempotencyKey':s.uid()})
    assert response.status_code==422,response.text
    assert response.json()['code']=='provider.invalid_asset_settings'
    assert client.get('/v1/projects/'+p['projectId']+'/jobs').json()['jobs']==[]
    assert load(client,p)==p

def test_asset_generation_translates_shared_validator_error(client,monkeypatch):
    from adapters.spritegen import provider
    p=new(client)
    def reject(params,reference=None,regeneration_target=None):
        assert reference is None and regeneration_target is None
        raise provider.ProviderError('provider.test_error','검증 실패',details={'field':'prompt'})
    monkeypatch.setattr(provider,'validate_asset_params',reject)
    response=client.post('/v1/projects/'+p['projectId']+'/jobs',json={
        'operation':'generate','inputRevision':p['revision'],'params':{'scope':'asset'},'idempotencyKey':s.uid()})
    assert response.status_code==422,response.text
    assert response.json()['code']=='provider.test_error'
    assert response.json()['details']=={'field':'prompt'}
    assert client.get('/v1/projects/'+p['projectId']+'/jobs').json()['jobs']==[]

@pytest.mark.parametrize('scope',[None,'states','sheet','frame'])
@pytest.mark.parametrize('reference_state',['missing','draft','approved'])
def test_nonasset_generation_preserves_reference_gate(client,scope,reference_state):
    p=new(client)
    if reference_state!='missing':
        p,a=upload(client,p)
        reference=client.post('/v1/projects/'+p['projectId']+'/reference-revisions',json={
            'expectedRevision':p['revision'],'reference':{'identityAssetId':a['assetId']}}).json()
        if reference_state=='approved':
            assert client.post('/v1/reference-revisions/'+reference['referenceRevisionId']+'/approve',json={
                'expectedRevision':reference['savedRevision'],'reviewChecks':{'identity':True}}).status_code==200
        p=load(client,p)
    params={'providerId':'codex','frameCount':1,'prompt':'기존 생성'}
    if scope is not None: params['scope']=scope
    if reference_state=='draft': params['referenceRevisionId']=reference['referenceRevisionId']
    response=client.post('/v1/projects/'+p['projectId']+'/jobs',json={
        'operation':'generate','inputRevision':p['revision'],'params':params,'idempotencyKey':s.uid()})
    assert response.status_code=={'missing':404,'draft':424,'approved':202}[reference_state],response.text
    if reference_state=='draft': assert response.json()['code']=='REFERENCE_REQUIRED'
    assert len(client.get('/v1/projects/'+p['projectId']+'/jobs').json()['jobs'])==(reference_state=='approved')

def test_image_use_settings_round_trip_without_generation(client):
    p=new(client)
    settings={'providerId':'codex','prompt':'3등신 여성 성직자','frameCount':8,'scope':'sheet','layoutGuide':True,
              'imageUse':'grok-video','videoBase':{'direction':'side','facing':'right','pose':'walk','bodyPlan':'biped','equipment':'staff:right'}}
    p=edit(client,p,[{'type':'setGenerationSettings','settings':settings}])
    assert load(client,p)['generationSettings']==settings
    assert client.get('/v1/projects/'+p['projectId']+'/jobs').json()['jobs']==[]
    assert p['storage']['syncPending'] is False

@pytest.mark.parametrize('settings',[
    {'imageUse':'unknown'}, {'layoutGuide':'true'}, {'videoBase':None}, {'videoBase':[]},
    {'videoBase':{'direction':'unknown'}}, {'videoBase':{'facing':'front'}}, {'videoBase':{'pose':'run'}},
    {'videoBase':{'equipment':False}}, {'videoBase':{'bodyPlan':'x'*2001}}, {'videoBase':{'extra':'unknown'}},
])
def test_invalid_image_use_settings_leave_project_unchanged(client,settings):
    p=new(client)
    response=client.patch('/v1/projects/'+p['projectId']+'/edits',json={'expectedRevision':p['revision'],'operations':[{'type':'setGenerationSettings','settings':settings}]})
    assert response.status_code==422,response.text
    assert load(client,p)['revision']==p['revision']
    assert load(client,p)['generationSettings']==p['generationSettings']

def test_reference_name_create_rename_history_and_legacy_round_trip(client):
    c=client;p,a=approved(c);url='/v1/projects/'+p['projectId']
    created=c.post(url+'/reference-revisions',json={'expectedRevision':p['revision'],'reference':{'identityAssetId':a['assetId'],'name':'  용사 🐉  '}})
    assert created.status_code==201,created.text
    rid=created.json()['referenceRevisionId']
    approval=c.post('/v1/reference-revisions/'+rid+'/approve',json={'expectedRevision':created.json()['savedRevision'],'reviewChecks':{'identity':True}})
    assert approval.status_code==200,approval.text
    p=load(c,p);ref=next(ref for ref in p['references'] if ref['referenceRevisionId']==rid)
    assert ref['name']=='용사 🐉'
    clip=p['clips'][0]
    p=edit(c,p,[{'type':'updateClip','clipId':clip['clipId'],'changes':{'referenceRevisionId':rid}}])
    p=edit(c,p,[{'type':'updateClip','clipId':clip['clipId'],'changes':{'review':'approved'}}])
    assert p['references'][1]['approval']=='approved'
    assert p['clips'][0]['referenceRevisionId']==rid and p['clips'][0]['review']=='approved'
    before={key:p[key] for key in ('activeReferenceRevisionId','assets','frames','alignmentGroups','alignments','clips','generationSettings')}
    original_ref=dict(ref)
    revision=p['revision']
    p=edit(c,p,[{'type':'renameReference','referenceRevisionId':rid,'name':'  장군  '}])
    assert next(ref for ref in p['references'] if ref['referenceRevisionId']==rid)['name']=='장군'
    renamed_ref=next(ref for ref in p['references'] if ref['referenceRevisionId']==rid)
    assert {key:value for key,value in renamed_ref.items() if key!='name'}=={key:value for key,value in original_ref.items() if key!='name'}
    assert {key:p[key] for key in before}==before
    assert load(c,p)['references']==p['references']
    restored=c.post(url+'/restore-revision',json={'expectedRevision':p['revision'],'targetRevision':revision})
    assert restored.status_code==200,restored.text
    assert next(ref for ref in restored.json()['snapshot']['references'] if ref['referenceRevisionId']==rid)['name']=='용사 🐉'
    legacy=load(c,p)
    with s.transaction() as db:
        snapshot=s.get_project(p['projectId'],db);next(ref for ref in snapshot['references'] if ref['referenceRevisionId']==rid).pop('name');s.write_project(db,snapshot,'legacy reference fixture')
    legacy=load(c,legacy)
    assert 'name' not in next(ref for ref in legacy['references'] if ref['referenceRevisionId']==rid)
    renamed=edit(c,legacy,[{'type':'renameReference','referenceRevisionId':rid,'name':'복원 이름'}])
    assert next(ref for ref in renamed['references'] if ref['referenceRevisionId']==rid)['name']=='복원 이름'

@pytest.mark.parametrize('name',['','   ','중복 🧙'])
def test_reference_names_allow_blank_duplicates_and_trim(client,name):
    c=client;p,a=upload(c,new(c));url='/v1/projects/'+p['projectId']
    response=c.post(url+'/reference-revisions',json={'expectedRevision':p['revision'],'reference':{'identityAssetId':a['assetId'],'name':name}})
    assert response.status_code==201,response.text
    p=load(c,p);assert p['references'][0]['name']==name.strip()
    p=edit(c,p,[{'type':'renameReference','referenceRevisionId':response.json()['referenceRevisionId'],'name':name}])
    assert p['references'][0]['name']==name.strip()
    if name=='중복 🧙':
        second=c.post(url+'/reference-revisions',json={'expectedRevision':p['revision'],'reference':{'identityAssetId':a['assetId'],'name':name}})
        assert second.status_code==201,second.text
        assert [ref['name'] for ref in load(c,p)['references']]==[name,name]

@pytest.mark.parametrize('name',[None,False,123,[],{},'x'*201])
def test_reference_name_create_rejects_invalid_values_atomically(client,name):
    c=client;p,a=upload(c,new(c));before=load(c,p)
    response=c.post('/v1/projects/'+p['projectId']+'/reference-revisions',json={'expectedRevision':p['revision'],'reference':{'identityAssetId':a['assetId'],'name':name}})
    assert response.status_code==422,response.text
    assert load(c,p)==before

@pytest.mark.parametrize('operation',[
    {'type':'renameReference','referenceRevisionId':'r','name':None},
    {'type':'renameReference','referenceRevisionId':'r','name':False},
    {'type':'renameReference','referenceRevisionId':'r','name':123},
    {'type':'renameReference','referenceRevisionId':'r','name':[]},
    {'type':'renameReference','referenceRevisionId':'r','name':'x'*201},
    {'type':'renameReference','referenceRevisionId':'r','name':'x','extra':True},
    {'type':'unsupportedReferenceEdit','referenceRevisionId':'r','name':'x'},
])
def test_reference_rename_rejects_invalid_operation_before_mutation(client,operation):
    c=client;p,a=upload(c,new(c));created=c.post('/v1/projects/'+p['projectId']+'/reference-revisions',json={'expectedRevision':p['revision'],'reference':{'identityAssetId':a['assetId']}})
    p=load(c,p);before=p
    operation=dict(operation,referenceRevisionId=created.json()['referenceRevisionId'])
    response=c.patch('/v1/projects/'+p['projectId']+'/edits',json={'expectedRevision':p['revision'],'operations':[{'type':'updateCharacter','name':'변경 불가'},operation]})
    assert response.status_code==422,response.text
    assert load(c,p)==before

def test_reference_rename_unknown_id_batch_atomic_and_stale_conflict(client):
    c=client;p,a=upload(client,new(client));created=c.post('/v1/projects/'+p['projectId']+'/reference-revisions',json={'expectedRevision':p['revision'],'reference':{'identityAssetId':a['assetId'],'name':'기존'}})
    p=load(c,p);url='/v1/projects/'+p['projectId']
    missing=c.patch(url+'/edits',json={'expectedRevision':p['revision'],'operations':[{'type':'updateCharacter','name':'변경 불가'},{'type':'renameReference','referenceRevisionId':'unknown','name':'이름'}]})
    assert missing.status_code==404
    assert load(c,p)==p
    stale=c.patch(url+'/edits',json={'expectedRevision':p['revision']-1,'operations':[{'type':'renameReference','referenceRevisionId':created.json()['referenceRevisionId'],'name':'덮어쓰기'}]})
    assert stale.status_code==409
    assert load(c,p)==p

def test_upload_batch_atomic_immutable_and_duplicate(client):
    c=client;p=new(c);p,a=upload(c,p);h=a['sha256'];path=s.asset_path(a['assetId'])
    r=c.post('/v1/projects/'+p['projectId']+'/assets',files=[('files',('okay.png',png(),'image/png')),('files',('broken.png',b'not png','image/png'))]);assert r.status_code==422
    assert len(load(c,p)['assets'])==1
    p,b=upload(c,p,png((0,255,0,255)));assert a['sha256']!=b['sha256'];assert s.digest(path.read_bytes())==h
    r=c.post('/v1/projects/'+p['projectId']+'/duplicate',json={'expectedRevision':p['revision'],'name':'사본'});assert r.status_code==201;assert r.json()['projectId']!=p['projectId']

def deletion_state():
    """Snapshot only the fixture's temporary store, including retained bytes."""
    with s.connect() as db:
        rows={table:[tuple(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY rowid')]
              for table in ('projects','revisions','assets','jobs','events','artifacts','exports')}
    files={str(path.relative_to(s.DATA)):path.read_bytes()
           for directory in ('assets','jobs','artifacts','uploads')
           for path in (s.DATA/directory).rglob('*') if path.is_file()}
    return rows,files


def test_delete_project_removes_records_preserves_shared_assets_and_other_project(client):
    c=client;p,asset=approved(c)
    p=edit(c,p,[{'type':'updateClip','clipId':p['clips'][0]['clipId'],'changes':{'review':'approved'}}])
    pid=p['projectId'];url='/v1/projects/'+pid
    export_body={'savedRevision':p['revision'],'clipRevisionIds':[p['clips'][0]['clipRevisionId']],'idempotencyKey':s.uid()}
    response=c.post(url+'/exports',json=export_body);assert response.status_code==202,response.text
    exported=response.json();run_job(exported['jobId'])
    duplicate=c.post(url+'/duplicate',json={'expectedRevision':p['revision'],'name':'공유 원본 사본'})
    assert duplicate.status_code==201
    other=duplicate.json();other_url='/v1/projects/'+other['projectId']
    other_export=c.post(other_url+'/exports',json={**export_body,'savedRevision':other['revision'],'clipRevisionIds':[other['clips'][0]['clipRevisionId']],'idempotencyKey':s.uid()})
    assert other_export.status_code==202,other_export.text
    other_output=other_export.json();other_job=run_job(other_output['jobId'])
    before,files=deletion_state()
    deleted_jobs={row[0] for row in before['jobs'] if row[1]==pid}
    deleted_artifacts=[row[0] for row in before['artifacts'] if row[1] in deleted_jobs]
    assert deleted_artifacts and len(deleted_jobs)>=2
    assert c.get(url+'/revisions').json()['revisions']
    assert c.get('/v1/exports/'+exported['exportId']).status_code==200
    root=s.project_folder(pid);other_root=s.project_folder(other['projectId'])
    other_bytes={path:path.read_bytes() for path in other_root.rglob('*') if path.is_file()}
    assert (root/'project.sqlite3').is_file() and any((root/'outputs').rglob('*'))
    response=c.request('DELETE',url,json={'expectedRevision':p['revision']})
    assert response.status_code==200 and response.json()=={'deletedProjectId':pid,'folderDeleted':True}
    # The project's own folder (sources, history DB, jobs, outputs) is gone; nothing beside it remains.
    assert not root.exists() and not [x for x in root.parent.iterdir() if x.name.startswith('.'+root.name)]
    assert {path:path.read_bytes() for path in other_root.rglob('*') if path.is_file() and path.name not in ('project.json','project.sqlite3')}=={k:v for k,v in other_bytes.items() if k.name not in ('project.json','project.sqlite3')}
    assert {item['projectId'] for item in c.get('/v1/projects').json()['projects']}=={other['projectId']}
    for suffix in ('','/revisions','/jobs','/exports'):
        response=c.get(url+suffix)
        assert response.status_code==404 and response.json()['code']=='PROJECT_NOT_FOUND'
    for jid in deleted_jobs:
        for suffix in ('','/events'):
            response=c.get('/v1/jobs/'+jid+suffix)
            assert response.status_code==404 and response.json()['code']=='JOB_NOT_FOUND'
        assert c.post('/v1/jobs/'+jid+'/retry',json={'idempotencyKey':s.uid()}).status_code==404
        assert c.post('/v1/jobs/'+jid+'/cancel',json={'expectedStatus':'succeeded'}).status_code==404
    for aid in deleted_artifacts:
        assert c.get('/v1/artifacts/'+aid+'/download').status_code==404
    assert c.get('/v1/exports/'+exported['exportId']).status_code==404
    # Old revisions, idempotency keys, and job endpoints cannot resurrect this ID.
    assert c.post(url+'/restore-revision',json={'expectedRevision':p['revision'],'targetRevision':1}).status_code==404
    assert c.post(url+'/duplicate',json={'expectedRevision':p['revision'],'name':'부활 금지'}).status_code==404
    assert c.patch(url+'/edits',json={'expectedRevision':p['revision'],'operations':[{'type':'updateCharacter','name':'부활 금지'}]}).status_code==404
    assert c.post(url+'/exports',json=export_body).status_code==404
    assert c.post(url+'/jobs',json={'operation':'inspect','inputRevision':p['revision'],'idempotencyKey':s.uid()}).status_code==404
    assert c.post(url+'/backup',json={'savedRevision':p['revision']}).status_code==404
    assert c.request('DELETE',url,json={'expectedRevision':p['revision']}).status_code==404
    after,remaining_files=deletion_state()
    for table in ('projects','revisions','jobs','exports'):
        key_index=1 if table=='jobs' else 2 if table=='exports' else 0
        assert after[table]==[row for row in before[table] if row[key_index]!=pid],table
    for table in ('events','artifacts'):
        key_index=0 if table=='events' else 1
        assert after[table]==[row for row in before[table] if row[key_index] not in deleted_jobs],table
    assert after['assets']==before['assets']
    assert remaining_files==files
    assert load(c,other)==other
    assert asset['assetId'] in {a['assetId'] for a in other['assets']}
    for a in other['assets']:
        response=c.get(a['url']);assert response.status_code==200
        assert s.digest(response.content)==a['sha256']
    assert c.get('/v1/exports/'+other_output['exportId']).status_code==200
    for artifact in other_job['artifacts']:
        assert c.get(artifact['url']).status_code==200


@pytest.mark.parametrize('status',['queued','running','cancel_requested'])
def test_delete_project_rejects_active_jobs_without_changes(client,status):
    c=client;p,asset=upload(c,new(c));j=queue(c,p,'extract',[asset['assetId']],{'mode':'whole'})
    with s.transaction() as db:
        job=s.get_job(j['jobId'],db);job['status']=status;s.write_job(db,job)
    before=deletion_state()
    response=c.request('DELETE','/v1/projects/'+p['projectId'],json={'expectedRevision':p['revision']})
    assert response.status_code==409 and response.json()['code']=='PROJECT_BUSY'
    assert '취소' in response.json()['message']
    assert deletion_state()==before
    # A cancellation request is still active; only its terminal result unblocks deletion.
    with s.transaction() as db:
        job=s.get_job(j['jobId'],db);job['status']='canceled';s.write_job(db,job)
    assert c.request('DELETE','/v1/projects/'+p['projectId'],json={'expectedRevision':p['revision']}).status_code==200


@pytest.mark.parametrize('status',['succeeded','needs_review','failed','canceled','interrupted','provider_outcome_unknown'])
def test_delete_project_allows_terminal_jobs(client,status):
    c=client;p=new(c);j=queue(c,p,'inspect')
    with s.transaction() as db:
        job=s.get_job(j['jobId'],db);job['status']=status;s.write_job(db,job)
    response=c.request('DELETE','/v1/projects/'+p['projectId'],json={'expectedRevision':p['revision']})
    assert response.status_code==200
    assert c.post('/v1/jobs/'+j['jobId']+'/retry',json={'idempotencyKey':s.uid()}).status_code==404
    with s.connect() as db:
        assert not db.execute('SELECT 1 FROM events WHERE job_id=?',(j['jobId'],)).fetchone()


@pytest.mark.parametrize('body',[
    {},{'expectedRevision':0},{'expectedRevision':-1},{'expectedRevision':True},
    {'expectedRevision':False},{'expectedRevision':1.0},{'expectedRevision':1.5},
    {'expectedRevision':'1'},{'expectedRevision':None},{'expectedRevision':[]},
    {'expectedRevision':{}},{'expectedRevision':1,'force':True},None,[],
])
def test_delete_project_strict_body_preserves_records(client,body):
    c=client;p=new(c);queue(c,p,'inspect');before=deletion_state()
    response=c.request('DELETE','/v1/projects/'+p['projectId'],json=body)
    assert response.status_code==422 and response.json()['code']=='VALIDATION_ERROR'
    assert deletion_state()==before


@pytest.mark.parametrize('headers',[
    {'X-Session-Token':''},{'X-Session-Token':'incorrect'},
    {'Origin':'https://evil.invalid'},
])
def test_delete_project_security_preserves_records(client,headers):
    c=client;p,asset=upload(c,new(c));before=deletion_state()
    response=c.request('DELETE','/v1/projects/'+p['projectId'],json={'expectedRevision':p['revision']},headers=headers)
    assert response.status_code==403
    assert response.json()['code']==('ORIGIN_FORBIDDEN' if 'Origin' in headers else 'SESSION_REQUIRED')
    assert deletion_state()==before


def test_delete_project_revision_conflict_precedes_busy_check(client):
    c=client;p=new(c);old=p['revision'];p,asset=upload(c,p);queue(c,p,'inspect')
    before=deletion_state()
    response=c.request('DELETE','/v1/projects/'+p['projectId'],json={'expectedRevision':old})
    assert response.status_code==409 and response.json()['code']=='REVISION_CONFLICT'
    assert response.json()['details']=={'expectedRevision':old,'savedRevision':p['revision']}
    assert deletion_state()==before
    response=c.request('DELETE','/v1/projects/missing',json={'expectedRevision':1})
    assert response.status_code==404 and response.json()['code']=='PROJECT_NOT_FOUND'
    assert deletion_state()==before


def test_delete_project_rolls_back_all_dependent_deletes(client):
    import sqlite3
    c=client;p,asset=upload(c,new(c))
    response=c.post('/v1/projects/'+p['projectId']+'/backup',json={'savedRevision':p['revision']})
    run_job(response.json()['jobId']);before=deletion_state()
    with s.connect() as db:
        db.execute("CREATE TRIGGER reject_project_delete BEFORE DELETE ON projects BEGIN SELECT RAISE(ABORT, 'injected delete failure'); END")
    root=s.project_folder(p['projectId']);folder_before={x:x.read_bytes() for x in root.rglob('*') if x.is_file()}
    with pytest.raises(sqlite3.IntegrityError,match='injected delete failure'):
        c.request('DELETE','/v1/projects/'+p['projectId'],json={'expectedRevision':p['revision']})
    assert deletion_state()==before
    assert {x:x.read_bytes() for x in root.rglob('*') if x.is_file()}==folder_before


@pytest.mark.parametrize('completed',[False,True])
def test_delete_project_serializes_with_export_registration(client,completed):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    c=client;p,_=approved(c)
    p=edit(c,p,[{'type':'updateClip','clipId':p['clips'][0]['clipId'],'changes':{'review':'approved'}}])
    pid=p['projectId'];url='/v1/projects/'+pid
    body={'savedRevision':p['revision'],'clipRevisionIds':[p['clips'][0]['clipRevisionId']],'idempotencyKey':s.uid()}
    if completed:
        response=c.post(url+'/exports',json=body);assert response.status_code==202
        run_job(response.json()['jobId'])
    barrier=Barrier(2)
    def remove():
        barrier.wait(timeout=5)
        return c.request('DELETE',url,json={'expectedRevision':p['revision']})
    def submit():
        barrier.wait(timeout=5)
        return c.post(url+'/exports',json=body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        removing=pool.submit(remove);submitting=pool.submit(submit)
        deleted=removing.result(timeout=10);exported=submitting.result(timeout=10)
    with s.connect() as db:
        if deleted.status_code==200:
            assert exported.status_code in (202,404,424),exported.text
            # Deletion can finish between the initial snapshot and asset check.
            if exported.status_code!=202:
                assert exported.json()['code']=={404:'PROJECT_NOT_FOUND',424:'ASSET_MISSING'}[exported.status_code]
            assert not db.execute('SELECT 1 FROM exports WHERE project_id=?',(pid,)).fetchone()
            assert not db.execute('SELECT 1 FROM jobs WHERE project_id=?',(pid,)).fetchone()
        else:
            assert deleted.status_code==409 and deleted.json()['code']=='PROJECT_BUSY'
            assert not completed and exported.status_code==202,exported.text
            record=exported.json()
            assert db.execute('SELECT job_id FROM exports WHERE id=?',(record['exportId'],)).fetchone()[0]==record['jobId']


def test_export_registration_failure_rolls_back_job_events_and_outbox(client):
    import sqlite3
    c=client;p,_=approved(c)
    p=edit(c,p,[{'type':'updateClip','clipId':p['clips'][0]['clipId'],'changes':{'review':'approved'}}])
    folder=s.project_folder(p['projectId']);portable=(folder/'project.sqlite3').read_bytes()
    before=deletion_state()
    with s.connect() as db:
        db.execute("CREATE TRIGGER reject_export BEFORE INSERT ON exports BEGIN SELECT RAISE(ABORT, 'injected export failure'); END")
    with pytest.raises(sqlite3.IntegrityError,match='injected export failure'):
        c.post('/v1/projects/'+p['projectId']+'/exports',json={'savedRevision':p['revision'],
            'clipRevisionIds':[p['clips'][0]['clipRevisionId']],'idempotencyKey':s.uid()})
    assert deletion_state()==before and (folder/'project.sqlite3').read_bytes()==portable
    with s.connect() as db:
        assert not db.execute('SELECT 1 FROM folder_sync WHERE project_id=?',(p['projectId'],)).fetchone()


def test_export_concurrent_idempotency_preserves_snapshot_and_running_job(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from services.worker.main import claim
    c=client;p,_=approved(c)
    p=edit(c,p,[{'type':'updateClip','clipId':p['clips'][0]['clipId'],'changes':{'review':'approved'}}])
    url='/v1/projects/'+p['projectId']+'/exports'
    body={'savedRevision':p['revision'],'clipRevisionIds':[p['clips'][0]['clipRevisionId']],'idempotencyKey':s.uid()}
    barrier=Barrier(2)
    def submit():
        barrier.wait(timeout=5)
        return c.post(url,json=body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(submit) for _ in range(2)]
        responses=[future.result(timeout=10) for future in futures]
    assert all(r.status_code==202 for r in responses),[r.text for r in responses]
    record=responses[0].json();assert responses[1].json()==record
    job=s.get_job(record['jobId']);assert job['snapshot']==s.get_project(p['projectId'])
    claimed=claim();assert claimed['jobId']==job['jobId'] and claimed['exportId']==record['exportId']
    running=s.get_job(job['jobId'])
    repeated=c.post(url,json=body)
    assert repeated.status_code==202 and repeated.json()==record
    assert s.get_job(job['jobId'])==running
    conflict=c.post(url,json={**body,'outlineMode':'preview-only'})
    assert conflict.status_code==409 and conflict.json()['code']=='IDEMPOTENCY_CONFLICT'
    with s.connect() as db:
        assert db.execute("SELECT count(*) FROM jobs WHERE project_id=? AND operation='export'",(p['projectId'],)).fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM exports WHERE job_id=?',(job['jobId'],)).fetchone()[0]==1


def test_export_postcommit_folder_failure_retains_atomic_records_for_retry(client,monkeypatch):
    import sqlite3
    from services.api import project_folders
    c=client;p,_=approved(c)
    p=edit(c,p,[{'type':'updateClip','clipId':p['clips'][0]['clipId'],'changes':{'review':'approved'}}])
    url='/v1/projects/'+p['projectId']+'/exports'
    body={'savedRevision':p['revision'],'clipRevisionIds':[p['clips'][0]['clipRevisionId']],'idempotencyKey':s.uid()}
    def unavailable(*_): raise OSError('injected folder failure')
    with monkeypatch.context() as fault:
        fault.setattr(project_folders,'_sync',unavailable)
        response=c.post(url,json=body)
    assert response.status_code==503 and response.json()['code']=='PROJECT_FOLDER_SYNC_FAILED'
    with s.connect() as db:
        row=db.execute("SELECT id FROM jobs WHERE project_id=? AND operation='export'",(p['projectId'],)).fetchone()
        jid=row[0];eid=db.execute('SELECT id FROM exports WHERE job_id=?',(jid,)).fetchone()[0]
        assert db.execute('SELECT 1 FROM folder_sync WHERE project_id=?',(p['projectId'],)).fetchone()
    snapshot=s.get_job(jid)['snapshot']
    response=c.post(url,json=body)
    assert response.status_code==202 and response.json()=={'exportId':eid,'jobId':jid}
    assert s.get_job(jid)['snapshot']==snapshot
    # An idempotent read does not dirty the transaction again; retain the outbox
    # for the existing startup/worker/explicit folder flush recovery path.
    project_folders.flush([p['projectId']])
    with sqlite3.connect(s.project_folder(p['projectId'])/'project.sqlite3') as db:
        assert db.execute('SELECT job_id FROM exports WHERE id=?',(eid,)).fetchone()[0]==jid
        assert db.execute('SELECT status FROM jobs WHERE id=?',(jid,)).fetchone()[0]=='queued'


def test_delete_project_serializes_with_new_job_submission(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    c=client;p=new(c);url='/v1/projects/'+p['projectId'];barrier=Barrier(2)
    def remove():
        barrier.wait(timeout=5)
        return c.request('DELETE',url,json={'expectedRevision':p['revision']})
    def submit():
        barrier.wait(timeout=5)
        return c.post(url+'/jobs',json={'operation':'inspect','inputRevision':p['revision'],'idempotencyKey':s.uid()})
    with ThreadPoolExecutor(max_workers=2) as pool:
        removing=pool.submit(remove);submitting=pool.submit(submit)
        deleted=removing.result(timeout=10);queued=submitting.result(timeout=10)
    if deleted.status_code==200:
        assert queued.status_code==404 and queued.json()['code']=='PROJECT_NOT_FOUND'
        with s.connect() as db:
            assert not db.execute('SELECT 1 FROM jobs WHERE project_id=?',(p['projectId'],)).fetchone()
    else:
        assert deleted.status_code==409 and deleted.json()['code']=='PROJECT_BUSY'
        assert queued.status_code==202
        assert load(c,p)==p

def test_conflict_and_empty_export(client):
    c=client;p=new(c);p2=edit(c,p,[{'type':'createClip','clip':{'name':'빈 동작'}}])
    r=c.patch('/v1/projects/'+p['projectId']+'/edits',json={'expectedRevision':p['revision'],'operations':[{'type':'updateCharacter','name':'덮어쓰기'}]});assert r.status_code==409
    assert load(c,p)['characterName']!='덮어쓰기'
    r=c.post('/v1/projects/'+p['projectId']+'/exports',json={'savedRevision':p2['revision'],'clipRevisionIds':[p2['clips'][0]['clipRevisionId']],'idempotencyKey':s.uid()});assert r.status_code==422;assert r.json()['code']=='EMPTY_TIMELINE'
    assert c.patch('/v1/projects/'+p['projectId']+'/edits',json={'expectedRevision':p2['revision'],'operations':[{'type':'arbitraryPatch','path':'../../'}]}).status_code==422

def test_delete_clip_preserves_sources_other_clips_and_restores_history(client):
    c=client;p,a=approved(c);target=p['clips'][0]
    p=edit(c,p,[{'type':'updateClip','clipId':target['clipId'],'changes':{'review':'approved'}}])
    p=edit(c,p,[{'type':'createClip','clip':{'name':'보존할 동작'}}]);keeper=p['clips'][1]
    p=edit(c,p,[{'type':'addOccurrence','clipId':keeper['clipId'],'frameVersionId':p['frames'][0]['frameVersionId']},
                 {'type':'updateClip','clipId':keeper['clipId'],'changes':{'review':'approved'}},
                 {'type':'setGenerationSettings','settings':{'clipId':target['clipId'],'prompt':'기존 생성 설정'}}])
    with s.transaction() as db:
        snapshot=s.get_project(p['projectId'],db);video=s.DATA/'videos'/'fixture.mp4';video.parent.mkdir(parents=True,exist_ok=True);video.write_bytes(b'fixture video')
        db.execute('INSERT INTO videos VALUES (?,?,?)',('fixture-video',s.dumps({'videoId':'fixture-video','sha256':s.digest(video.read_bytes()),'originalFilename':'fixture.mp4','mediaType':'video/mp4','provenance':{'kind':'test'}}),s.stored_path(video)))
        snapshot['videos']=[{'videoId':'fixture-video','sha256':s.digest(video.read_bytes()),'originalFilename':'fixture.mp4','mediaType':'video/mp4','provenance':{'kind':'test'}}];s.write_project(db,snapshot,'시험 영상 fixture')
    p=load(c,p);before=p;target_revision=p['revision'];url='/v1/projects/'+p['projectId']
    keeper=next(clip for clip in before['clips'] if clip['clipId']!=target['clipId'])
    target_revision_id=next(clip['clipRevisionId'] for clip in before['clips'] if clip['clipId']==target['clipId'])
    export=c.post(url+'/exports',json={'savedRevision':p['revision'],'clipRevisionIds':[target_revision_id],'idempotencyKey':s.uid()})
    assert export.status_code==202,export.text
    existing_exports=c.get(url+'/exports').json()
    response=c.patch(url+'/edits',json={'expectedRevision':p['revision'],'operations':[{'type':'deleteClip','clipId':target['clipId']}]})
    assert response.status_code==200,response.text
    assert response.json()['snapshot']['clips']==[keeper]
    reopened=load(c,p)
    assert reopened==response.json()['snapshot']
    for key in ('frames','assets','videos','alignments','references','generationSettings'):
        assert reopened[key]==before[key]
    assert reopened['generationSettings']['clipId']==target['clipId']
    assert target_revision in {item['revision'] for item in c.get(url+'/revisions').json()['revisions']}
    assert c.get(url+'/exports').json()==existing_exports
    restored=c.post(url+'/restore-revision',json={'expectedRevision':reopened['revision'],'targetRevision':target_revision})
    assert restored.status_code==200,restored.text
    assert {clip['clipId'] for clip in restored.json()['snapshot']['clips']}=={target['clipId'],keeper['clipId']}
    assert s.digest(s.asset_path(a['assetId']).read_bytes())==a['sha256']

def test_delete_last_clip_and_rejects_conflicts_or_unknown_ids_atomically(client):
    c=client;p=new(c);p=edit(c,p,[{'type':'createClip','clip':{'name':'마지막 동작'}}]);clip=p['clips'][0];url='/v1/projects/'+p['projectId']
    stale=c.patch(url+'/edits',json={'expectedRevision':p['revision']-1,'operations':[{'type':'deleteClip','clipId':clip['clipId']}]})
    assert stale.status_code==409
    missing=c.patch(url+'/edits',json={'expectedRevision':p['revision'],'operations':[{'type':'updateCharacter','name':'변경되면 안 됨'},{'type':'deleteClip','clipId':'missing'}]})
    assert missing.status_code==404
    assert load(c,p)==p
    deleted=c.patch(url+'/edits',json={'expectedRevision':p['revision'],'operations':[{'type':'deleteClip','clipId':clip['clipId']}]})
    assert deleted.status_code==200 and deleted.json()['snapshot']['clips']==[]
    assert load(c,p)['clips']==[]

def test_occurrences_timing_restore_and_original(client):
    c=client;p,a=approved(c);cl=p['clips'][0];o=cl['occurrences'][0]
    p=edit(c,p,[{'type':'duplicateOccurrence','clipId':cl['clipId'],'occurrenceId':o['occurrenceId']}]);two=p['clips'][0]['occurrences'];assert two[0]['occurrenceId']!=two[1]['occurrenceId'];assert two[0]['frameVersionId']==two[1]['frameVersionId']
    p=edit(c,p,[{'type':'setTiming','clipId':cl['clipId'],'occurrenceId':two[0]['occurrenceId'],'durationMs':80,'timingMode':'explicit'},{'type':'updateClip','clipId':cl['clipId'],'changes':{'defaultFps':5}}]);assert [o['durationMs'] for o in p['clips'][0]['occurrences']]==[80,200]
    rev=p['revision'];p=edit(c,p,[{'type':'removeOccurrence','clipId':cl['clipId'],'occurrenceId':two[0]['occurrenceId']}]);r=c.post('/v1/projects/'+p['projectId']+'/restore-revision',json={'expectedRevision':p['revision'],'targetRevision':rev});assert r.status_code==200;assert [o['durationMs'] for o in r.json()['snapshot']['clips'][0]['occurrences']]==[80,200]
    assert s.digest(s.asset_path(a['assetId']).read_bytes())==a['sha256']

def test_job_idempotency_cancel_unknown(client):
    c=client;p=new(c);p,a=upload(c,p);body={'operation':'extract','inputRevision':p['revision'],'assetIds':[a['assetId']],'params':{'mode':'whole'},'idempotencyKey':'repeat'};url='/v1/projects/'+p['projectId']+'/jobs'
    first=c.post(url,json=body);second=c.post(url,json=body);assert first.json()['jobId']==second.json()['jobId']
    body['params']['mode']='components';assert c.post(url,json=body).status_code==409
    jid=first.json()['jobId'];assert c.post('/v1/jobs/'+jid+'/cancel',json={'expectedStatus':'queued'}).status_code==202
    assert c.get('/v1/jobs/'+jid).json()['status']=='canceled'
    with s.transaction() as db:
        j=s.get_job(jid,db);j['status']='provider_outcome_unknown';s.write_job(db,j)
    assert c.post('/v1/jobs/'+jid+'/retry',json={'idempotencyKey':'retry'}).status_code==409

def test_backup_restore_and_path_attack(client):
    c=client;p,a=approved(c)
    response=c.post('/v1/projects/'+p['projectId']+'/backup',json={'savedRevision':p['revision']});j=run_job(response.json()['jobId'])
    raw=c.get(j['artifacts'][0]['url']).content
    r=c.post('/v1/projects/restore',files={'backupZip':('backup.zip',raw,'application/zip')},data={'idempotencyKey':s.uid()});assert r.status_code==202,r.text
    restored=run_job(r.json()['jobId']);other=load(c,{'projectId':restored['result']['projectId']});assert other['projectId']!=p['projectId'];assert len(other['frames'])==1;assert other['assets'][0]['sha256']==a['sha256']
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z: z.writestr('../outside','bad')
    r=c.post('/v1/projects/restore',files={'backupZip':('attack.zip',b.getvalue(),'application/zip')},data={'idempotencyKey':s.uid()})
    with pytest.raises(s.AppError) as error: run_job(r.json()['jobId'])
    assert error.value.code=='BACKUP_PATH'

def test_export_full_rgba_and_immutable_snapshot(client):
    c=client;p,a=approved(c);cl=p['clips'][0];p=edit(c,p,[{'type':'updateClip','clipId':cl['clipId'],'changes':{'review':'approved'}}])
    r=c.post('/v1/projects/'+p['projectId']+'/exports',json={'savedRevision':p['revision'],'clipRevisionIds':[p['clips'][0]['clipRevisionId']],'idempotencyKey':s.uid()});assert r.status_code==202,r.text
    old=p['revision'];p=edit(c,p,[{'type':'updateCharacter','name':'출력 중 수정'}]);j=run_job(r.json()['jobId'])
    assert j['result']['manifest']['projectRevision']==old
    out=c.get('/v1/exports/'+r.json()['exportId']).json();assert out['status']=='succeeded';assert out['files']
    assert c.get('/v1/projects/'+p['projectId']).json()['characterName']=='출력 중 수정'

def test_local_session_and_origin(client):
    c=client
    assert c.post('/v1/projects',json={'name':'attack'},headers={'origin':'https://evil.invalid'}).status_code==403
    assert c.post('/v1/projects',json={'name':'attack'},headers={'X-Session-Token':''}).status_code==403
    assert c.get('/v1/health',headers={'host':'evil.invalid'}).status_code==400

def test_failed_save_rolls_back_and_invalid_timing(client,monkeypatch):
    c=client;p,a=approved(c);cl=p['clips'][0];oid=cl['occurrences'][0]['occurrenceId']
    for duration in (0,-1,1.2,True,60001):
        r=c.patch('/v1/projects/'+p['projectId']+'/edits',json={'expectedRevision':p['revision'],'operations':[{'type':'setTiming','clipId':cl['clipId'],'occurrenceId':oid,'durationMs':duration}]})
        assert r.status_code==422
    before=load(c,p)
    with pytest.raises(RuntimeError):
        with s.transaction() as db:
            snap=s.get_project(p['projectId'],db);snap['name']='중단된 저장';s.write_project(db,snap,'fault injection');raise RuntimeError('before commit')
    assert load(c,p)==before

def test_partial_regeneration_preserves_lineage(client):
    c=client;p,a=approved(c);old=p['frames'][0]
    gen={'generationVersionId':s.uid(),'parentFrameVersionId':old['frameVersionId']}
    with s.transaction() as db:
        pp=s.get_project(p['projectId'],db);asset=s.register_asset(png((20,140,240,255)),'regenerated.png','source',{'kind':'mock-provider','generationVersionId':gen['generationVersionId']},c=db);pp['assets'].append(asset);pp['generations'].append(gen);s.write_project(db,pp,'mock generation fixture')
    p=load(c,p);run_job(queue(c,p,'cutout',[asset['assetId']],{'key':'green'})['jobId']);p=load(c,p)
    run_job(queue(c,p,'extract',[p['assets'][-1]['assetId']],{'mode':'whole'})['jobId']);p=load(c,p);newer=p['frames'][-1]
    assert newer['frameId']==old['frameId'];assert newer['frameVersionId']!=old['frameVersionId'];assert newer['parentFrameVersionId']==old['frameVersionId']
    assert p['alignments'][newer['frameVersionId']]['approval']=='pending'
    assert p['clips'][0]['occurrences'][0]['frameVersionId']==old['frameVersionId']

def test_rejected_frame_reason_survives_reopen_and_blocks_export(client):
    c=client;p,a=approved(c);fid=p['frames'][0]['frameVersionId'];cid=p['clips'][0]['clipId']
    r=c.patch('/v1/projects/'+p['projectId']+'/edits',json={'expectedRevision':p['revision'],'operations':[{'type':'setFrameReview','frameVersionId':fid,'review':'rejected'}]})
    assert r.status_code==422
    p=edit(c,p,[{'type':'setFrameReview','frameVersionId':fid,'review':'rejected','reason':'장비가 승인 기준과 다릅니다.'}])
    reopened=load(c,p);f=reopened['frames'][0]
    assert f['review']=='rejected' and f['reviewReason']=='장비가 승인 기준과 다릅니다.'
    assert f['reviewReferenceRevisionId']==p['activeReferenceRevisionId']
    p=edit(c,p,[{'type':'updateClip','clipId':cid,'changes':{'review':'approved'}}])
    r=c.post('/v1/projects/'+p['projectId']+'/exports',json={'savedRevision':p['revision'],'clipRevisionIds':[p['clips'][0]['clipRevisionId']],'idempotencyKey':s.uid()})
    assert r.status_code==422

@pytest.mark.parametrize('mutation', ['timing','transform','pixels','order','group','anchor','reference','outline'])
def test_edits_revoke_clip_approval_and_block_exports(client,mutation):
    c=client;p,_=approved(c);cl=p['clips'][0];cid=cl['clipId'];fid=p['frames'][0]['frameVersionId'];oid=cl['occurrences'][0]['occurrenceId']
    p=edit(c,p,[{'type':'updateClip','clipId':cid,'changes':{'review':'approved'}}])
    operations={
        'timing':{'type':'setTiming','clipId':cid,'occurrenceId':oid,'durationMs':150},
        'transform':{'type':'setTransform','clipId':cid,'occurrenceId':oid,'transform':{'dx':1}},
        'pixels':{'type':'setPixelEdits','clipId':cid,'occurrenceId':oid,'pixelEdits':[{'x':25,'y':25,'color':[0,0,0,0]}]},
        'order':{'type':'reorderOccurrences','clipId':cid,'occurrenceIds':[oid]},
        'group':{'type':'setAlignmentGroup','alignmentGroupId':p['alignmentGroups'][0]['alignmentGroupId'],'changes':{'targetAnchor':{'x':30,'y':50}}},
        'anchor':{'type':'setAlignment','frameVersionId':fid,'alignment':{**p['alignments'][fid],'sourceAnchor':{'x':30,'y':50}}},
        'reference':{'type':'updateClip','clipId':cid,'changes':{'referenceRevisionId':p['activeReferenceRevisionId'],'review':'approved'}},
        'outline':{'type':'setOutline','outline':{'enabled':True}},
    }
    p=edit(c,p,[operations[mutation]]);reopened=load(c,p)
    assert reopened['clips'][0]['review']=='pending'
    assert reopened['clips'][0]['reviewInvalidatedReason']
    response=c.post('/v1/projects/'+p['projectId']+'/exports',json={'savedRevision':p['revision'],'clipRevisionIds':[p['clips'][0]['clipRevisionId']],'idempotencyKey':s.uid()})
    assert response.status_code==422 and response.json()['code']=='CLIP_UNAPPROVED'
    if mutation in ('anchor','group'):
        assert p['alignments'][fid]['approval']=='pending'
        assert p['alignments'][fid]['reviewInvalidatedReason']
        p=edit(c,p,[{'type':'updateClip','clipId':cid,'changes':{'review':'approved'}}])
        response=c.post('/v1/projects/'+p['projectId']+'/exports',json={'savedRevision':p['revision'],'clipRevisionIds':[p['clips'][0]['clipRevisionId']],'idempotencyKey':s.uid()})
        assert response.status_code==422 and response.json()['code']=='ANCHOR_UNAPPROVED'
        # Full UI echo contains the server-owned reason; reapproval must accept it.
        p=edit(c,p,[{'type':'setAlignment','frameVersionId':fid,'alignment':{**p['alignments'][fid],'approval':'approved'}}])
        assert 'reviewInvalidatedReason' not in p['alignments'][fid]
    p=edit(c,p,[{'type':'updateClip','clipId':cid,'changes':{'review':'approved'}}])
    assert 'reviewInvalidatedReason' not in p['clips'][0]
    response=c.post('/v1/projects/'+p['projectId']+'/exports',json={'savedRevision':p['revision'],'clipRevisionIds':[p['clips'][0]['clipRevisionId']],'idempotencyKey':s.uid()})
    assert response.status_code==202,response.text
    assert run_job(response.json()['jobId'])['status']=='succeeded'


def test_export_rejects_duplicate_missing_and_stale_selections(client):
    c=client;p,_=approved(c);p=edit(c,p,[{'type':'updateClip','clipId':p['clips'][0]['clipId'],'changes':{'review':'approved'}}]);rid=p['clips'][0]['clipRevisionId']
    for selection,code in [([rid,rid],'INVALID_CLIP_SELECTION'),([rid,'missing'],'ENTITY_NOT_FOUND')]:
        response=c.post('/v1/projects/'+p['projectId']+'/exports',json={'savedRevision':p['revision'],'clipRevisionIds':selection,'idempotencyKey':s.uid()})
        assert response.status_code in (404,422) and response.json()['code']==code
    # Worker must not silently export the valid subset of a stale selection.
    for selection,code in [([rid,'missing'],'CLIP_MISSING'),([rid,rid],'INVALID_CLIP_SELECTION')]:
        job={'snapshot':p,'operation':'export','jobId':s.uid(),'request':{'clipRevisionIds':selection}}
        with pytest.raises(s.AppError) as error: execute(job,s.DATA/'jobs'/job['jobId']/'staging')
        assert error.value.code==code
    with s.transaction() as db:
        p['alignments'][p['frames'][0]['frameVersionId']]['groupRevisionId']='stale';s.write_project(db,p,'stale anchor test fixture')
    response=c.post('/v1/projects/'+p['projectId']+'/exports',json={'savedRevision':p['revision'],'clipRevisionIds':[rid],'idempotencyKey':s.uid()})
    assert response.status_code==422 and response.json()['code']=='ANCHOR_UNAPPROVED'


def test_public_job_scope_for_legacy_records_and_future_events(client):
    c=client;p,_=approved(c);cid=p['clips'][0]['clipId']
    response=queue(c,p,'inspect',params={'clipIds':[cid]})
    assert response['inspectionClipIds']==[cid]
    jid=response['jobId']
    # Request metadata stays private; the field is derived for legacy job rows.
    with s.connect() as db:
        stored=db.execute('SELECT body FROM jobs WHERE id=?',(jid,)).fetchone()[0]
        event=json.loads(db.execute('SELECT body FROM events WHERE job_id=?',(jid,)).fetchone()[0])
    assert 'inspectionClipIds' not in json.loads(stored)
    assert event['inspectionClipIds']==[cid] and 'snapshot' not in event and 'request' not in event
    for public in [c.get('/v1/jobs/'+jid).json(),c.get('/v1/projects/'+p['projectId']+'/jobs').json()['jobs'][0]]:
        assert public['inspectionClipIds']==[cid]
        assert 'snapshot' not in public and 'request' not in public
    with s.connect() as db: assert db.execute('SELECT body FROM jobs WHERE id=?',(jid,)).fetchone()[0]==stored


def test_extract_public_lineage_new_and_legacy_is_read_only(client):
    import copy
    c=client;p,_=approved(c)
    first=p['frames'][0]['frameVersionId']
    job=queue(c,p,'extract',[p['assets'][0]['assetId']],{'mode':'whole'})
    completed=run_job(job['jobId']);p=load(c,p)
    added=p['frames'][-1]['frameVersionId']
    assert completed['result']['frameVersionIds']==[added]
    assert first not in completed['result']['frameVersionIds']
    legacy=copy.deepcopy(completed);legacy['result'].pop('frameVersionIds')
    before=copy.deepcopy(legacy)
    with s.connect() as db:
        stored_jobs=db.execute('SELECT id,body FROM jobs ORDER BY id').fetchall()
        stored_revisions=db.execute('SELECT project_id,revision,snapshot,reason FROM revisions ORDER BY project_id,revision').fetchall()
    # Read an old-format job without backfilling either persisted jobs or snapshots.
    public=s.public_job(legacy)
    assert public['result']['frameVersionIds']==[added]
    assert 'snapshot' not in public and 'request' not in public
    assert legacy==before
    with s.connect() as db:
        assert [tuple(r) for r in db.execute('SELECT id,body FROM jobs ORDER BY id')]==[tuple(r) for r in stored_jobs]
        assert [tuple(r) for r in db.execute('SELECT project_id,revision,snapshot,reason FROM revisions ORDER BY project_id,revision')]==[tuple(r) for r in stored_revisions]


@pytest.mark.parametrize('missing_evidence',['before','after','reason','before_project','after_project','revision','other_project'])
def test_extract_public_lineage_requires_both_matching_snapshots(client,missing_evidence):
    import copy
    c=client;p,_=approved(c)
    job=queue(c,p,'extract',[p['assets'][0]['assetId']],{'mode':'whole'})
    legacy=copy.deepcopy(run_job(job['jobId']));legacy['result'].pop('frameVersionIds')
    revision=legacy['result']['savedRevision'];pid=p['projectId']
    # Corrupt only this test's temporary database to exercise each missing proof.
    with s.transaction() as db:
        if missing_evidence in ('before','after'):
            db.execute('DELETE FROM revisions WHERE project_id=? AND revision=?',(pid,revision-1 if missing_evidence=='before' else revision))
        elif missing_evidence=='reason':
            db.execute('UPDATE revisions SET reason=? WHERE project_id=? AND revision=?',('편집',pid,revision))
        elif missing_evidence in ('before_project','after_project'):
            rev=revision-1 if missing_evidence=='before_project' else revision
            snapshot=json.loads(db.execute('SELECT snapshot FROM revisions WHERE project_id=? AND revision=?',(pid,rev)).fetchone()[0])
            snapshot['projectId']='different-project'
            db.execute('UPDATE revisions SET snapshot=? WHERE project_id=? AND revision=?',(s.dumps(snapshot),pid,rev))
        elif missing_evidence=='revision': legacy['result'].pop('savedRevision')
        elif missing_evidence=='other_project': legacy['projectId']='different-project'
    assert 'frameVersionIds' not in s.public_job(legacy)['result']
