"""Video integration regressions; synthetic media and fake remote transport, no billed calls."""
import io,json,subprocess,zipfile
from pathlib import Path
from types import SimpleNamespace
import pytest
from PIL import Image,ImageDraw
from fastapi.testclient import TestClient
from services.api import store as s,videos
from services.api.main import app
from services.worker.task import execute
from services.worker.main import publish,recover
from adapters.spritegen import video_provider as vp

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(s,'DATA',tmp_path/'data');s.init()
    with TestClient(app) as c:
        c.headers['X-Session-Token']=c.get('/v1/health').json()['sessionToken'];yield c

@pytest.fixture
def media(tmp_path):
    im=Image.new('RGB',(64,64),(255,0,255));ImageDraw.Draw(im).rectangle((24,12,40,53),fill=(140,70,30));im.save(tmp_path/'source.png')
    target=tmp_path/'fixture.mp4'
    subprocess.run(['ffmpeg','-v','error','-loop','1','-i',str(tmp_path/'source.png'),'-t','1','-r','8','-pix_fmt','yuv420p',str(target)],check=True)
    return target.read_bytes()

def new(c): return c.post('/v1/projects',json={'name':'영상 회귀 시험'}).json()
def load(c,p): return c.get('/v1/projects/'+p['projectId']).json()
def upload(c,p,media):
    r=c.post('/v1/projects/'+p['projectId']+'/videos',files={'file':('synthetic-fixture.mp4',media,'video/mp4')},data={'expectedRevision':p['revision']})
    assert r.status_code==201,r.text
    return r.json()['snapshot'],r.json()['video']
def queue(c,p,op='process_video',params=None,ids=None,idem=None):
    return c.post('/v1/projects/'+p['projectId']+'/jobs',json={'operation':op,'inputRevision':p['revision'],'assetIds':ids or [],'params':params or {},'idempotencyKey':idem or s.uid()})
def run(j):
    j=s.get_job(j['jobId']);out=s.job_directory(j['jobId'])/j['attemptId']/'staging'
    result=execute(j,out);publish(j,{'ok':True,'result':result});return s.get_job(j['jobId'])
def base(c,p):
    out=io.BytesIO();im=Image.new('RGBA',(64,128));ImageDraw.Draw(im).rectangle((24,24,40,117),fill=(100,70,40,255));im.save(out,format='PNG')
    r=c.post('/v1/projects/'+p['projectId']+'/assets',files={'files':('synthetic-still.png',out.getvalue(),'image/png')})
    assert r.status_code==201
    return load(c,p),r.json()['assets'][0]

def test_upload_limits_atomic_revision_and_project_scope(client,media):
    c=client;p=new(c)
    r=c.post('/v1/projects/'+p['projectId']+'/videos',files={'file':('bad.mp4',b'not a video','video/mp4')},data={'expectedRevision':p['revision']})
    assert r.status_code==422 and load(c,p).get('videos',[])==[]
    p,v=upload(c,p,media)
    assert c.get(v['url']).content==media
    stale=c.post('/v1/projects/'+p['projectId']+'/videos',files={'file':('f.mp4',media)},data={'expectedRevision':1})
    assert stale.status_code==409 and len(load(c,p)['videos'])==1
    other=new(c);r=queue(c,other,params={'videoId':v['videoId']})
    assert r.status_code==404
    assert queue(c,p,params={'videoId':v['videoId'],'loopMode':'manual','startFrame':0,'endFrame':999}).status_code==422
    assert queue(c,p,'generate_video',{'durationSeconds':20}).status_code==422
    assert queue(c,p,params={'videoId':v['videoId'],'finishMode':'invalid'}).status_code==422


def test_spill_reference_is_project_scoped_and_only_for_processing(client,media):
    c=client;p,a=base(c,new(c));p,v=upload(c,p,media)
    other,foreign=base(c,new(c))
    for ref in (foreign['assetId'],'missing'):
        assert queue(c,p,params={'videoId':v['videoId'],'spillReferenceAssetId':ref}).status_code==404
    assert queue(c,p,params={'videoId':v['videoId'],'spillReferenceAssetId':23}).status_code==422
    assert queue(c,p,'generate_video',{'spillReferenceAssetId':a['assetId']},[a['assetId']]).status_code==422
    assert c.get('/v1/projects/'+p['projectId']+'/jobs').json()['jobs']==[]


