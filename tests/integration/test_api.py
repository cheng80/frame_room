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
    j=s.get_job(jid);out=s.DATA/'jobs'/jid/j['attemptId']/'staging';out.mkdir(parents=True,exist_ok=True)
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

def test_upload_batch_atomic_immutable_and_duplicate(client):
    c=client;p=new(c);p,a=upload(c,p);h=a['sha256'];path=s.asset_path(a['assetId'])
    r=c.post('/v1/projects/'+p['projectId']+'/assets',files=[('files',('okay.png',png(),'image/png')),('files',('broken.png',b'not png','image/png'))]);assert r.status_code==422
    assert len(load(c,p)['assets'])==1
    p,b=upload(c,p,png((0,255,0,255)));assert a['sha256']!=b['sha256'];assert s.digest(path.read_bytes())==h
    r=c.post('/v1/projects/'+p['projectId']+'/duplicate',json={'expectedRevision':p['revision'],'name':'사본'});assert r.status_code==201;assert r.json()['projectId']!=p['projectId']

def test_conflict_and_empty_export(client):
    c=client;p=new(c);p2=edit(c,p,[{'type':'createClip','clip':{'name':'빈 동작'}}])
    r=c.patch('/v1/projects/'+p['projectId']+'/edits',json={'expectedRevision':p['revision'],'operations':[{'type':'updateCharacter','name':'덮어쓰기'}]});assert r.status_code==409
    assert load(c,p)['characterName']!='덮어쓰기'
    r=c.post('/v1/projects/'+p['projectId']+'/exports',json={'savedRevision':p2['revision'],'clipRevisionIds':[p2['clips'][0]['clipRevisionId']],'idempotencyKey':s.uid()});assert r.status_code==422;assert r.json()['code']=='EMPTY_TIMELINE'
    assert c.patch('/v1/projects/'+p['projectId']+'/edits',json={'expectedRevision':p2['revision'],'operations':[{'type':'arbitraryPatch','path':'../../'}]}).status_code==422

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
