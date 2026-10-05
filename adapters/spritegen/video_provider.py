"""Single Grok login submission with durable receipt and GET-only resume."""
from __future__ import annotations
import json, shutil
from pathlib import Path
from services.api import store as s
from services.api.edits import number
from .provider import _engine, ProviderError

MODELS=('grok-imagine-video-1.5','grok-imagine-video-1.5-lite')
DEFAULTS=dict(state='walk',direction='side',facing='right',motionPrompt='',model=MODELS[0],durationSeconds=3,resolution='480p',key='auto',loopMode='auto',maxFrames=8,bodyHeight=94,cellWidth=64,cellHeight=128,finishMode='gif',repairMode='off',between='auto',startFoot='auto',bodyPlan='',equipment='')

def validate_params(params,*,generation):
    allowed=set(DEFAULTS)|{'referenceRevisionId','videoId','startFrame','endFrame','spillReferenceAssetId','matchClipId','startIndex'}
    if set(params)-allowed: raise s.AppError('VIDEO_FIELDS','지원하지 않는 영상 설정입니다.',details={'fields':sorted(set(params)-allowed)})
    value={**DEFAULTS,**params}
    # Only new walks adopt the game-sized cycle; explicit saved requests keep
    # their count, and other motions keep their previous extraction default.
    if 'maxFrames' not in params and value['state']!='walk': value['maxFrames']=32
    enums={'state':('idle','walk','run','jump','attack','dance','wave','cheer'),'direction':('side','front','back','front_diagonal','back_diagonal'),'facing':('right','left'),'model':MODELS,'resolution':('480p','720p'),'key':('auto','green','magenta','cyan','white'),'loopMode':('auto','full','manual'),'finishMode':('gif','rgba'),'repairMode':('off','auto','on'),'between':('auto','on','off'),'startFoot':('auto','left','right')}
    for k,values in enums.items():
        if value[k] not in values: raise s.AppError('VIDEO_SETTING',f'영상 {k} 설정을 확인하세요.')
    for k,lo,hi in [('durationSeconds',2,6),('maxFrames',4,64),('bodyHeight',16,512),('cellWidth',32,1024),('cellHeight',32,1024)]:
        number(value[k],lo,hi,k,True);value[k]=int(value[k])
    if value['bodyHeight']>value['cellHeight']-4: raise s.AppError('VIDEO_CELL','셀 높이를 몸 높이보다 4px 이상 크게 지정하세요.')
    if not isinstance(value['motionPrompt'],str) or len(value['motionPrompt'])>2000: raise s.AppError('VIDEO_PROMPT','동작 설명은 2,000자 이하로 입력하세요.')
    from .video_prompt import parse_structured_params
    parse_structured_params(value)
    if 'startIndex' in value:
        if generation: raise s.AppError('VIDEO_SETTING','시작 위상 직접 선택은 생성 완료된 영상에서 사용할 수 있습니다.')
        number(value['startIndex'],0,63,'시작 위상',True);value['startIndex']=int(value['startIndex'])
    if value['loopMode']=='manual':
        if generation: raise s.AppError('VIDEO_RANGE','구간 직접 선택은 생성 완료된 영상에서 사용할 수 있습니다.')
        number(value.get('startFrame'),0,599,'시작 프레임',True);number(value.get('endFrame'),1,600,'끝 프레임',True)
        if value['endFrame']<=value['startFrame']: raise s.AppError('VIDEO_RANGE','끝 프레임은 시작보다 커야 합니다.')
    if generation and 'spillReferenceAssetId' in params: raise s.AppError('VIDEO_SETTING','새 영상은 생성에 사용한 기준 그림으로 색 번짐을 판정합니다.')
    for k in ('videoId','referenceRevisionId','spillReferenceAssetId','matchClipId'):
        if k in value and value[k] is not None and (not isinstance(value[k],str) or not value[k]): raise s.AppError('VIDEO_SETTING',f'{k} 값을 확인하세요.')
    return value

def login_credential():
    _engine()
    from sprite_gen.gen.xai import resolve_credential,AUTH_SOURCE_GROK_LOGIN
    try: credential=resolve_credential(env={})
    except SystemExit as e: raise ProviderError('GROK_LOGIN_REQUIRED','Grok Build 로그인을 확인하세요. 만료됐다면 grok login으로 다시 로그인하세요.') from e
    if credential.source!=AUTH_SOURCE_GROK_LOGIN: raise ProviderError('GROK_LOGIN_REQUIRED','Grok Build 로그인이 필요합니다. API 키로 전환하지 않습니다.')
    return credential