def test_imported_spill_reference_survives_rewind_and_portable_restore(client,media,monkeypatch):
    import sprite_gen.gen.xai as xai
    monkeypatch.setattr(xai,'http_json',lambda *_:pytest.fail('Spill repair must stay local'))
    c=client;p,a=base(c,new(c));p,v=upload(c,p,media)
    request={'videoId':v['videoId'],'spillReferenceAssetId':a['assetId'],'loopMode':'full','maxFrames':4,'bodyHeight':32,'cellWidth':64,'cellHeight':64}
    response=queue(c,p,params=request);assert response.status_code==202,response.text
    job=s.get_job(response.json()['jobId']);out=s.job_directory(job['jobId'])/job['attemptId']/'staging'
    result=execute(job,out)
    assert result['processing']['spill']['mode']=='full'
    assert result['processing']['spillReferenceAssetId']==a['assetId']
    assert 'reference' not in result['processing']['spill']
    r=c.post('/v1/projects/'+p['projectId']+'/restore-revision',json={'expectedRevision':p['revision'],'targetRevision':1});assert r.status_code==200
    publish(job,{'ok':True,'result':result});p=load(c,p);s.validate_snapshot(p)
    assert any(x['assetId']==a['assetId'] for x in p['assets'])
    keyed=[x for x in p['assets'] if x['provenance'].get('processing')=='chroma-key']
    assert len(keyed)==4 and all(x['provenance']['spillReferenceAssetId']==a['assetId'] for x in keyed)
    invalid=json.loads(s.dumps(p));invalid['assets']=[x for x in invalid['assets'] if x['assetId']!=a['assetId']]
    with pytest.raises(s.AppError):s.validate_snapshot(invalid)
    backup=run(c.post('/v1/projects/'+p['projectId']+'/backup',json={'savedRevision':p['revision']}).json())
    archive=c.get(backup['artifacts'][0]['url']).content
    restored=run(c.post('/v1/projects/restore',files={'backupZip':('ref-backup.zip',archive,'application/zip')},data={'idempotencyKey':'spill-ref-restore'}).json())
    copy=c.get('/v1/projects/'+restored['result']['projectId']).json();s.validate_snapshot(copy)
    original=next(x for x in copy['assets'] if x['originalFilename']=='synthetic-still.png')
    assert original['assetId']!=a['assetId']
    assert all(x['provenance']['spillReferenceAssetId']==original['assetId'] for x in copy['assets'] if x['provenance'].get('processing')=='chroma-key')



def test_jobless_restore_keeps_shared_work_and_rehomes_resources(client,media):
    p,v=upload(client,new(client),media)
    backup=run(client.post('/v1/projects/'+p['projectId']+'/backup',json={'savedRevision':p['revision']}).json())
    archive=client.get(backup['artifacts'][0]['url']).content
    response=client.post('/v1/projects/restore',files={'backupZip':('synthetic-backup.zip',archive,'application/zip')},data={'idempotencyKey':'folder-restore'})
    assert response.status_code==202,response.text
    job=s.get_job(response.json()['jobId'])
    assert not job['projectId']
    assert s.job_directory(job['jobId'])==s.DATA/'jobs'/job['jobId']
    assert s.artifact_directory(job['jobId'])==s.DATA/'artifacts'/job['jobId']
    restored=run(job);assert restored['status']=='succeeded'
    copy=client.get('/v1/projects/'+restored['result']['projectId']).json()
    restored_path=videos.path_for(copy['videos'][0]['videoId'])
    assert restored_path.is_relative_to(s.project_folder(copy['projectId'])/'videos')
    assert restored_path.read_bytes()==videos.path_for(v['videoId']).read_bytes()==media
    assert copy['projectId']!=p['projectId']


