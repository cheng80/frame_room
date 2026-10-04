"""Video sampling regression; synthetic pixels are not generated art."""
from pathlib import Path
from PIL import Image,ImageDraw
import pytest
from services.api import store as s
from adapters.spritegen.video_normalization import normalize_frames
from adapters.spritegen.video_processing import _engine

@pytest.fixture(autouse=True)
def local_storage(tmp_path,monkeypatch):
    monkeypatch.setattr(s,'DATA',tmp_path)


def test_common_video_scale_matches_color_alpha_engine_and_preserves_sources(tmp_path):
    frames=[];images=[];originals={}
    for i in range(4):
        im=Image.new('RGBA',(128,160))
        draw=ImageDraw.Draw(im)
        draw.rectangle((35,30+i*3,78,129),fill=(90,70,50,255))
        # Small, brightly tinted video pixels must be filtered during reduction.
        draw.line((25+i*8,65,65,132),fill=(200,210,210,255),width=4)
        im.putpixel((25+i*8,65),(50,220,20,255))
        path=tmp_path/f'input-{i}.png';im.save(path);originals[path]=path.read_bytes()
        frames.append({'keyedPath':str(path),'sourceFrameIndex':i});images.append(im)
    paths,recipe=normalize_frames(frames,100,32,tmp_path/'normalized',resize_mode='color-alpha')
    strip,meta=_engine('video.loop').build_strip(images,max_height=1024,max_width=8192,max_cells=4,cycle_seconds=1,body_height=32,standing_src=100,anchor='none')
    assert recipe['bodyScale']==.32 and recipe['perPoseFit'] is False
    assert (recipe['width'],recipe['height'])==(meta['w'],meta['h'])
    for i,path in enumerate(paths):
        image=Image.open(path).convert('RGBA')
        assert image.tobytes()==strip.crop((i*meta['w'],0,(i+1)*meta['w'],meta['h'])).tobytes()
    assert originals=={path:path.read_bytes() for path in originals}
    box=recipe['sourceRect'];mapping=recipe['sourceToFrameTransform']
    assert mapping['offsetX']==-box['x']*mapping['scaleX']
    assert mapping['offsetY']==-box['y']*mapping['scaleY']
    assert (tmp_path/'normalized/normalization.json').is_file()
    subset,subset_recipe=normalize_frames(frames[::2],100,32,tmp_path/'subset',bounds_paths=[f['keyedPath'] for f in frames],resize_mode='color-alpha')
    assert subset_recipe==recipe
    assert all(Image.open(path).tobytes()==Image.open(paths[i*2]).tobytes() for i,path in enumerate(subset))


def test_motion_excursion_does_not_shrink_body_to_requested_cell(tmp_path):
    frames=[]
    for i,y in enumerate((10,210)):
        im=Image.new('RGBA',(128,400));ImageDraw.Draw(im).rectangle((40,y,70,y+99),fill=(70,90,110,255))
        path=tmp_path/f'{i}.png';im.save(path);frames.append({'keyedPath':str(path),'sourceFrameIndex':i})
    _,recipe=normalize_frames(frames,100,94,tmp_path/'normalized')
    assert recipe['bodyScale']==.94
    assert recipe['height']>128  # The editor reports overflow; no silent per-state fit.


def test_first_frame_anchor_survives_different_motion_windows(tmp_path):
    frames=[]
    for i,x in enumerate((35,10)):
        im=Image.new('RGBA',(128,160));ImageDraw.Draw(im).rectangle((x,30,78,129),fill=(90,70,50,255))
        path=tmp_path/f'{i}.png';im.save(path);frames.append({'keyedPath':str(path),'sourceFrameIndex':i})
    source={'x':56.5,'y':130}
    for i,selected in enumerate((frames[:1],frames)):
        _,recipe=normalize_frames(selected,100,32,tmp_path/f'normalized-{i}',source_anchor=source)
        m=recipe['sourceToFrameTransform'];a=recipe['anchor']
        assert (a['x']-m['offsetX'])/m['scaleX']==pytest.approx(source['x'])
        assert (a['y']-m['offsetY'])/m['scaleY']==pytest.approx(source['y'])
        assert recipe['anchorMode']=='first-video-frame'
