"""One attempt per isolated child process. No shell evaluation or implicit retries."""
from __future__ import annotations
import io, json, os, shutil, stat, sys, zipfile
from pathlib import Path, PurePosixPath
from PIL import Image
from services.api import store as s

def asset_from_image(image,name,provenance):
    b=io.BytesIO(); image.save(b,format='PNG'); return s.register_asset(b.getvalue(),name,'derived',provenance)

def backup(snapshot,out):
    files={}; asset_records=[]
    for a in snapshot['assets']:
        path=s.asset_path(a['assetId']); name='assets/'+a['sha256']; files[name]=path
        asset_records.append(dict(assetId=a['assetId'],file=name,sha256=a['sha256']))
    with zipfile.ZipFile(out/'project-backup.zip','w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('project.json',s.dumps({'schemaVersion':1,'snapshot':snapshot,'assets':asset_records}))
        for name,path in files.items(): z.write(path,name)
    return dict(files=['project-backup.zip'],summary='프로젝트 백업 완료')

def restore(request,out):
    path=s.DATA/'uploads'/request['backupHash']
    try:
        with zipfile.ZipFile(path) as z:
            infos=z.infolist()
            if len(infos)>2048 or sum(i.file_size for i in infos)>1024**3: raise s.AppError('BACKUP_LIMIT','백업 압축 해제 한도를 초과했습니다.')
            names=[]
            for i in infos:
                p=PurePosixPath(i.filename)
                if p.is_absolute() or '..' in p.parts or '\\' in i.filename or ':' in i.filename or stat.S_ISLNK(i.external_attr>>16): raise s.AppError('BACKUP_PATH','안전하지 않은 백업 경로입니다.')
                names.append(i.filename)
            if len(names)!=len(set(names)): raise s.AppError('BACKUP_DUPLICATE','중복 항목이 있는 백업입니다.')
            if z.getinfo('project.json').file_size>32*1024*1024: raise s.AppError('BACKUP_LIMIT','프로젝트 데이터 한도를 초과했습니다.')
            payload=json.loads(z.read('project.json'))
            if payload.get('schemaVersion')!=1 or payload.get('snapshot',{}).get('schemaVersion')!=1: raise s.AppError('SCHEMA_UNSUPPORTED','지원하지 않는 백업 버전입니다.')
            p=s.validate_snapshot(payload['snapshot']); pending=[]
            for a in payload['assets']:
                data=z.read(a['file'])
                if s.digest(data)!=a['sha256']: raise s.AppError('BACKUP_HASH','백업 자료의 해시가 일치하지 않습니다.')
                old=next((x for x in p['assets'] if x['assetId']==a['assetId']),None)
                if not old or old['sha256']!=a['sha256']: raise s.AppError('BACKUP_ASSETS','백업 자료 목록이 일치하지 않습니다.')
                meta=s.validate_image(data,old['originalFilename']); pending.append((old,data,meta))
            if {a['assetId'] for a,_,_ in pending}!={a['assetId'] for a in p['assets']}: raise s.AppError('BACKUP_ASSETS','필수 자료가 누락되었습니다.')
            mapping={}
            for old,data,meta in pending:
                new=s.register_asset(data,old['originalFilename'],old['role'],old['provenance'],meta); mapping[old['assetId']]=new
            # Portable snapshot contains only relative public URLs. Remap each opaque asset use.
            def remap(v):
                if isinstance(v,dict): return {k:remap(x) for k,x in v.items()}
                if isinstance(v,list): return [remap(x) for x in v]
                if isinstance(v,str) and v in mapping: return mapping[v]['assetId']
                return v
            p=remap(p); p['assets']=list(mapping.values()); p=s.remap_reference_ids(p)
            p.update(projectId=s.uid(),name=p['name']+' (복원)',revision=1,journal=[],createdAt=s.now())
            return dict(restoredProject=p,files=[])
    except (zipfile.BadZipFile,KeyError,ValueError,TypeError) as e: raise s.AppError('BACKUP_INVALID','손상되었거나 지원하지 않는 백업입니다.') from e

def execute(j,out):
    from alignment.pipeline import extract_regions,suggest_anchor,cutout_image,build_bundle
    p=j['snapshot']; request=j['request']; op=j['operation']; params=request.get('params',{})
    out.mkdir(parents=True,exist_ok=True)
    if op=='backup': return backup(p,out)
    if op=='restore': return restore(request,out)
    if op=='generate':
        from adapters.spritegen.provider import generate
        rid=params.get('referenceRevisionId',p['activeReferenceRevisionId']); ref=next(r for r in p['references'] if r['referenceRevisionId']==rid)
        checkpoint=out.parent/'provider-completed.json'
        if j.get('reuseProviderAttemptId') and not checkpoint.exists():
            prior=s.DATA/'jobs'/j['jobId']/j['reuseProviderAttemptId']/'provider-completed.json'
            recovered=json.loads(prior.read_text())
            local=[]
            for i,name in enumerate(recovered['providerResult']['paths']):
                source=Path(name).resolve()
                if not source.is_relative_to(s.DATA) or not source.is_file(): raise s.AppError('CHECKPOINT_MISSING','확정 생성 원본이 없습니다.')
                expected=recovered['providerResult']['receipt'].get('sha256')
                if expected and s.digest(source.read_bytes())!=expected: raise s.AppError('CHECKPOINT_HASH','생성 원본의 해시가 다릅니다.')
                target=out/f'recovered-{i}.png'; shutil.copyfile(source,target); local.append(str(target))
            recovered['providerResult']['paths']=local
            s.atomic_bytes(checkpoint,s.dumps(recovered).encode())
        if checkpoint.exists():
            saved=json.loads(checkpoint.read_text())
            if saved['requestHash']!=j['requestHash']: raise s.AppError('CHECKPOINT_HASH','생성 체크포인트의 입력이 다릅니다.')
            result=saved['providerResult']
        else:
            if params.get('scope')=='frame':
                frame=next((f for f in p['frames'] if f['frameVersionId']==params.get('frameVersionId')),None)
                if frame is None: raise s.AppError('FRAME_MISSING','재생성할 프레임을 선택하세요.')
                asset=next(a for a in p['assets'] if a['assetId']==frame['imageAssetId'])
                target={'frameVersionId':frame['frameVersionId'],'imageAssetId':asset['assetId'],'sha256':asset['sha256']}
                result=generate(params,ref,s.asset_path,out,regeneration_target=target)
            else:
                result=generate(params,ref,s.asset_path,out)
            s.atomic_bytes(checkpoint,s.dumps({'requestHash':j['requestHash'],'providerResult':result}).encode())
        gid=s.uid(); assets=[]
        for name in result['paths']:
            path=Path(name)
            if not path.is_absolute(): path=out/path
            if not path.resolve().is_relative_to(out.resolve()): raise s.AppError('PROVIDER_PATH','생성 결과 경로가 잘못되었습니다.')
            assets.append(s.register_asset(path.read_bytes(),path.name,'source',{'kind':'real-provider','providerId':result['providerId'],'generationVersionId':gid,'referenceRevisionId':rid}))
        generation=dict(generationVersionId=gid,jobId=j['jobId'],referenceRevisionId=rid,requestSnapshot=result['requestSnapshot'],promptHash=s.digest(params.get('prompt','').encode()),providerId=result['providerId'],model=result['model'],receipt=result['receipt'],rawAssetIds=[a['assetId'] for a in assets],requestedFrameCount=params.get('frameCount',1),returnedImageCount=len(assets),scope=params.get('scope','states'),parentFrameVersionId=params.get('frameVersionId'))
        return dict(assets=assets,generations=[generation],files=[],status='needs_review',receipt=result['receipt'])
    if op in ('extract','cutout'):
        aids=request.get('assetIds',[])
        if not aids: raise s.AppError('ASSETS_REQUIRED','처리할 이미지를 선택하세요.')
        assets=[]; frames=[]; alignments={}; groups=[]; warnings=[]
        existing=next((g for g in p['alignmentGroups'] if g['alignmentGroupId']==params.get('groupId')),None)
        cell=p.get('defaultCell',{'width':512,'height':512})
        group=existing or dict(alignmentGroupId=s.uid(),groupRevisionId=s.uid(),frameVersionIds=[],mode='preserve-source-scale',sharedScale=1,cell={**cell,'edge':2},targetAnchor={'x':cell['width']/2,'y':cell['height']-18},bodyMeasurement=None,resampler='nearest',roundingVersion='js-round-v1')
        for aid in aids:
            path=s.asset_path(aid)
            if op=='cutout':
                target=out/f'{s.uid()}.png'; stats=cutout_image(path,target,params)
                assets.append(s.register_asset(target.read_bytes(),'배경정리.png','derived',{'kind':'cutout','parentAssetId':aid,'params':params})); continue
            crops=extract_regions(path,params)
            for i,crop in enumerate(crops):
                img=crop['image']; meta=asset_from_image(img,f'프레임-{i+1}.png',{'kind':'raw-crop','parentAssetId':aid,'sourceRect':crop['rect']}); assets.append(meta)
                fid=s.uid(); source=next(a for a in p['assets'] if a['assetId']==aid)
                f=dict(frameId=s.uid(),frameVersionId=fid,rawAssetId=aid,imageAssetId=meta['assetId'],sourceRect=crop['rect'],sourceToFrameTransform=crop.get('sourceToFrameTransform',{'scaleX':1,'scaleY':1,'offsetX':-crop['rect']['x'],'offsetY':-crop['rect']['y']}),extractionVersion='raw-v1',nativeScaleGroupId=group['alignmentGroupId'],review='pending',hidden=False)
                # Follow immutable derived assets back to their generation, including cutout.
                ancestor=source; seen=set(); gen=None
                while ancestor and ancestor['assetId'] not in seen:
                    seen.add(ancestor['assetId']); provenance=ancestor.get('provenance',{})
                    gen=provenance.get('generationVersionId')
                    if gen: break
                    ancestor=next((a for a in p['assets'] if a['assetId']==provenance.get('parentAssetId')),None)
                if gen:
                    f['generationVersionId']=gen
                    generation=next((v for v in p['generations'] if v['generationVersionId']==gen),{})
                    parent=next((v for v in p['frames'] if v['frameVersionId']==generation.get('parentFrameVersionId')),None)
                    if parent: f.update(frameId=parent['frameId'],parentFrameVersionId=parent['frameVersionId'])
                f['extractionReview']={k:v for k,v in crop.items() if k not in ('image','rect','sourceToFrameTransform')}
                frames.append(f); group['frameVersionIds'].append(fid)
                try: anchor=suggest_anchor(img)
                except Exception: anchor={'x':img.width/2,'y':img.height}
                alignments[fid]=dict(frameVersionId=fid,groupRevisionId=group['groupRevisionId'],sourceAnchor=anchor,anchorSpace='crop',method='automatic',contactMode='grounded',authoredOffsetPx={'x':0,'y':0},approval='pending')
                if crop.get('warnings'): warnings.extend(crop['warnings'])
        if op=='extract': groups=[group]
        return dict(assets=assets,frames=frames,alignmentGroups=groups,alignments=alignments,warnings=warnings,files=[],status='needs_review')
    if op in ('align','inspect','bake','export'):
        rids=request.get('clipRevisionIds',params.get('clipRevisionIds'))
        if 'clipIds' not in params and rids is not None:
            if len(set(rids))!=len(rids): raise s.AppError('INVALID_CLIP_SELECTION','같은 동작이 중복 선택되었습니다.')
            missing=set(rids)-{cl['clipRevisionId'] for cl in p['clips']}
            if missing: raise s.AppError('CLIP_MISSING','선택한 동작 버전을 찾을 수 없습니다.',422,{'affectedIds':sorted(missing)})
        ids=params['clipIds'] if 'clipIds' in params else [cl['clipId'] for cl in p['clips'] if rids is None or cl['clipRevisionId'] in rids]
        if not ids: raise s.AppError('EMPTY_TIMELINE','검수할 동작을 선택하세요.')
        strict=op=='export'
        eid=j.get('exportId',j['jobId'])
        return build_bundle(p,ids,s.asset_path,out,eid,strict=strict,outline_mode=request.get('outlineMode',p['outline'].get('mode','bake')))
    raise s.AppError('OPERATION_UNSUPPORTED','지원하지 않는 처리입니다.')

def main():
    jid,attempt_id=sys.argv[1:3]; s.init(); j=s.get_job(jid)
    if j['attemptId']!=attempt_id: return
    out=s.DATA/'jobs'/jid/attempt_id/'staging'; result_path=out.parent/'result.json'
    try:
        if j.get('reuseResultAttemptId'):
            previous=s.DATA/'jobs'/jid/j['reuseResultAttemptId']
            payload=json.loads((previous/'result.json').read_text())
            if not payload.get('ok'): raise s.AppError('CHECKPOINT_INVALID','완료 체크포인트가 없습니다.')
            source=previous/'staging'
            if not source.exists(): source=s.DATA/'artifacts'/jid/j['reuseResultAttemptId']
            shutil.copytree(source,out)
            result=payload['result']
            for name,expected in result.get('publicationHashes',{}).items():
                if s.digest((out/name).read_bytes())!=expected: raise s.AppError('CHECKPOINT_HASH','완료 파일의 해시가 다릅니다.')
        else:
            result=execute(j,out)
        result['publicationHashes']={name:s.digest((out/name).read_bytes()) for name in result.get('files',[])}
        s.atomic_bytes(result_path,s.dumps({'ok':True,'result':result}).encode())
    except BaseException as e:
        error=dict(code=getattr(e,'code','PROCESSING_FAILED'),message=getattr(e,'message','처리에 실패했습니다. 입력과 설정을 확인하세요.'),details=getattr(e,'details',{}),stage=j['operation'],retryable=j['operation']!='generate')
        # Exception text from providers can contain credentials; only typed safe fields are exposed.
        checkpoint=out.parent/'provider-completed.json'
        completed=json.loads(checkpoint.read_text()) if checkpoint.exists() else None
        s.atomic_bytes(result_path,s.dumps({'ok':False,'error':error,'outcomeUnknown':bool(getattr(e,'outcome_unknown',False)),'exceptionType':type(e).__name__,'providerCheckpoint':completed}).encode())
        raise SystemExit(1)
if __name__=='__main__': main()
