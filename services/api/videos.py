"""Immutable MP4 resources, kept separate from PNG/WebP assets."""
from __future__ import annotations
import json, tempfile
from pathlib import Path
from adapters.spritegen.video_probe import MAX_BYTES, VideoProbeError, read_timing
from . import store as s

def validate(data:bytes,filename:str)->dict:
    if len(data)>MAX_BYTES: raise s.AppError('VIDEO_LIMIT','영상은 64 MiB 이하로 선택하세요.',413)
    if len(data)<12 or data[4:8]!=b'ftyp': raise s.AppError('VIDEO_FORMAT','정상 MP4 영상을 선택하세요.')
    with tempfile.TemporaryDirectory(prefix='frame-room-video-') as d:
        path=Path(d)/'input.mp4'; path.write_bytes(data)
        try:
            timing=read_timing(path)
        except VideoProbeError as exc:
            if exc.code=='VIDEO_DEPENDENCY':
                raise s.AppError(exc.code,'영상 정보를 읽을 ffprobe가 필요합니다.',424) from exc
            if exc.code=='VIDEO_DIMENSIONS':
                raise s.AppError(exc.code,'영상은 15초·2048px·60fps·600프레임 이하여야 합니다.',413) from exc
            if exc.code=='VIDEO_LIMIT':
                raise s.AppError(exc.code,'영상은 64 MiB 이하로 선택하세요.',413) from exc
            raise s.AppError('VIDEO_DECODE','영상 정보를 읽지 못했습니다. 정상 MP4를 선택하세요.') from exc
    return dict(sha256=s.digest(data),originalFilename=Path(filename).name[:250],mediaType='video/mp4',
                **{key:timing[key] for key in ('width','height','fps','frameCount','streamIndex','constantFrameRate')},
                durationMs=round(timing['durationMs']))

def register(data,filename,provenance=None,metadata=None,c=None,project_id=None):
    meta=dict(metadata or validate(data,filename)); vid=s.uid()
    path=s.DATA/'videos'/meta['sha256'][:2]/(meta['sha256']+'.mp4')
    pid=project_id or s._project_scope.get()
    if pid:
        from .project_folders import resource_name
        path=s.project_folder(pid,c)/resource_name('videos',vid,meta)
    if path.exists():
        if s.digest(path.read_bytes())!=meta['sha256']: raise s.AppError('VIDEO_HASH','보존 영상의 해시가 일치하지 않습니다.',424)
    else: s.atomic_bytes(path,data)
    meta.update(videoId=vid,url=f'/v1/videos/{vid}/content',provenance=provenance or {'kind':'imported-video'})
    if c is None:
        with s.transaction() as cc:
            cc.execute('INSERT INTO videos VALUES (?,?,?)',(vid,s.dumps(meta),s.stored_path(path)))
            s.own_resource(cc,pid,'videos',vid)
    else:
        c.execute('INSERT INTO videos VALUES (?,?,?)',(vid,s.dumps(meta),s.stored_path(path)))
        s.own_resource(c,pid,'videos',vid)
    return meta

def path_for(vid):
    with s.connect() as c: row=c.execute('SELECT metadata,path FROM videos WHERE id=?',(vid,)).fetchone()
    if not row: raise s.AppError('VIDEO_MISSING','보존 영상을 찾을 수 없습니다.',424)
    from .project_folders import resource_path
    path=resource_path('videos',vid,row)
    if s.digest(path.read_bytes())!=json.loads(row['metadata'])['sha256']: raise s.AppError('VIDEO_HASH','원본 영상의 해시가 변경되었습니다.',424)
    return path

def metadata_for(vid,c=None):
    if c is None:
        with s.connect() as db: return metadata_for(vid,db)
    row=c.execute('SELECT metadata FROM videos WHERE id=?',(vid,)).fetchone()
    if not row: raise s.AppError('VIDEO_MISSING','보존 영상 기록이 없습니다.',424)
    return json.loads(row[0])

def attach_dependencies(project,video,references,c,*,reference_ids=(),asset_ids=()):
    """Append required immutable sources after a concurrent revision restore.

    Keep the user's active reference and existing edits. A completed job may
    reintroduce only the sources needed by its newly published candidates.
    """
    assets={a['assetId'] for a in project['assets']};visited_videos=set()
    def asset(aid):
        if not aid or aid in assets: return
        row=c.execute('SELECT metadata FROM assets WHERE id=?',(aid,)).fetchone()
        if not row: raise s.AppError('ASSET_MISSING','영상 원본의 참조 이미지가 없습니다.',424)
        item=json.loads(row[0]);assets.add(aid);project['assets'].append(item)
        provenance=item.get('provenance',{})
        asset(provenance.get('parentAssetId'))
        asset(provenance.get('spillReferenceAssetId'))
        if provenance.get('sourceVideoId'): attach(metadata_for(provenance['sourceVideoId'],c))
    def attach(item,extra_refs=()):
        if item['videoId'] in visited_videos: return
        visited_videos.add(item['videoId'])
        provenance=item.get('provenance',{})
        for key in ('baseAssetId','referenceAssetId'): asset(provenance.get(key))
        ref_ids=set(extra_refs)|{provenance.get('referenceRevisionId')}
        for rid in ref_ids-{None}:
            reference=next((r for r in project['references'] if r['referenceRevisionId']==rid),None)
            if reference is None:
                reference=next((r for r in references if r['referenceRevisionId']==rid),None)
                if reference is None: raise s.AppError('REFERENCE_MISSING','영상 제작에 사용한 기준 기록이 없습니다.',424)
                project['references'].append(reference)
            for aid in [reference['identityAssetId']]+reference.get('styleAssetIds',[])+reference.get('poseAssetIds',[]): asset(aid)
        if not any(v['videoId']==item['videoId'] for v in project.setdefault('videos',[])): project['videos'].append(item)
    attach(video,reference_ids)
    for aid in asset_ids: asset(aid)
