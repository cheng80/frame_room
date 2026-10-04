"""Video jobs: preserve the received MP4 before any fallible local processing."""
from __future__ import annotations
from pathlib import Path
from services.api import store as s, videos
from adapters.spritegen.video_provider import validate_params,read_checkpoint,checkpoint_state,generate

STAGES={'prepare':5,'submit':10,'poll':20,'download':45,'extract':55,'select_cycle':75,'finish_frames':85,'import_candidates':90}

def execute_video(j,out):
    from adapters.spritegen.video_processing import process_clip
    params=validate_params(j['request'].get('params',{}),generation=j['operation']=='generate_video')
    checkpoint=s.job_directory(j['jobId'])/'video-checkpoint.json'
    def progress(stage,message):
        with s.transaction() as c:
            current=s.get_job(j['jobId'],c)
            if current['attemptId']!=j['attemptId']: raise s.AppError('JOB_STALE','이전 실행이 중단되었습니다.')
            if current['status']=='cancel_requested': raise s.AppError('CANCELED','로컬 처리가 취소되었습니다. 받은 영상은 보존됩니다.')
            if stage==current.get('step'): return
            current.update(step=stage,progress={'percent':STAGES.get(stage,0),'message':message})
            if stage=='submit': current['externalStarted']=True
            if j['operation']=='generate_video': current.update({k:v for k,v in checkpoint_state(j).items() if k!='outcomeUnknown'})
            s.write_job(c,current)
    receipt=None;prompt=None;preparation=None
    if j['operation']=='generate_video':
        saved=read_checkpoint(checkpoint)
        if saved and saved.get('requestHash')!=j['requestHash']: raise s.AppError('VIDEO_CHECKPOINT_HASH','다른 요청의 영상 체크포인트입니다.')
        current=s.get_project(j['projectId'])
        video=next((v for v in current.get('videos',[]) if v.get('provenance',{}).get('jobId')==j['jobId']),None)
        if video is None and saved and saved.get('videoId'):
            video=videos.metadata_for(saved['videoId'])
        if video:
            receipt=video['provenance'].get('receipt');preparation=video['provenance'].get('preparation');video_path=videos.path_for(video['videoId'])
            if not any(v['videoId']==video['videoId'] for v in current.get('videos',[])):
                with s.transaction() as c:
                    current=s.get_project(j['projectId'],c)
                    videos.attach_dependencies(current,video,j['snapshot']['references'],c)
                    s.write_project(c,current,'보존 영상 다시 연결')
        else:
            received=None
            if saved and saved.get('phase')=='downloaded':
                old=s.resolve_work_path(j['jobId'],saved.get('localPath',''))
                if not old.is_relative_to(s.job_directory(j['jobId']).resolve()) or not old.is_file(): raise s.AppError('VIDEO_CHECKPOINT_MISSING','받은 영상 파일이 없습니다. 추가 생성은 실행하지 않았습니다.',424)
                if s.digest(old.read_bytes())!=saved['receipt']['sha256']: raise s.AppError('VIDEO_CHECKPOINT_HASH','받은 영상의 해시가 다릅니다.',424)
                received={'path':old,'receipt':saved['receipt'],'preparation':saved.get('preparation'),'prompt':saved.get('prompt')}
            if received is None:
                source=s.asset_path(j['request']['assetIds'][0])
                received=generate(source,out/'generation',params,checkpoint,j['requestHash'],progress,job_id=j['jobId'])
            receipt=received['receipt'];prompt=received.get('prompt');preparation=received.get('preparation')
            data=Path(received['path']).read_bytes();meta=videos.validate(data,'Grok-'+params['state']+'.mp4')
            provenance={'kind':'real-provider-video','providerId':'grok-video','jobId':j['jobId'],'baseAssetId':j['request']['assetIds'][0],
                        'referenceRevisionId':params.get('referenceRevisionId'),'receipt':receipt,'settings':params,'prompt':prompt,'preparation':preparation}
            with s.transaction() as c:
                current=s.get_project(j['projectId'],c)
                if preparation:
                    prepared=s.resolve_work_path(j['jobId'],preparation['path'])
                    if not prepared.is_relative_to(s.job_directory(j['jobId']).resolve()) or not prepared.is_file(): raise s.AppError('VIDEO_INPUT_MISSING','영상용 기준 그림이 없습니다.')
                    reference=s.register_asset(prepared.read_bytes(),'영상 기준 캔버스.png','derived',{'kind':'video-input','parentAssetId':j['request']['assetIds'][0]},c=c)
                    current['assets'].append(reference)
                    provenance['referenceAssetId']=reference['assetId']
                    provenance['preparation']={k:v for k,v in preparation.items() if k not in ('path','sourcePath')}
                video=videos.register(data,'Grok-'+params['state']+'.mp4',provenance,meta,c)
                videos.attach_dependencies(current,video,j['snapshot']['references'],c)
                s.write_project(c,current,'Grok 원본 영상 보존')
            video_path=videos.path_for(video['videoId'])
        saved=read_checkpoint(checkpoint) or {'requestHash':j['requestHash']}
        saved.update(phase='preserved',videoId=video['videoId'],receipt=receipt)
        s.atomic_bytes(checkpoint,s.dumps(saved).encode())
    else:
        video=next(v for v in j['snapshot'].get('videos',[]) if v['videoId']==params['videoId'])
        video_path=videos.path_for(video['videoId'])
        stored_settings=video.get('provenance',{}).get('settings',{})
        for field in ('direction','facing'):
            if field not in j['request'].get('params',{}) and field in stored_settings:
                params[field]=stored_settings[field]
    with s.transaction() as c:
        current=s.get_job(j['jobId'],c);current.update(resumable=True,result={'videoId':video['videoId'],**({'receipt':receipt} if receipt else {})});s.write_job(c,current)
    processing_params=dict(params)
    match_clip=None
    if params.get('matchClipId'):
        match_clip=next(cl for cl in j['snapshot']['clips'] if cl['clipId']==params['matchClipId'])
        processing_params.update(targetFrameCount=len(match_clip['occurrences']),
                                 targetDurationMs=sum(o['durationMs'] for o in match_clip['occurrences']))
    preparation=preparation or video.get('provenance',{}).get('preparation')
    if preparation:
        if j['operation']=='generate_video': processing_params['key']=preparation['key']
    spill_reference=params.get('spillReferenceAssetId') or video.get('provenance',{}).get('referenceAssetId')
    if spill_reference:
        processing_params['referencePath']=str(s.asset_path(spill_reference))
    result=process_clip(video_path,out/'processing',processing_params,on_progress=progress)
    if match_clip and result['selection'].get('cycleAlignment'):
        result['selection']['cycleAlignment'].update(matchClipId=match_clip['clipId'],matchClipRevisionId=match_clip['clipRevisionId'])
    # Public lineage records IDs and decisions, not machine-local file paths.
    spill={k:v for k,v in result.get('extraction',{}).get('spill',{}).items() if k not in ('reference','referencePath')}
    progress('finish_frames','편집·출력에 사용할 색상과 투명도를 마무리합니다.')
    gid=s.uid();grid=params['cellWidth'],params['cellHeight'];source=result['source'];anchor=result['anchor']
    scale=params['bodyHeight']/result['standingHeight']
    if not .01<=scale<=8: raise s.AppError('VIDEO_SCALE','원본 체고와 목표 크기의 차이가 너무 큽니다. 목표 몸 높이를 조정하세요.')
    from adapters.spritegen.video_normalization import normalize_frames
    keyed_dir=result.get('extraction',{}).get('processedKeyedDir') or result.get('extraction',{}).get('keyedDir')
    bounds_paths=sorted(Path(keyed_dir).glob('frame-*.png'))[result['selection']['startFrame']:result['selection']['endFrame']] if keyed_dir else None
    bounds_paths=result.get('boundsPaths') or bounds_paths
    normalized,normalization=normalize_frames(result['frames'],result['standingHeight'],params['bodyHeight'],out/'normalized',bounds_paths=bounds_paths,source_anchor=result['anchor'],resize_mode='legacy' if params['finishMode']=='gif' else 'color-alpha')
    from adapters.spritegen.video_finish import finish_frames
    finished,finish=finish_frames(normalized,out/'finished',mode=params['finishMode'],cell_width=grid[0],cell_height=grid[1])
    progress('import_candidates','마무리한 프레임을 새 동작과 후보에 등록합니다.')
    anchor=normalization['anchor']
    group=dict(alignmentGroupId=gid,groupRevisionId=s.uid(),frameVersionIds=[],mode='preserve-source-scale',sharedScale=1,
               cell={'width':grid[0],'height':grid[1],'edge':2},targetAnchor={'x':grid[0]/2,'y':grid[1]-10},bodyMeasurement=None,resampler='nearest',roundingVersion='js-round-v1',
               measurementProposal={'bodyHeight':result['standingHeight']*normalization['sourceToFrameTransform']['scaleY'],'targetHeight':params['bodyHeight'],'source':'video-normalized-first-frame'})
    assets=[];frames=[];alignments={};occurrences=[]
    generation_id=s.uid() if receipt else None
    for item,normalized_path,finished_path in zip(result['frames'],normalized,finished):
        provenance={'kind':'video-frame','sourceVideoId':video['videoId'],'sourceVideoSha256':video['sha256'],
                    'sourceFrameIndex':item['sourceFrameIndex'],'sourceTimeMs':item['sourceTimeMs'],'interpolated':bool(item.get('interpolated')),
                    'sourceProcessing':item.get('processing',{'kind':'chroma-key'}),
                    **({'interpolation':item['processing']['interpolation']} if item.get('processing',{}).get('interpolation') else {})}
        if generation_id: provenance['generationVersionId']=generation_id
        source_provenance={k:v for k,v in provenance.items() if k not in ('interpolation','sourceProcessing')};source_provenance['interpolated']=False
        raw=videos_frame_asset(item['rawPath'],f"영상원본-{item['sourceFrameIndex']}.png",{**source_provenance,'kind':'video-frame-raw'})
        keyed=videos_frame_asset(item.get('originalKeyedPath',item['keyedPath']),f"영상후보-{item['sourceFrameIndex']}.png",{**source_provenance,'parentAssetId':raw['assetId'],'processing':'chroma-key','spill':spill,**({'spillReferenceAssetId':spill_reference} if spill_reference else {})})
        assets.extend([raw,keyed])
        if item.get('originalKeyedPath',item['keyedPath'])!=item['keyedPath']:
            keyed=videos_frame_asset(item['keyedPath'],f"영상보완-{item['sourceFrameIndex']}.png",{**provenance,'parentAssetId':keyed['assetId'],'processing':item.get('processing',{}).get('kind','video-motion-correction')})
            assets.append(keyed)
        normalized_asset=videos_frame_asset(normalized_path,f"영상크기-{item['sourceFrameIndex']}.png",{**provenance,'parentAssetId':keyed['assetId'],'processing':'video-normalization','normalization':normalization,'spill':spill,**({'spillReferenceAssetId':spill_reference} if spill_reference else {})})
        candidate=videos_frame_asset(finished_path,f"영상편집-{item['sourceFrameIndex']}.png",{**provenance,'parentAssetId':normalized_asset['assetId'],'processing':'video-finish','normalization':normalization,'finish':finish})
        assets.extend([normalized_asset,candidate]);fid=s.uid();group['frameVersionIds'].append(fid)
        frame=dict(frameId=s.uid(),frameVersionId=fid,rawAssetId=raw['assetId'],imageAssetId=candidate['assetId'],sourceRect=normalization['sourceRect'],
                   sourceToFrameTransform=normalization['sourceToFrameTransform'],extractionVersion='video-v3-finished',nativeScaleGroupId=gid,review='pending',hidden=False,
                   sourceVideoId=video['videoId'],sourceFrameIndex=item['sourceFrameIndex'],sourceTimeMs=item['sourceTimeMs'],interpolated=bool(item.get('interpolated')),
                   **({'interpolation':item['processing']['interpolation']} if item.get('processing',{}).get('interpolation') else {}))
        frame['sourceProcessing']=item.get('processing',{'kind':'chroma-key'})
        if generation_id: frame['generationVersionId']=generation_id
        frames.append(frame)
        alignments[fid]=dict(frameVersionId=fid,groupRevisionId=group['groupRevisionId'],sourceAnchor=anchor,anchorSpace='crop',method='automatic',contactMode='grounded',authoredOffsetPx={'x':0,'y':0},approval='pending')
        occurrences.append(dict(occurrenceId=s.uid(),frameVersionId=fid,durationMs=item['durationMs'],timingMode='explicit',transform={'dx':0,'dy':0,'scaleX':1,'scaleY':1,'rotationDeg':0,'shearX':0,'shearY':0,'flipX':False,'flipY':False},pixelEdits=[]))
    names={'idle':'대기','walk':'걷기','run':'달리기','jump':'점프','attack':'공격','dance':'춤','wave':'손 흔들기','cheer':'환호'}
    directions={'side':'측면','front':'정면','back':'뒷면','front_diagonal':'앞 대각선','back_diagonal':'뒤 대각선'}
    clip=dict(clipId=s.uid(),clipRevisionId=s.uid(),name=f"영상 {names[params['state']]} · 검수 대기",stateId=params['state'],facing=params['facing'],referenceRevisionId=params.get('referenceRevisionId') or j['snapshot'].get('activeReferenceRevisionId'),loop=result['selection']['loop'],endBehavior='hold-last',defaultFps=min(60,max(1,round(len(frames)/(sum(o['durationMs'] for o in occurrences)/1000)))),occurrences=occurrences,review='pending',sourceVideoId=video['videoId'])
    clip['direction']=params['direction']
    clip['name']=f"영상 {names[params['state']]} · {directions[params['direction']]} · 검수 대기"
    generations=[]
    if receipt:
        generations=[dict(generationVersionId=generation_id,jobId=j['jobId'],providerId='grok-video',model=receipt['model'],sourceVideoId=video['videoId'],receipt=receipt,requestSnapshot=params,rawAssetIds=[a['assetId'] for a in assets if a['provenance']['kind']=='video-frame-raw'])]
    # Publish a preview from the same finished assets and geometry as the editor.
    # The extraction thumbnail remains diagnostic only and is not the result preview.
    from alignment.pipeline import render_occurrence
    from alignment.animation_exports import write_animation_formats
    preview_snapshot={**j['snapshot'],'assets':j['snapshot']['assets']+assets,
                      'frames':j['snapshot']['frames']+frames,
                      'alignmentGroups':j['snapshot']['alignmentGroups']+[group],
                      'alignments':{**j['snapshot']['alignments'],**alignments}}
    cells=[render_occurrence(preview_snapshot,clip,o,s.asset_path,include_outline=False)[0] for o in occurrences]
    preview=write_animation_formats(cells,[o['durationMs'] for o in occurrences],clip['loop'],out/'final-preview')
    s.atomic_bytes(out/'final-preview'/'preview.json',s.dumps(preview).encode())
    intermediate_files=[name for name in result.get('files',[]) if not name.endswith(('preview.gif','preview.sheet.png'))]
    files=['processing/'+name for name in intermediate_files]+['normalized/normalization.json','finished/finish.json']
    files+=['final-preview/'+name for name in preview['files']]+['final-preview/preview.json']
    return dict(assets=assets,frames=frames,alignmentGroups=[group],alignments=alignments,clips=[clip],generations=generations,
                files=files,status='needs_review',videoId=video['videoId'],clipId=clip['clipId'],frameVersionIds=group['frameVersionIds'],
                processing={'source':source,'selection':result['selection'],'outputFrames':len(frames),'durationMs':sum(o['durationMs'] for o in occurrences),'normalization':normalization,'finish':finish,'preview':preview,'spill':spill,**({'spillReferenceAssetId':spill_reference} if spill_reference else {})},**({'receipt':receipt} if receipt else {}))

def videos_frame_asset(path,name,provenance):
    return s.register_asset(Path(path).read_bytes(),name,'derived',provenance)