def capability():
    ready=True; reason='Grok 로그인 파일을 확인했습니다. 실제 사용량과 서버 권한은 생성 시 확인됩니다.'
    try: login_credential()
    except (ImportError,ProviderError): ready=False;reason='Grok Build 로그인이 필요합니다. 터미널에서 grok login 후 연결을 다시 확인하세요.'
    dependencies=all(shutil.which(n) for n in ('ffmpeg','ffprobe'))
    if not dependencies: reason='영상 처리에 ffmpeg와 ffprobe가 필요합니다.'
    from .video_processing import rife_capability
    rife={k:v for k,v in rife_capability().items() if k not in ('binary','modelPath')}
    return dict(providerId='grok-video',label='Grok 영상',mediaKind='video',available=ready and dependencies,loginReady=ready,reason=reason,defaultModel=MODELS[0],models=[{'id':MODELS[0],'name':'Pro'},{'id':MODELS[1],'name':'Lite'}],billingRoute='Grok 로그인 · 계정 사용량 차감, 잔여량 확인 불가',quota=None,lastSuccess=None,capabilities=dict(video=True,resolution=True,resolutions=['480p','720p'],durationSeconds={'min':2,'max':6,'default':3},resume=True,apiKeyFallback=False,finishModes=['gif','rgba'],repairModes=['off','auto','on'],rife=rife))

def read_checkpoint(path):
    return json.loads(path.read_text()) if path.is_file() else None

def checkpoint_state(job):
    path=s.job_directory(job['jobId'])/'video-checkpoint.json'
    try: saved=read_checkpoint(path)
    except (OSError,ValueError): return {'outcomeUnknown':True,'resumable':False}
    if not saved: return {'outcomeUnknown':bool(job.get('externalStarted')),'resumable':False}
    if not isinstance(saved,dict): return {'outcomeUnknown':True,'resumable':False}
    return {'outcomeUnknown':saved.get('phase')=='submitting' and not saved.get('requestId'),
            'resumable':bool(saved.get('requestId') or saved.get('videoId')),'videoId':saved.get('videoId')}

