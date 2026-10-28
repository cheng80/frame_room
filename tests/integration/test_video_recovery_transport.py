"""M1: real urllib traffic to loopback, synthetic MP4, no authentication or paid calls."""
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from sprite_gen.gen.xai import Credential
from adapters.spritegen import video_provider as vp
from services.api import store as s, project_folders
from services.worker import task, main as worker
from test_video_jobs import client, media, base, new, queue, load, upload


@pytest.fixture
def remote(monkeypatch, media):
    state=SimpleNamespace(posts=0,polls=[],downloads=0,actions=[],post='accepted',download='valid',download_actions=[],request_id='same-id',model=vp.MODELS[0])
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_): pass
        def reply(self,status,body):
            self.send_response(status);self.send_header('Content-Length',str(len(body)));self.end_headers()
            try:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass
        def slow(self,body,*,headers=False,status=200):
            if headers:body=b'HTTP/1.1 200 OK\r\nContent-Length: 1000\r\n\r\n'+body
            else:
                self.send_response(status);self.send_header('Content-Length',str(len(body)));self.end_headers()
            for offset in range(0,len(body),5 if headers else 100):
                try:self.wfile.write(body[offset:offset+(5 if headers else 100)]);self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError):break
                time.sleep(.03)
        def fault(self,action):
            if action in ('slowbody','slowheaders'):
                self.slow(b'x'*1000,headers=action=='slowheaders');return True
            if action=='disconnect':
                self.connection.shutdown(socket.SHUT_RDWR);self.connection.close();return True
            if action in ('truncated','timeout'):
                self.send_response(200);self.send_header('Content-Length','1000');self.end_headers()
                if action=='timeout':time.sleep(.15)
                else:self.wfile.write(b'{"status":');self.wfile.flush();self.close_connection=True
                return True
            return False
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length',0)));state.posts+=1
            if self.fault(state.post):return
            if isinstance(state.post,int):return self.reply(state.post,b'{"error":"denied"}')
            if state.post=='nonjson':return self.reply(200,b'invalid-json')
            self.reply(202,json.dumps({'request_id':state.request_id}).encode())
        def do_GET(self):
            if self.path.startswith('/clip'):
                state.downloads+=1
                if state.download_actions:state.download=state.download_actions.pop(0)
                if isinstance(state.download,int):return self.reply(state.download,b'error')
                if state.download in ('auth','auth-rejected','auth-slow'):
                    if not self.headers.get('Authorization'):
                        if state.download=='auth-slow':time.sleep(.07)
                        return self.reply(403,b'authentication needed')
                    if state.download=='auth-rejected':return self.reply(401,b'denied')
                    if state.download=='auth-slow':return self.slow(media)
                    return self.reply(200,media)
                if self.fault(state.download):return
                if state.download=='error':return self.reply(503,b'no')
                data=media if state.download=='valid' else b'\x00\x00\x00\x18ftyp'+b'invalid-container'
                return self.reply(200,data)
            state.polls.append(self.path)
            action=state.actions.pop(0) if state.actions else 'done'
            if action=='auth-slow-body':return self.slow(b'x'*1000,status=401)
            if self.fault(action):return
            if action=='nonjson':return self.reply(200,b'not-json')
            if isinstance(action,int):return self.reply(action,b'{"error":"safe"}')
            video={} if action=='missing' else {'url':state.url+'/clip?signature=DO-NOT-PUBLISH','duration':1}
            self.reply(200,json.dumps({'status':'done','model':state.model,'video':video}).encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    state.url='http://127.0.0.1:'+str(server.server_port)
    monkeypatch.setattr(__import__('sprite_gen.gen.video',fromlist=['API_BASE']),'API_BASE',state.url)
    monkeypatch.setattr(vp,'HTTP_TIMEOUT_SECONDS',.05)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield state
    finally:server.shutdown();server.server_close();thread.join(timeout=2)


def generate(client,remote,**kwargs):
    if not hasattr(remote,'source'):
        _,a=base(client,new(client));remote.source=s.asset_path(a['assetId'])
    remote.checkpoint=s.DATA/'transport'/'checkpoint.json';remote.work=s.DATA/'transport'/'generation'
    return vp.generate(remote.source,remote.work,vp.validate_params({},generation=True),remote.checkpoint,'transport-hash',
                       credential=Credential('SYNTHETIC-TOKEN-DO-NOT-PUBLISH','grok-login'),sleep=lambda _:None,**kwargs)


@pytest.mark.parametrize('fault',[429,500,503,'disconnect','truncated','nonjson','timeout'])
def test_real_transport_get_retry_keeps_id_and_redacts_receipt(client,remote,fault):
    remote.actions=[fault,'done']
    result=generate(client,remote)
    assert remote.posts==1 and remote.polls==['/videos/same-id']*2 and remote.downloads==1
    assert result['receipt']['postCount']==1 and result['receipt']['pollCount']==2
    assert result['receipt']['downloadCount']==1 and result['receipt']['sha256']==s.digest(result['path'].read_bytes())
    public=json.dumps(result['receipt'])
    assert 'SYNTHETIC-TOKEN' not in public and 'signature' not in public and remote.url not in public
    assert vp.read_checkpoint(remote.checkpoint)['phase']=='downloaded'


@pytest.mark.parametrize('fault',[401,403])
def test_auth_rejection_stops_without_fallback_and_manually_resumes_same_id(client,remote,fault):
    remote.actions=[fault]
    with pytest.raises(vp.ProviderError) as exc:generate(client,remote)
    assert exc.value.code=='GROK_AUTH_REJECTED' and remote.posts==1 and len(remote.polls)==1
    assert vp.read_checkpoint(remote.checkpoint)['stopReason']=='GROK_AUTH_REJECTED'
    generate(client,remote)
    assert remote.posts==1 and remote.polls==['/videos/same-id']*2


@pytest.mark.parametrize('fault',[429,403,503,'disconnect','truncated','nonjson','timeout'])
def test_real_transport_post_is_never_repeated_even_after_manual_retry(client,remote,fault):
    remote.post=fault
    with pytest.raises(vp.ProviderError):generate(client,remote)
    with pytest.raises(vp.ProviderError):generate(client,remote)
    assert remote.posts==1 and remote.polls==[] and not (remote.work/'original.mp4').exists()


@pytest.mark.parametrize('fault',['missing','error','truncated','timeout','invalid'])
def test_incomplete_download_is_never_published_and_same_id_can_resume(client,remote,fault):
    if fault=='missing':remote.actions=['missing']
    else:remote.download=fault
    with pytest.raises(vp.ProviderError):generate(client,remote)
    saved=vp.read_checkpoint(remote.checkpoint)
    assert saved['phase']=='submitted' and saved['requestId']=='same-id' and saved['stopReason']
    if fault=='invalid':assert remote.downloads==1
    assert not (remote.work/'original.mp4').exists() and not (remote.work/'original.mp4.part').exists()
    remote.download='valid';result=generate(client,remote)
    assert remote.posts==1 and result['path'].is_file()


def test_poll_retry_limit_and_total_deadline(client,remote):
    remote.actions=[503]*4
    with pytest.raises(vp.ProviderError) as exc:generate(client,remote)
    assert exc.value.code=='VIDEO_POLL_RETRY_LIMIT' and len(remote.polls)==4
    remote.actions=['timeout']*4
    started=time.monotonic()
    with pytest.raises(vp.ProviderError) as exc:generate(client,remote,timeout=.035)
    assert exc.value.code=='VIDEO_RECOVERY_TIMEOUT' and time.monotonic()-started<.5
    assert remote.posts==1 and len(remote.polls)==5


@pytest.mark.parametrize('legacy',[False,True])
def test_local_atomic_original_is_reused_before_authentication(client,remote,monkeypatch,legacy):
    result=generate(client,remote)
    saved=vp.read_checkpoint(remote.checkpoint);saved.pop('receipt');saved['phase']='submitted'
    if legacy:saved.pop('requestIdVerified')
    s.atomic_bytes(remote.checkpoint,s.dumps(saved).encode())
    monkeypatch.setattr(vp,'login_credential',lambda:pytest.fail('local resume must not authenticate'))
    recovered=vp.generate(remote.source,remote.work,vp.validate_params({},generation=True),remote.checkpoint,'transport-hash')
    assert recovered['receipt']['downloadRecovered'] and recovered['path']==result['path']
    assert remote.posts==1 and len(remote.polls)==1 and remote.downloads==1
    assert ('requestId' in recovered['receipt']) is not legacy
    assert vp.read_checkpoint(remote.checkpoint)['requestId']=='same-id'


@pytest.mark.parametrize('after_commit',[False,True])
@pytest.mark.parametrize('legacy_policy',[False,True])
def test_completed_video_save_retry_never_processes_or_duplicates(client,media,monkeypatch,after_commit,legacy_policy):
    p,v=upload(client,new(client),media)
    response=queue(client,p,params={'videoId':v['videoId'],'frameSelection':'uniform','loopMode':'full','maxFrames':4,'bodyHeight':32,'cellWidth':64,'cellHeight':64})
    j=s.get_job(response.json()['jobId']);out=s.job_directory(j['jobId'])/j['attemptId']/'staging'
    result=task.execute(j,out);result['publicationHashes']={name:s.digest((out/name).read_bytes()) for name in result['files']}
    payload={'ok':True,'result':result};s.atomic_bytes(out.parent/'result.json',s.dumps(payload).encode())
    original=(out.parent/'result.json').read_bytes()
    real_write=s.write_project;real_flush=project_folders.flush
    if after_commit:
        monkeypatch.setattr(project_folders,'flush',lambda *_a,**_k:(_ for _ in ()).throw(s.AppError('PROJECT_FOLDER_SYNC_FAILED','synthetic folder failure',503)))
    else:
        monkeypatch.setattr(s,'write_project',lambda *_a,**_k:(_ for _ in ()).throw(OSError('synthetic save failure')))
    with pytest.raises((s.AppError,OSError)):worker.publish(j,payload)
    if after_commit:
        assert worker.handle_folder_failure(j,s.AppError('PROJECT_FOLDER_SYNC_FAILED','synthetic folder failure',503))
        assert s.get_job(j['jobId'])['status']=='interrupted'
    monkeypatch.setattr(s,'write_project',real_write);monkeypatch.setattr(project_folders,'flush',real_flush)
    with s.transaction() as c:
        failed=s.get_job(j['jobId'],c);failed.update(status='interrupted',completedResult=True)
        if legacy_policy: failed.pop('processingPolicy',None)
        s.write_job(c,failed)
    retried=client.post('/v1/jobs/'+j['jobId']+'/retry',json={'idempotencyKey':'save-only'})
    assert retried.status_code==200,retried.text
    current=s.get_job(j['jobId'])
    monkeypatch.setattr(task,'execute',lambda *_:pytest.fail('completed save must not process again'))
    monkeypatch.setattr(vp,'generate',lambda *_a,**_k:pytest.fail('completed save must not generate or download'))
    if not after_commit:
        monkeypatch.setattr(__import__('sys'),'argv',['task',j['jobId'],current['attemptId']]);task.main()
        work=s.job_directory(j['jobId'])/current['attemptId'];worker.publish(current,json.loads((work/'result.json').read_text()))
    final=load(client,p);done=s.get_job(j['jobId'])
    assert done['status']=='needs_review' and done['published'] and len(final['clips'])==1
    clip=final['clips'][0];assert clip['occurrences']==result['clips'][0]['occurrences']
    assert final['frames']==result['frames'] and len(final['frames'])==4
    folder=s.project_folder(p['projectId']);portable=json.loads((folder/'project.json').read_text())
    assert portable['projectId']==final['projectId'] and portable['revision']==final['revision']
    import sqlite3
    with sqlite3.connect(folder/'project.sqlite3') as db:
        saved=json.loads(db.execute('SELECT snapshot FROM projects WHERE id=?',(p['projectId'],)).fetchone()[0])
    assert saved['clips']==final['clips'] and saved['frames']==final['frames']
    assert (out.parent/'result.json').read_bytes()==original
    repeated=client.post('/v1/jobs/'+j['jobId']+'/retry',json={'idempotencyKey':'save-only'})
    assert repeated.status_code==200 and len(load(client,p)['clips'])==1
    assert all((s.artifact_directory(j['jobId'])/done['attemptId']/a['name']).is_file() for a in done['artifacts'])


@pytest.mark.parametrize('stage',['poll-body','poll-headers','download','download-auth','submit'])
def test_trickle_responses_obey_absolute_budget(client,remote,monkeypatch,stage):
    monkeypatch.setattr(vp,'HTTP_TIMEOUT_SECONDS',1)
    if stage.startswith('poll'):remote.actions=['slowheaders' if stage.endswith('headers') else 'slowbody']
    elif stage=='submit':remote.post='slowheaders'
    else:remote.download='auth-slow' if stage=='download-auth' else 'slowbody'
    started=time.monotonic()
    with pytest.raises(vp.ProviderError):generate(client,remote,timeout=.12)
    assert time.monotonic()-started<.24
    assert remote.posts==1 and not (remote.work/'original.mp4').exists()
    if stage=='download-auth':assert vp.read_checkpoint(remote.checkpoint)['downloadCount']==2


def test_download_auth_attempt_counts_and_manual_resume(client,remote):
    remote.download='auth-rejected'
    with pytest.raises(vp.ProviderError) as exc:generate(client,remote)
    assert exc.value.code=='GROK_AUTH_REJECTED' and remote.downloads==2
    assert vp.read_checkpoint(remote.checkpoint)['downloadCount']==2
    remote.download='auth';result=generate(client,remote)
    assert result['receipt']['downloadCount']==4 and remote.posts==1


@pytest.mark.parametrize('request_id',[None,123,'../../secret?token=bad','https://invalid/?signature=bad'])
def test_unusable_request_id_is_unknown_and_never_replayed(client,remote,request_id):
    remote.request_id=request_id
    with pytest.raises(vp.ProviderError) as exc:generate(client,remote)
    assert exc.value.outcome_unknown
    with pytest.raises(vp.ProviderError):generate(client,remote)
    assert remote.posts==1 and not remote.polls
    assert vp.read_checkpoint(remote.checkpoint)['requestId'] is None


def test_untrusted_provider_model_never_enters_public_receipt(client,remote):
    remote.model='https://invalid/?signature=DO-NOT-PUBLISH'
    result=generate(client,remote)
    assert result['receipt']['model']==vp.MODELS[0] and result['receipt']['modelSource']=='request'
    assert 'signature' not in json.dumps(result['receipt'])


def test_auth_rejection_does_not_wait_for_or_retry_a_slow_error_body(client,remote):
    remote.actions=['auth-slow-body']
    started=time.monotonic()
    with pytest.raises(vp.ProviderError) as exc:generate(client,remote)
    assert exc.value.code=='GROK_AUTH_REJECTED' and len(remote.polls)==1
    assert time.monotonic()-started<.15 and remote.posts==1


@pytest.mark.parametrize('request_id',['SYNTHETIC-TOKEN-DO-NOT-PUBLISH','prefix-SYNTHETIC-TOKEN-DO-NOT-PUBLISH-suffix'])
def test_reflected_credential_is_not_saved_or_publicly_exposed(client,remote,request_id):
    remote.request_id=request_id
    with pytest.raises(vp.ProviderError) as exc:generate(client,remote)
    assert exc.value.outcome_unknown and remote.posts==1 and not remote.polls
    saved=vp.read_checkpoint(remote.checkpoint)
    assert 'SYNTHETIC-TOKEN' not in json.dumps(saved)
    assert 'SYNTHETIC-TOKEN' not in json.dumps(vp.recovery_receipt(saved))
    with pytest.raises(vp.ProviderError):generate(client,remote)
    assert remote.posts==1


def test_legacy_id_is_hidden_until_explicit_credential_validation(client,remote):
    generate(client,remote)
    saved=vp.read_checkpoint(remote.checkpoint);saved.pop('requestIdVerified');saved['phase']='submitted'
    saved['requestId']='SYNTHETIC-TOKEN-DO-NOT-PUBLISH';saved['receipt']['requestId']=saved['requestId']
    (remote.work/'original.mp4').unlink()
    s.atomic_bytes(remote.checkpoint,s.dumps(saved).encode());original=remote.checkpoint.read_bytes()
    assert 'requestId' not in vp.recovery_receipt(saved)
    assert 'requestId' not in vp.checkpoint_receipt(saved)
    with pytest.raises(vp.ProviderError) as exc:generate(client,remote)
    assert exc.value.code=='VIDEO_CHECKPOINT_ID'
    assert remote.checkpoint.read_bytes()==original and remote.posts==1 and len(remote.polls)==1


@pytest.mark.parametrize('fault',[429,500,503,'disconnect','truncated','timeout'])
def test_download_transient_retry_uses_same_result_and_counts_real_http(client,remote,fault):
    remote.download_actions=[fault,'valid']
    result=generate(client,remote)
    assert remote.posts==1 and remote.polls==['/videos/same-id']
    assert remote.downloads==2 and result['receipt']['downloadCount']==2


def test_download_retry_exhaustion_and_auth_stop(client,remote):
    remote.download=503
    with pytest.raises(vp.ProviderError) as exc:generate(client,remote)
    assert exc.value.code=='VIDEO_DOWNLOAD_RETRY_LIMIT'
    assert remote.downloads==4 and remote.posts==1
    assert vp.read_checkpoint(remote.checkpoint)['downloadCount']==4
    remote.download='auth-rejected'
    with pytest.raises(vp.ProviderError) as exc:generate(client,remote)
    assert exc.value.code=='GROK_AUTH_REJECTED' and remote.downloads==6
    assert remote.posts==1 and not (remote.work/'original.mp4').exists()


@pytest.mark.parametrize('name',['original.mp4.part','original.mp4'])
def test_original_publication_never_follows_planted_symlinks(client,remote,name):
    original=s.DATA/'synthetic-user-original';original.write_bytes(b'ORIGINAL MUST SURVIVE')
    work=s.DATA/'transport'/'generation';work.mkdir(parents=True)
    (work/name).symlink_to(original)
    if name=='original.mp4':
        with pytest.raises(vp.ProviderError):generate(client,remote)
        assert remote.posts==0 and (work/name).is_symlink()
    else:
        result=generate(client,remote)
        assert not result['path'].is_symlink() and (work/name).is_symlink()
        assert remote.posts==1 and result['path'].read_bytes()!=original.read_bytes()
    assert original.read_bytes()==b'ORIGINAL MUST SURVIVE'


def test_failed_atomic_original_publication_keeps_old_bytes_and_cleans_temp(client,remote,monkeypatch):
    import os
    work=s.DATA/'transport'/'generation';work.mkdir(parents=True)
    original=work/'original.mp4';original.write_bytes(b'OLD OUTPUT MUST SURVIVE')
    real_replace=os.replace
    def reject(source,target):
        if str(target)==str(original):raise OSError('synthetic atomic publication failure')
        return real_replace(source,target)
    monkeypatch.setattr(os,'replace',reject)
    with pytest.raises(vp.ProviderError):generate(client,remote)
    assert original.read_bytes()==b'OLD OUTPUT MUST SURVIVE'
    assert not list(work.glob('*.part')) and remote.posts==1


@pytest.mark.parametrize('outside',[False,True])
def test_generation_parent_symlink_cannot_escape_or_overwrite_project_bytes(client,remote,outside,tmp_path):
    target=(tmp_path if outside else s.DATA)/'synthetic-original-directory';target.mkdir()
    original=target/'original.mp4';original.write_bytes(b'PRESERVED ORIGINAL')
    work=s.DATA/'transport'/'generation';work.parent.mkdir(parents=True);work.symlink_to(target,target_is_directory=True)
    with pytest.raises(vp.ProviderError) as exc:generate(client,remote)
    assert exc.value.code=='VIDEO_CHECKPOINT_PATH' and remote.posts==0
    assert original.read_bytes()==b'PRESERVED ORIGINAL' and work.is_symlink()


def test_legacy_receipt_is_allowlisted_without_auth_or_rewriting_evidence(client,remote,monkeypatch):
    generate(client,remote)
    saved=vp.read_checkpoint(remote.checkpoint);saved.pop('requestIdVerified')
    secret='https://provider.invalid/clip?signature=LEGACY-SECRET'
    saved['receipt'].update(model=secret,url=secret,token='LEGACY-SECRET',elapsedSeconds=secret,postCount=secret)
    saved.update(stopReason=secret,pollCount=secret)
    s.atomic_bytes(remote.checkpoint,s.dumps(saved).encode());original=remote.checkpoint.read_bytes()
    monkeypatch.setattr(vp,'login_credential',lambda:pytest.fail('local reuse must not authenticate'))
    result=vp.generate(remote.source,remote.work,vp.validate_params({},generation=True),remote.checkpoint,'transport-hash')
    assert 'LEGACY-SECRET' not in json.dumps(result['receipt'])
    assert 'LEGACY-SECRET' not in json.dumps(vp.recovery_receipt(saved))
    assert result['receipt']['model']=='unknown' and result['receipt']['sha256']==s.digest(result['path'].read_bytes())
    assert vp.read_checkpoint(remote.checkpoint)['receipt']==saved['receipt']
    assert remote.checkpoint.read_bytes()==original
    assert remote.posts==1 and len(remote.polls)==1 and remote.downloads==1