def test_real_local_processing_candidates_timing_and_backup(client,media,monkeypatch):
    import sprite_gen.gen.xai as xai
    monkeypatch.setattr(xai,'http_json',lambda *_:pytest.fail('No remote calls in video processing'))
    c=client;p,v=upload(c,new(c),media);before=p['revision']
    request={'videoId':v['videoId'],'loopMode':'manual','startFrame':1,'endFrame':7,'maxFrames':4,'bodyHeight':32,'cellWidth':64,'cellHeight':64,'key':'magenta'}
    r=queue(c,p,params=request,idem='local-video');assert r.status_code==202,r.text
    # A duplicate submission uses the existing job even after its input revision becomes stale.
    j=run(r.json());assert j['status']=='needs_review'
    assert queue(c,p,params=request,idem='local-video').json()['jobId']==j['jobId']
    p=load(c,p);assert p['revision']==before+1
    assert len(p['videos'])==1 and len(p['frames'])==4 and len(p['clips'])==1
    clip=p['clips'][0];assert sum(o['durationMs'] for o in clip['occurrences'])==750
    assert all(f['review']=='pending' and f['sourceVideoId']==v['videoId'] for f in p['frames'])
    assert all(a['approval']=='pending' for a in p['alignments'].values())
    assert all(o['timingMode']=='explicit' for o in clip['occurrences'])
    assert j['result']['processing']['finish']['mode']=='gif'
    by_asset={a['assetId']:a for a in p['assets']}
    for frame in p['frames']:
        candidate=by_asset[frame['imageAssetId']]
        assert candidate['provenance']['processing']=='video-finish'
        parent=by_asset[candidate['provenance']['parentAssetId']]
        assert parent['provenance']['processing']=='video-normalization'
        assert candidate['alphaStats']['partial']==0
        assert candidate['provenance']['finish']['paletteSamplingScale']==3
    s.validate_snapshot(p)
    baked=run(queue(c,p,'bake',{'clipIds':[clip['clipId']]}).json())
    runtime=baked['result']['manifest']
    assert runtime['sourceVideos'][0]['videoId']==v['videoId']
    assert all(f['sourceVideoId']==v['videoId'] for f in runtime['frameSources'])
    b=run(c.post('/v1/projects/'+p['projectId']+'/backup',json={'savedRevision':p['revision']}).json())
    archive=c.get(b['artifacts'][0]['url']).content
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        payload=json.loads(z.read('project.json'));assert payload['videos'][0]['sha256']==v['sha256']
        assert z.read(payload['videos'][0]['file'])==media
    restored=run(c.post('/v1/projects/restore',files={'backupZip':('backup.zip',archive,'application/zip')},data={'idempotencyKey':'video-restore'}).json())
    q=c.get('/v1/projects/'+restored['result']['projectId']).json();s.validate_snapshot(q)
    nv=q['videos'][0];assert nv['videoId']!=v['videoId'] and c.get(nv['url']).content==media
    assert all(f['sourceVideoId']==nv['videoId'] for f in q['frames'])
    assert q['clips'][0]['sourceVideoId']==nv['videoId']
    for asset in q['assets']:
        assert asset['provenance']['sourceVideoId']==nv['videoId']
        with s.connect() as db:
            stored=json.loads(db.execute('SELECT metadata FROM assets WHERE id=?',(asset['assetId'],)).fetchone()[0])
        assert stored['provenance']==asset['provenance']


def test_video_failure_keeps_received_mp4_and_resume_does_not_auth(client,media,monkeypatch):
    from services.worker import video_task
    from adapters.spritegen import video_processing
    c=client;p,a=base(c,new(c));r=queue(c,p,'generate_video',{},[a['assetId']]);assert r.status_code==202
    j=s.get_job(r.json()['jobId']);out=s.job_directory(j['jobId'])/j['attemptId']/'staging'
    local=out/'generation'/'original.mp4';s.atomic_bytes(local,media)
    receipt={'providerId':'grok-video','model':vp.MODELS[0],'requestId':'fake-request','sha256':s.digest(media)}
    checkpoint=s.job_directory(j['jobId'])/'video-checkpoint.json'
    s.atomic_bytes(checkpoint,s.dumps({'requestHash':j['requestHash'],'phase':'downloaded','localPath':str(local),'receipt':receipt,'postCount':1,'requestId':'fake-request'}).encode())
    monkeypatch.setattr(video_task,'generate',lambda *_:pytest.fail('Downloaded video must not regenerate'))
    def broken(*a,**kw): raise s.AppError('TEST_LOCAL_FAIL','합성 후처리 실패')
    monkeypatch.setattr(video_processing,'process_clip',broken)
    with pytest.raises(s.AppError):
        execute(j,out)
    p=load(c,p);assert len(p['videos'])==1
    assert c.get(p['videos'][0]['url']).content==media
    assert vp.checkpoint_state(j)['resumable']
    # Resume reads the already registered MP4 despite unavailable login.
    monkeypatch.setattr(vp,'login_credential',lambda:pytest.fail('Local resume must not require login'))
    with pytest.raises(s.AppError): execute(j,out)
    assert len(load(c,p)['videos'])==1