def generate(source,work,params,checkpoint,request_hash,on_progress=lambda *_:None,*,credential=None,call=None,download=None,sleep=None,job_id=None):
    _engine()
    from sprite_gen.gen import video
    from .video_processing import prepare_still,build_motion_prompt
    saved=read_checkpoint(checkpoint)
    if saved and saved.get('requestHash')!=request_hash: raise ProviderError('VIDEO_CHECKPOINT_HASH','영상 요청과 저장된 작업이 다릅니다.')
    if saved and saved.get('requestId') and saved.get('localPath'):
        # The engine atomically renames the completed MP4 before returning. A
        # crash between that rename and our receipt write must remain local.
        local=s.resolve_work_path(job_id,saved['localPath']) if job_id else Path(saved['localPath']).resolve()
        job_root=s.job_directory(job_id).resolve() if job_id else checkpoint.parent.resolve()
        if not local.is_relative_to(job_root): raise ProviderError('VIDEO_CHECKPOINT_PATH','영상 체크포인트 경로가 잘못되었습니다.')
        if local.is_file():
            from services.api.videos import validate
            data=local.read_bytes();meta=validate(data,local.name)
            if saved.get('receipt',{}).get('sha256') not in (None,meta['sha256']): raise ProviderError('VIDEO_CHECKPOINT_HASH','받은 영상의 해시가 다릅니다.')
            receipt=saved.get('receipt') or dict(providerId='grok-video',model=params['model'],modelSource='request',authSource='grok-login',requestId=saved['requestId'],sha256=meta['sha256'],durationRequested=params['durationSeconds'],resolutionRequested=params['resolution'],downloadRecovered=True)
            saved.update(phase='downloaded',receipt=receipt)
            s.atomic_bytes(checkpoint,s.dumps(saved).encode())
            return {'path':local,'receipt':receipt,'preparation':saved.get('preparation'),'prompt':saved.get('prompt')}
    if saved and not saved.get('requestId'):
        if saved.get('phase')=='submitting': raise ProviderError('PROVIDER_OUTCOME_UNKNOWN','영상 접수 여부가 불명확합니다. 자동 재전송하지 않습니다.',outcome_unknown=True)
        if saved.get('phase')=='rejected': raise ProviderError('VIDEO_RETRY_BLOCKED','거절된 생성 요청을 재전송하지 않습니다. 설정을 확인한 뒤 새 요청을 만드세요.')
    credential=credential or login_credential()
    from sprite_gen.gen.xai import AUTH_SOURCE_GROK_LOGIN,http_json
    if credential.source!=AUTH_SOURCE_GROK_LOGIN: raise ProviderError('GROK_LOGIN_REQUIRED','Grok 로그인 인증만 사용할 수 있습니다.')
    transport=call or http_json
    work.mkdir(parents=True,exist_ok=True)
    on_progress('prepare','기준 그림과 동작을 준비합니다.')
    canvas=work/'input-canvas.png'; preparation=prepare_still(source,canvas,params)
    prompt=build_motion_prompt(params)
    state=saved or {'requestHash':request_hash,'phase':'prepared','postCount':0,'authSource':'grok-login','createdAt':s.now()}
    state.update(localPath=str((work/'original.mp4').resolve()),preparation=preparation,prompt=prompt)
    def save(): s.atomic_bytes(checkpoint,s.dumps(state).encode())
    save()
    def guarded(method,url,token,body=None):
        if method=='POST':
            if state.get('requestId'): return 200,{'request_id':state['requestId']}
            if state['postCount']!=0: raise ProviderError('VIDEO_RETRY_BLOCKED','추가 영상 생성 요청을 차단했습니다.')
            state.update(phase='submitting',postCount=1);save();on_progress('submit','Grok에 영상 1건을 요청합니다.')
            status,reply=transport(method,url,token,body)
            rid=reply.get('request_id') if isinstance(reply,dict) else None
            state.update(phase='submitted' if rid else 'rejected',requestId=rid,submitHttpStatus=status);save()
        else:
            on_progress('poll','접수된 영상의 완료 상태를 확인합니다.')
            status,reply=transport(method,url,token,body)
        if status in (401,403): raise ProviderError('GROK_AUTH_REJECTED','Grok이 인증을 거부했습니다. 로그인 상태를 확인한 뒤 기존 요청 조회를 재개하세요.')
        if status==429: raise ProviderError('GROK_USAGE_LIMIT','Grok 사용량 제한에 도달했습니다. 자동 재생성하지 않습니다.')
        return status,reply
    def fetch(url,token):
        on_progress('download','완성된 원본 영상을 보존합니다.')
        return (download or video.http_download)(url,token)
    try:
        from sprite_gen.video.batch import pins_last_frame
        result=video.generate_video(video.VideoRequest(image=canvas,prompt=prompt,out=work/'original.mp4',duration=params['durationSeconds'],resolution=params['resolution'],model=params['model'],generate_audio=False,direction=None if params['direction']=='side' else params['direction'].replace('-','_'),facing=params['facing'],last_frame=canvas if pins_last_frame(params['state'],params['direction'].replace('-','_')) else None),credential=credential,call=guarded,download=fetch,sleep=sleep,poll_timeout=600)
    except ProviderError: raise
    except (SystemExit,OSError,ValueError) as exc:
        unknown=state.get('phase')=='submitting' and not state.get('requestId')
        raise ProviderError('PROVIDER_OUTCOME_UNKNOWN' if unknown else 'VIDEO_PROVIDER_FAILED','영상 결과를 받지 못했습니다. 접수 ID가 있으면 기존 요청 조회를 재개할 수 있습니다.',outcome_unknown=unknown) from exc
    receipt={'providerId':'grok-video','model':result.model,'authSource':'grok-login','requestId':result.request_id,'durationRequested':params['durationSeconds'],'resolutionRequested':params['resolution'],'sha256':s.digest(result.out.read_bytes()),'elapsedSeconds':round(result.elapsed_seconds,3)}
    state.update(phase='downloaded',localPath=str(result.out),receipt=receipt,preparation=preparation,prompt=prompt);save()
    return {'path':result.out,'receipt':receipt,'prompt':prompt,'preparation':preparation}
