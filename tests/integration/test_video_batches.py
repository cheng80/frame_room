"""Batch acceptance must be atomic and replayable before any paid worker call."""
import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from services.api import store as s
from services.api.main import app


@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setattr(s,'DATA',tmp_path/'data');s.init()
    with TestClient(app) as client:
        client.headers['X-Session-Token']=client.get('/v1/health').json()['sessionToken']
        p=client.post('/v1/projects',json={'name':'묶음 접수 검증'}).json()
        image=io.BytesIO();Image.new('RGBA',(16,32),(70,90,110,255)).save(image,format='PNG')
        a=client.post('/v1/projects/'+p['projectId']+'/assets',files={'files':('fixture.png',image.getvalue(),'image/png')}).json()['assets'][0]
        p=client.get('/v1/projects/'+p['projectId']).json()
        yield client,p,a


def test_video_batch_acceptance_and_replay_survive_revision_change(setup):
    c,p,a=setup;url='/v1/projects/'+p['projectId']+'/video-batches'
    body={'inputRevision':p['revision'],'idempotencyKey':'one-plan','items':[
        {'assetId':a['assetId'],'params':{'state':'walk','direction':'side'}},
        {'assetId':a['assetId'],'params':{'state':'run','direction':'front'}},
    ]}
    result=c.post(url,json=body);assert result.status_code==202,result.text
    value=result.json();assert len(value['jobs'])==2
    assert [j['batchIndex'] for j in value['jobs']]==[0,1]
    assert all(j['batchId']==value['batchId'] and j['batchSize']==2 and j['status']=='queued' for j in value['jobs'])
    with s.transaction() as db:
        updated=s.get_project(p['projectId'],db);s.write_project(db,updated,'unrelated local edit')
    again=c.post(url,json=body);assert again.status_code==202
    assert [j['jobId'] for j in again.json()['jobs']]==[j['jobId'] for j in value['jobs']]
    body['items'].pop()
    assert c.post(url,json=body).status_code==409
    assert len(c.get('/v1/projects/'+p['projectId']+'/jobs').json()['jobs'])==2


def test_video_batch_rejects_whole_plan_without_partial_jobs(setup):
    c,p,a=setup;url='/v1/projects/'+p['projectId']+'/video-batches'
    body={'inputRevision':p['revision'],'idempotencyKey':'invalid-plan','items':[
        {'assetId':a['assetId'],'params':{}}, {'assetId':'foreign-or-missing','params':{}},
    ]}
    assert c.post(url,json=body).status_code==404
    assert c.get('/v1/projects/'+p['projectId']+'/jobs').json()['jobs']==[]
    body['items'][1]['assetId']=a['assetId'];body['items'][1]['params']={'model':'invalid-model'}
    assert c.post(url,json=body).status_code==422
    assert c.get('/v1/projects/'+p['projectId']+'/jobs').json()['jobs']==[]
    body['items']=[{'assetId':a['assetId'],'params':{}}]*17
    assert c.post(url,json=body).status_code==422
    body['items']=[]
    assert c.post(url,json=body).status_code==422


@pytest.mark.parametrize('params',[{},{'frameJudge':'auto'},{'frameSelection':'vision','frameJudge':'auto'}])
def test_job_stored_before_the_fresh_default_replays_by_its_raw_request(setup,params):
    """A job saved before frameSelection defaulted hashed the raw request; the same raw replay returns it unchanged."""
    c,p,a=setup;url='/v1/projects/'+p['projectId']+'/jobs'
    raw={'operation':'generate_video','inputRevision':p['revision'],'assetIds':[a['assetId']],'params':params,'idempotencyKey':'old'}
    jid=c.post(url,json=raw).json()['jobId']
    original={k:v for k,v in raw.items() if k!='idempotencyKey'}
    with s.transaction() as db:  # stand-in for a record written by the previous code (test database only)
        job=s.get_job(jid,db);job.update(request=original,requestHash=s.digest(s.dumps(original).encode()));s.write_job(db,job)
        db.execute('UPDATE jobs SET request_hash=? WHERE id=?',(job['requestHash'],jid))
    replay=c.post(url,json=raw);assert replay.status_code==202,replay.text
    assert replay.json()['jobId']==jid and s.get_job(jid)['request']==original
    assert c.post(url,json={**raw,'params':{**params,'state':'run'}}).status_code==409
    assert len(c.get('/v1/projects/'+p['projectId']+'/jobs').json()['jobs'])==1


def test_new_default_and_explicit_uniform_jobs_replay_stably(setup):
    c,p,a=setup;url='/v1/projects/'+p['projectId']+'/jobs'
    base={'operation':'generate_video','inputRevision':p['revision'],'assetIds':[a['assetId']]}
    fresh={**base,'params':{},'idempotencyKey':'fresh'};uniform={**base,'params':{'frameSelection':'uniform'},'idempotencyKey':'uniform'}
    first,second=c.post(url,json=fresh).json(),c.post(url,json=uniform).json()
    assert s.get_job(first['jobId'])['request']['params']=={'frameSelection':'vision','frameJudge':'rules'}
    assert s.get_job(second['jobId'])['request']['params']=={'frameSelection':'uniform'}
    for body,job in ((fresh,first),(uniform,second)):
        again=c.post(url,json=body);assert again.status_code==202 and again.json()['jobId']==job['jobId']
    assert c.post(url,json={**fresh,'params':{'frameSelection':'uniform'}}).status_code==409  # changed content, same key
    assert c.post(url,json={**uniform,'params':{}}).status_code==409
    assert len(c.get('/v1/projects/'+p['projectId']+'/jobs').json()['jobs'])==2