def test_cycle_matching_uses_snapshot_timing_and_preserves_interpolation_lineage(client,media,monkeypatch):
    from adapters.spritegen import video_processing
    # This deterministic stand-in only tests integration; real RIFE is tested separately.
    class Interpolator:
        def __call__(self,a,b,t):return Image.blend(a,b,t)
        def describe(self):return {'kind':'synthetic-test-interpolator'}
    monkeypatch.setattr(video_processing,'rife_interpolator',Interpolator)
    c=client;p,v=upload(c,new(c),media)
    params={'videoId':v['videoId'],'loopMode':'manual','startFrame':0,'endFrame':8,'maxFrames':5,'bodyHeight':32,'cellWidth':64,'cellHeight':64,'repairMode':'off'}
    initial=run(queue(c,p,params=params).json());p=load(c,p)
    clip=p['clips'][0];assert len(clip['occurrences'])==5
    changed={**params,'maxFrames':8,'matchClipId':clip['clipId']}
    result=queue(c,p,params=changed);assert result.status_code==202,result.text
    job=run(result.json());p=load(c,p)
    matched=next(cl for cl in p['clips'] if cl['clipId']==job['result']['clipId'])
    assert len(matched['occurrences'])==5
    assert sum(o['durationMs'] for o in matched['occurrences'])==sum(o['durationMs'] for o in clip['occurrences'])
    frames=[f for f in p['frames'] if f['frameVersionId'] in job['result']['frameVersionIds']]
    assert any(f['interpolated'] for f in frames)
    assets={a['assetId']:a for a in p['assets']}
    for frame in frames:
        assert assets[frame['rawAssetId']]['provenance']['interpolated'] is False
        if frame['interpolated']:
            assert frame['interpolation']['method']=='rife-cycle-align'
            assert assets[frame['imageAssetId']]['provenance']['interpolation']==frame['interpolation']
    alignment=job['result']['processing']['selection']['cycleAlignment']
    assert alignment['matchClipRevisionId']==clip['clipRevisionId']
    assert queue(c,p,params={**params,'matchClipId':'missing'}).status_code==404
    assert queue(c,p,params={**params,'matchClipId':clip['clipId'],'loopMode':'full'}).status_code==422
    baked=run(queue(c,p,'bake',{'clipIds':[matched['clipId']]}).json())
    assert any(f.get('interpolated') for f in baked['result']['manifest']['frameSources'])


def test_submission_checkpoint_resume_and_unknown_guard(client,media,monkeypatch,tmp_path):
    from sprite_gen.gen.xai import Credential
    credential=Credential('not-a-real-token','grok-login')
    p,a=base(client,new(client));source=s.asset_path(a['assetId']);checkpoint=s.DATA/'probe'/'video.json';work=s.DATA/'probe'/'staging'
    calls=[]
    def interrupted(method,url,token,body):
        calls.append(method)
        if method=='POST': return 200,{'request_id':'saved-request'}
        raise SystemExit('test interrupted poll')
    with pytest.raises(vp.ProviderError): vp.generate(source,work,vp.validate_params({},generation=True),checkpoint,'hash',credential=credential,call=interrupted,sleep=lambda _:None)
    assert calls==['POST','GET'] and vp.read_checkpoint(checkpoint)['requestId']=='saved-request'
    def resume(method,url,token,body):
        assert method=='GET';calls.append(method)
        return 200,{'status':'done','model':vp.MODELS[0],'video':{'url':'https://example.invalid/fixture.mp4','duration':1}}
    result=vp.generate(source,work,vp.validate_params({},generation=True),checkpoint,'hash',credential=credential,call=resume,download=lambda *_:media,sleep=lambda _:None)
    assert calls==['POST','GET','GET'] and Path(result['path']).read_bytes()==media
    unknown=s.DATA/'unknown.json';s.atomic_bytes(unknown,s.dumps({'requestHash':'hash','phase':'submitting','postCount':1}).encode())
    with pytest.raises(vp.ProviderError) as e: vp.generate(source,work, vp.validate_params({},generation=True),unknown,'hash',credential=credential,call=lambda *_:pytest.fail('No replay'))
    assert e.value.outcome_unknown


