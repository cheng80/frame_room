"""Normalize decoded video once, before the editor's nearest-neighbour workflow.

Matches video.loop.build_strip's union crop + Lanczos sampling without its
implicit cell/frame caps. Every pose uses the same source rectangle and scale.
Raw and full-size keyed frames remain separate immutable source assets.
"""
from pathlib import Path
from PIL import Image
from services.api import store as s


def normalize_frames(frames, standing_height, body_height, directory, *, bounds_paths=None, source_anchor=None, resize_mode='legacy'):
    if resize_mode not in ('legacy','color-alpha'):
        raise s.AppError('VIDEO_RESIZE','영상 크기 처리 설정을 확인하세요.')
    boxes=[]
    for path in bounds_paths or [frame['keyedPath'] for frame in frames]:
        with Image.open(path) as im:
            box=im.convert('RGBA').getchannel('A').point(lambda a:255 if a>=8 else 0).getbbox()
            if box:boxes.append(box)
    if not boxes:raise s.AppError('VIDEO_EMPTY_FRAMES','영상 후보에 불투명한 픽셀이 없습니다.')
    left=min(b[0] for b in boxes)-8;top=max(0,min(b[1] for b in boxes)-8)
    right=max(b[2] for b in boxes)+8;bottom=max(b[3] for b in boxes)
    scale=body_height/standing_height
    width=max(1,round((right-left)*scale));height=max(1,round((bottom-top)*scale))
    if width*height>16_000_000 or max(width,height)>8192:
        raise s.AppError('VIDEO_SCALE','동작 영역이 너무 큽니다. 목표 몸 높이를 줄이세요.')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    rect=dict(x=left,y=top,width=right-left,height=bottom-top)
    sx=width/(right-left);sy=height/(bottom-top)
    mapping=dict(scaleX=sx,scaleY=sy,offsetX=-left*sx,offsetY=-top*sy)
    anchor=({'x':source_anchor['x']*sx+mapping['offsetX'],'y':source_anchor['y']*sy+mapping['offsetY']}
            if source_anchor else {'x':width/2,'y':height})
    paths=[]
    for output_index,frame in enumerate(frames):
        with Image.open(frame['keyedPath']) as im:
            cropped=im.convert('RGBA').crop((left,top,right,bottom))
            if resize_mode=='color-alpha':
                from .video_processing import _engine
                scaled=_engine('video.loop').resize_cell(cropped,(width,height))
            else:
                scaled=cropped.resize((width,height),Image.Resampling.LANCZOS)
        # The engine's strip composites onto a transparent canvas as well.
        result=Image.new('RGBA',scaled.size);result.alpha_composite(scaled)
        path=directory/f"frame-{frame.get('outputFrameIndex',output_index):04d}.png";result.save(path);paths.append(path)
    recipe=dict(method='video-union-lanczos-v1' if resize_mode=='legacy' else 'video-union-color-alpha-v2.19',sourceRect=rect,sourceToFrameTransform=mapping,
                bodyHeight=body_height,standingSourceHeight=standing_height,bodyScale=scale,
                width=width,height=height,anchor=anchor,anchorMode='first-video-frame' if source_anchor else 'union-bottom-centre',resampler='lanczos' if resize_mode=='legacy' else 'hamming-color-lanczos-alpha',perPoseFit=False)
    s.atomic_bytes(directory/'normalization.json',s.dumps(recipe).encode())
    return paths,recipe
