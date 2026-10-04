"""Regression: prepare can choose cyan, so imported rows must key it too."""
from PIL import Image,ImageDraw
import pytest
from sprite_gen.frames.cutout import cutout

@pytest.mark.parametrize('key',['auto','cyan'])
@pytest.mark.parametrize('background',[(0,255,255),(6,249,252)])
def test_cyan_generated_row_routes_to_chroma(tmp_path,key,background):
    source=tmp_path/'source.png';target=tmp_path/'alpha.png'
    image=Image.new('RGB',(64,64),background)
    ImageDraw.Draw(image).rectangle((18,10,45,54),fill=(95,52,28));image.save(source)
    report=cutout(source,target,key=key)
    result=Image.open(target).convert('RGBA')
    assert report['route']=='extract:cyan'
    assert result.getpixel((0,0))==(0,0,0,0)
    assert result.getpixel((30,30))==(95,52,28,255)
    assert report['alpha_zero_pct']>0