def test_recovery_and_retry_never_repeat_unknown_post(client,media):
    c=client;p,a=base(c,new(c));r=queue(c,p,'generate_video',{},[a['assetId']]);j=s.get_job(r.json()['jobId'])
    with s.transaction() as db:
        j.update(status='running',externalStarted=True);s.write_job(db,j)
    checkpoint=s.job_directory(j['jobId'])/'video-checkpoint.json'
    s.atomic_bytes(checkpoint,s.dumps({'requestHash':j['requestHash'],'phase':'submitting','postCount':1}).encode())
    recover();assert s.get_job(j['jobId'])['status']=='provider_outcome_unknown'
    assert c.post('/v1/jobs/'+j['jobId']+'/retry',json={'idempotencyKey':'unknown'}).status_code==409
    with s.transaction() as db:
        j=s.get_job(j['jobId'],db);j['status']='running';s.write_job(db,j)
    s.atomic_bytes(checkpoint,s.dumps({'requestHash':j['requestHash'],'phase':'submitted','postCount':1,'requestId':'known'}).encode())
    recover();j=s.get_job(j['jobId']);assert j['status']=='interrupted' and j['resumable']
    assert c.post('/v1/jobs/'+j['jobId']+'/retry',json={'idempotencyKey':'known'}).status_code==200


def test_generated_video_full_pipeline_preserves_prepared_reference(client,media,monkeypatch):
    from sprite_gen.gen.xai import Credential
    import sprite_gen.gen.xai as xai
    from sprite_gen.gen import video as engine_video
    monkeypatch.setattr(vp,'login_credential',lambda:Credential('synthetic-token','grok-login'))
    calls=[]
    def transport(method,url,token,body=None):
        calls.append(method)
        if method=='POST': return 200,{'request_id':'synthetic-full-pipeline'}
        return 200,{'status':'done','model':vp.MODELS[0],'video':{'url':'https://example.invalid/video.mp4','duration':1}}
    monkeypatch.setattr(xai,'http_json',transport)
    monkeypatch.setattr(engine_video,'http_download',lambda *_:media)
    p,a=base(client,new(client));r=queue(client,p,'generate_video',{'loopMode':'full','bodyHeight':32,'cellWidth':64,'cellHeight':64},[a['assetId']])
    assert r.status_code==202
    j=run(r.json());assert j['status']=='needs_review' and calls==['POST','GET']
    p=load(client,p);v=p['videos'][0];reference=next(a for a in p['assets'] if a['assetId']==v['provenance']['referenceAssetId'])
    assert reference['provenance']['kind']=='video-input' and s.asset_path(reference['assetId']).is_file()
    assert 'path' not in v['provenance']['preparation']
    assert p['clips'][0]['loop'] is False
    # Publication moved staging; a local reprocess uses the immutable reference asset.
    request={'videoId':v['videoId'],'loopMode':'manual','startFrame':0,'endFrame':8,'bodyHeight':32,'cellWidth':64,'cellHeight':64}
    j2=run(queue(client,p,params=request).json());assert j2['status']=='needs_review' and calls==['POST','GET']


def test_publication_after_revision_restore_relinks_video_and_backup(client,media):
    c=client;initial=new(c);p,v=upload(c,initial,media)
    queued=queue(c,p,params={'videoId':v['videoId'],'loopMode':'manual','startFrame':0,'endFrame':8,'bodyHeight':32,'cellWidth':64,'cellHeight':64}).json()
    job=s.get_job(queued['jobId']);out=s.job_directory(job['jobId'])/job['attemptId']/'staging'
    result=execute(job,out)
    response=c.post('/v1/projects/'+p['projectId']+'/restore-revision',json={'expectedRevision':p['revision'],'targetRevision':1})
    assert response.status_code==200 and response.json()['snapshot'].get('videos',[])==[]
    publish(job,{'ok':True,'result':result})
    after=load(c,p);s.validate_snapshot(after)
    assert after['videos'][0]['videoId']==v['videoId'] and after['name']==initial['name']
    b=run(c.post('/v1/projects/'+p['projectId']+'/backup',json={'savedRevision':after['revision']}).json())
    archive=c.get(b['artifacts'][0]['url']).content
    restored=run(c.post('/v1/projects/restore',files={'backupZip':('restored.zip',archive,'application/zip')},data={'idempotencyKey':'rewound-video-restore'}).json())
    copy=c.get('/v1/projects/'+restored['result']['projectId']).json();s.validate_snapshot(copy)
    assert c.get(copy['videos'][0]['url']).content==media


