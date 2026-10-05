"""Compare saved pixels around the reported arms. No generation or recoloring."""
import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def read(path):
    return Image.open(path).convert('RGBA')


def measure(raw, keyed, box, point):
    a = np.asarray(raw.crop(box)).astype(int)
    b = np.asarray(keyed.crop(box)).astype(int)
    opaque = b[:, :, 3] == 255
    changed = np.any(a[:, :, :3] != b[:, :, :3], axis=2) & opaque
    # A diagnostic RGB range, not semantic glove/sleeve segmentation.
    warm = (opaque & (a[:, :, 0] >= 80) & (a[:, :, 1] >= 70)
            & (a[:, :, 1] >= a[:, :, 0] * .8)
            & (np.minimum(a[:, :, 0], a[:, :, 1]) - a[:, :, 2] >= 30))
    return dict(roi=list(box), opaquePixels=int(opaque.sum()),
                changedOpaqueRGB=int(changed.sum()), warmRangePixels=int(warm.sum()),
                unchangedWarmRangePixels=int((warm & ~changed).sum()),
                sample=dict(xy=list(point), raw=list(raw.getpixel(point)),
                            keyed=list(keyed.getpixel(point))))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    root = parser.parse_args().root.resolve()
    specs = [
        dict(case='existing', frame=41, start=41, app='frame-room/run-02',
             reference=root.parent/'grok-walk-probe-20261004/input-canvas.png',
             reference_box=(291, 231, 351, 303), box=(322, 245, 382, 317),
             roi=(343, 279, 369, 307), point=(360, 295), label='기존 영상 · 원본 41번 · 빈손 쪽 장갑'),
        dict(case='new', frame=17, start=17, app='frame-room',
             reference=root/'new/video/input-canvas.png',
             reference_box=(279, 231, 339, 303), box=(337, 235, 397, 307),
             roi=(362, 268, 385, 293), point=(374, 278), label='새 영상 · 원본 17번 · 빈손 쪽 장갑'),
    ]
    font = ImageFont.truetype('/System/Library/Fonts/AppleSDGothicNeo.ttc', 22)
    small = ImageFont.truetype('/System/Library/Fonts/AppleSDGothicNeo.ttc', 17)
    sheet = Image.new('RGB', (1230, 770), '#151b24')
    draw = ImageDraw.Draw(sheet)
    draw.text((20, 14), '장갑 색의 출처: 기준 그림 → 원본 영상 → 배경 제거 → 최종 축소', font=font, fill='white')
    draw.text((20, 46), '기준 그림은 다른 자세. 영상 이후는 같은 프레임/부위. 확대 nearest, 색 보정 없음, RIFE 끄기.', font=small, fill='#c2cad5')
    facts = {'scope': 'Two manually selected glove ROIs and one sleeve ROI; not a temporal or semantic color score.', 'gloves': {}}
    for row, s in enumerate(specs):
        raw = read(root/s['case']/'upstream/frames/raw'/f"frame-{s['frame']+1:04d}.png")
        keyed = read(root/s['case']/'upstream/frames/keyed'/f"frame-{s['frame']+1:04d}.png")
        stats = measure(raw, keyed, s['roi'], s['point'])
        facts['gloves'][s['case']] = dict(sourceIndex=s['frame'], **stats)
        app = root/s['case']/s['app']
        norm = json.loads((app/'default/normalized/normalization.json').read_text())
        t = norm['sourceToFrameTransform']
        box = tuple((math.floor if i < 2 else math.ceil)(v * t['scaleX' if i % 2 == 0 else 'scaleY'] + t['offsetX' if i % 2 == 0 else 'offsetY']) for i, v in enumerate(s['box']))
        idx = s['frame']-s['start']
        finished = read(app/'default/finished'/f'frame-{idx:04d}.png')
        up = root/s['case']/'upstream/fixed'
        meta = json.loads((up/'walk.strip.json').read_text())
        latest = read(up/'walk.strip.png').crop((idx*meta['w'], 0, (idx+1)*meta['w'], meta['h']))
        panels = [('기준 그림', read(s['reference']).crop(s['reference_box'])),
                  ('원본 영상', raw.crop(s['box'])), ('배경 제거 · 양쪽 동일', keyed.crop(s['box'])),
                  ('현재 기본 GIF 마무리', finished.crop(box)), ('최신 RGBA', latest.crop(box))]
        top = 90 + row*335
        draw.text((20, top), s['label'], font=font, fill='white')
        for col, (label, im) in enumerate(panels):
            x = 20 + col*242
            draw.text((x, top+34), label, font=small, fill='#c2cad5')
            scale = max(1, min(216//im.width, 218//im.height))
            bg = Image.new('RGBA', im.size, (216, 220, 227, 255))
            bg.alpha_composite(im)
            enlarged = bg.convert('RGB').resize((im.width*scale, im.height*scale), Image.Resampling.NEAREST)
            sheet.paste(enlarged, (x, top+66))
        rgb = stats['sample']['raw'][:3]
        draw.text((20, top+292), f"장갑 실제 픽셀 {tuple(s['point'])}: 원본 RGB {rgb} → 배경 제거 후 동일", font=small, fill='#ead28e')
    raw = read(root/'new/upstream/frames/raw/frame-0026.png')
    keyed = read(root/'new/upstream/frames/keyed/frame-0026.png')
    facts['newSleeve'] = dict(sourceIndex=25, **measure(raw, keyed, (238, 214, 260, 245), (249, 229)))
    sheet.save(root/'arm-color-stages.png')
    (root/'arm-color-check.json').write_text(json.dumps(facts, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(facts, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