def test_preserved_video_resume_after_rewind_never_calls_auth(client,media,monkeypatch):
    from services.worker import video_task
    from adapters.spritegen import video_processing
    c=client;p,a=base(c,new(c));queued=queue(c,p,'generate_video',{},[a['assetId']]).json();job=s.get_job(queued['jobId'])
    out=s.job_directory(job['jobId'])/job['attemptId']/'staging';path=out/'generation'/'original.mp4';s.atomic_bytes(path,media)
    receipt={'model':vp.MODELS[0],'requestId':'relink','sha256':s.digest(media)}
    checkpoint=s.job_directory(job['jobId'])/'video-checkpoint.json'
    s.atomic_bytes(checkpoint,s.dumps({'phase':'downloaded','requestHash':job['requestHash'],'localPath':str(path),'receipt':receipt,'requestId':'relink','postCount':1}).encode())
    monkeypatch.setattr(video_task,'generate',lambda *_:pytest.fail('No generation/auth during preserved recovery'))
    def broken(*a,**kw):raise s.AppError('LOCAL_TEST_FAILURE','합성 후처리 실패')
    monkeypatch.setattr(video_processing,'process_clip',broken)
    with pytest.raises(s.AppError):execute(job,out)
    p=load(c,p);vid=p['videos'][0]['videoId']
    r=c.post('/v1/projects/'+p['projectId']+'/restore-revision',json={'expectedRevision':p['revision'],'targetRevision':1});assert r.status_code==200
    with pytest.raises(s.AppError):execute(job,out)
    q=load(c,p);s.validate_snapshot(q)
    assert q['videos'][0]['videoId']==vid and any(x['assetId']==a['assetId'] for x in q['assets'])



@pytest.mark.parametrize('phase', ['submitted', 'downloaded'])
@pytest.mark.parametrize('stored_form', ['legacy-absolute', 'relative'])
def test_video_checkpoint_recovery_in_external_project_folder(client,media,monkeypatch,tmp_path,phase,stored_form):
    """Synthetic MP4 copied from legacy storage; only real local extraction runs."""
    import sprite_gen.gen.xai as xai
    parent=tmp_path/'user projects';parent.mkdir()
    response=client.post('/v1/projects',json={'name':'외부 영상 프로젝트','parentDirectory':str(parent)})
    assert response.status_code==201,response.text
    p,a=base(client,response.json())
    params={'loopMode':'full','maxFrames':4,'bodyHeight':32,'cellWidth':64,'cellHeight':64}
    queued=queue(client,p,'generate_video',params,[a['assetId']])
    assert queued.status_code==202,queued.text
    j=s.get_job(queued.json()['jobId']);root=s.project_folder(p['projectId'])
    assert root.is_relative_to(parent) and not root.is_relative_to(s.DATA)
    out=s.job_directory(j['jobId'])/j['attemptId']/'staging'
    video_relative=Path('jobs')/j['jobId']/j['attemptId']/'staging'/'generation'/'original.mp4'
    still_relative=video_relative.with_name('input-canvas.png')
    still=s.asset_path(a['assetId']).read_bytes()
    for relative,data in [(video_relative,media),(still_relative,still)]:
        s.atomic_bytes(s.DATA/relative,data)
        s.atomic_bytes(root/relative,data)
    def stored(relative):return str(s.DATA/relative) if stored_form=='legacy-absolute' else relative.as_posix()
    checkpoint=s.job_directory(j['jobId'])/'video-checkpoint.json'
    receipt={'model':vp.MODELS[0],'requestId':'synthetic-relocation','sha256':s.digest(media)}
    preparation={'path':stored(still_relative),'sourcePath':str(s.asset_path(a['assetId'])),'key':'magenta'}
    s.atomic_bytes(checkpoint,s.dumps({'requestHash':j['requestHash'],'phase':phase,'requestId':'synthetic-relocation',
        'postCount':1,'localPath':stored(video_relative),'receipt':receipt,'preparation':preparation}).encode())
    monkeypatch.setattr(vp,'login_credential',lambda:pytest.fail('Local checkpoint resume must not authenticate'))
    monkeypatch.setattr(xai,'http_json',lambda *a,**k:pytest.fail('Local checkpoint resume must not request AI'))
    done=run(j)
    assert done['status']=='needs_review',done
    project=load(client,p)
    assert len(project['videos'])==1 and len(project['frames'])==4
    assert videos.path_for(project['videos'][0]['videoId']).is_relative_to(root/'videos')
    assert client.get(project['videos'][0]['url']).content==media
    assert all(s.asset_path(asset['assetId']).is_relative_to(root/'assets') for asset in project['assets'])
    assert vp.read_checkpoint(checkpoint)['phase']=='preserved'
    assert (s.DATA/video_relative).read_bytes()==media and (s.DATA/still_relative).read_bytes()==still
    assert s.artifact_directory(j['jobId'])==root/'outputs'/j['jobId']
    for artifact in done['artifacts']:
        response=client.get(artifact['url'])
        assert response.status_code==200,response.text
        assert s.digest(response.content)==artifact['sha256']


def test_completed_mp4_crash_window_recovers_without_credentials(client,media,monkeypatch):
    p,a=base(client,new(client));work=s.DATA/'crash-probe'/'attempt';local=work/'original.mp4';s.atomic_bytes(local,media)
    checkpoint=work.parent/'checkpoint.json'
    s.atomic_bytes(checkpoint,s.dumps({'phase':'submitted','requestHash':'crash','requestId':'crash-request','postCount':1,'localPath':str(local)}).encode())
    monkeypatch.setattr(vp,'login_credential',lambda:pytest.fail('Completed MP4 must recover without login'))
    result=vp.generate(s.asset_path(a['assetId']),work.parent/'new-attempt',vp.validate_params({},generation=True),checkpoint,'crash',call=lambda *_:pytest.fail('No remote lookup needed'))
    assert result['path']==local and result['receipt']['downloadRecovered']
    assert vp.read_checkpoint(checkpoint)['phase']=='downloaded'


def test_fast_explicit_vfr_range_keeps_timing_and_valid_default_fps(client,media,monkeypatch,tmp_path):
    from adapters.spritegen import video_processing
    from alignment.pipeline import _clip_gates
    c=client;p,v=upload(c,new(c),media)
    image=Image.new('RGBA',(64,64));ImageDraw.Draw(image).rectangle((25,15,40,55),fill=(170,80,30,255));frame=tmp_path/'vfr-keyed.png';image.save(frame)
    result={'source':{'width':64,'height':64,'fps':24,'frameCount':4,'durationMs':40},'selection':{'loop':True},'standingHeight':40,'anchor':{'x':32,'y':55},'files':[],
            'frames':[{'rawPath':str(frame),'keyedPath':str(frame),'sourceFrameIndex':i,'sourceTimeMs':i*10,'durationMs':10} for i in range(4)]}
    monkeypatch.setattr(video_processing,'process_clip',lambda *_a,**_kw:result)
    j=run(queue(c,p,params={'videoId':v['videoId'],'loopMode':'full','bodyHeight':32,'cellWidth':64,'cellHeight':64}).json())
    q=load(c,p);clip=q['clips'][0]
    assert clip['defaultFps']==60 and sum(o['durationMs'] for o in clip['occurrences'])==40
    assert 'UNSUPPORTED_TIMING' not in {e['code'] for e in _clip_gates(q,clip)}


def test_dependency_reattach_follows_video_derived_base_images(client,media):
    c=client;p,a=base(c,new(c));p,v1=upload(c,p,media)
    image=Image.open(s.asset_path(a['assetId']));buf=io.BytesIO();image.save(buf,format='PNG')
    with s.transaction() as db:
        derived=s.register_asset(buf.getvalue(),'video-derived-base.png','derived',{'kind':'video-frame','sourceVideoId':v1['videoId'],'parentAssetId':a['assetId']},c=db)
        v2=videos.register(media,'second-video.mp4',{'kind':'real-provider-video','baseAssetId':derived['assetId']},c=db)
    empty=new(c)
    with s.transaction() as db:
        videos.attach_dependencies(empty,v2,[],db)
    s.validate_snapshot(empty)
    assert {v['videoId'] for v in empty['videos']}=={v1['videoId'],v2['videoId']}
    assert {v['assetId'] for v in empty['assets']}=={a['assetId'],derived['assetId']}
