"""Local correction of the delivered cleric; never generate or overwrite sources.

The polygons are reviewed annotations for this character, not a hair detector.
"""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from alignment.pipeline import _engine
from alignment.animation_exports import _sheet, write_animation_formats

PALETTE = [(176, 121, 67), (201, 148, 82), (228, 178, 108),
           (244, 200, 130), (255, 224, 162), (255, 240, 192)]
# shortcut: masks fit this cleric only; annotate again when the source character changes.
REGIONS = {
    'N': [[(46, 80), (68, 76), (79, 84), (81, 101), (49, 105), (43, 90)]],
    'NE': [[(69, 40), (78, 41), (82, 60), (72, 66)],
           [(39, 83), (69, 72), (76, 82), (73, 101), (68, 109), (44, 108), (35, 98)]],
    'E': [[(59, 47), (75, 47), (81, 60), (78, 65), (65, 67), (57, 60)],
          [(48, 68), (64, 64), (66, 77), (61, 90), (60, 103), (37, 101), (35, 90)],
          [(70, 75), (75, 76), (75, 88), (70, 87), (67, 81)]],
    'SE': [[(59, 47), (75, 47), (81, 60), (78, 65), (65, 67), (57, 60)],
           [(48, 68), (64, 64), (65, 78), (61, 89), (61, 99), (39, 99), (35, 90)]],
    'S': [[(48, 57), (80, 57), (81, 65), (47, 65)],
          [(43, 67), (51, 67), (54, 85), (46, 96), (38, 92), (39, 79)],
          [(76, 67), (87, 72), (98, 86), (95, 98), (84, 97), (76, 83)]],
    'NW': [[(50, 57), (61, 57), (63, 74), (50, 75)],
           [(67, 89), (83, 89), (89, 97), (90, 105), (84, 109), (70, 107), (66, 100)]],
}
PROTECTED = {
    'N': [(42, 71, 84, 83), (42, 100, 85, 119), (73, 80, 89, 95), (35, 80, 52, 95)],
    'NE': [(58, 50, 69, 69), (68, 61, 83, 81), (58, 78, 127, 159), (74, 0, 127, 159),
           (58, 103, 85, 122), (35, 69, 67, 84)],
    'E': [(51, 47, 63, 67), (65, 62, 87, 83), (52, 77, 74, 95),
          (39, 101, 62, 115), (35, 69, 61, 82), (35, 88, 52, 119),
          (52, 80, 80, 120), (56, 61, 87, 84)],
    'SE': [(52, 47, 64, 66), (63, 62, 83, 84), (54, 77, 74, 92),
           (70, 34, 100, 68), (35, 69, 61, 82), (48, 82, 85, 115), (56, 61, 87, 84)],
    'S': [(40, 54, 50, 70), (77, 54, 89, 70), (52, 63, 78, 85),
          (38, 95, 53, 110), (80, 97, 99, 113), (43, 80, 58, 110), (76, 80, 92, 110)],
    'NW': [(60, 67, 76, 83), (48, 72, 65, 85), (60, 78, 90, 89), (61, 106, 93, 123)],
}
for direction, source in [('W', 'E'), ('SW', 'SE')]:
    REGIONS[direction] = [[(128-x, y) for x, y in polygon] for polygon in REGIONS[source]]
    PROTECTED[direction] = [(128-r, t, 128-l, b) for l, t, r, b in PROTECTED[source]]
for direction, rectangle in {'NE': (82, 0, 127, 159), 'SE': (78, 0, 127, 159),
                             'S': (0, 0, 45, 159), 'SW': (0, 0, 47, 159),
                             'W': (0, 0, 47, 159), 'NW': (0, 0, 53, 159)}.items():
    PROTECTED[direction].append(rectangle)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def head_and_sole(cell, columns=(50, 76)):
    alpha = np.array(cell)[..., 3] > 128
    # Reviewed hood columns exclude the staff in all eight source directions.
    rows = np.flatnonzero(alpha[:, columns[0]:columns[1]].any(axis=1))
    if not len(rows):
        raise ValueError('Missing hood/body in annotated columns')
    return int(rows[0]), int(np.flatnonzero(alpha.any(axis=1))[-1])+1


def hair_mask(cell, direction, vertical_shift):
    area = Image.new('L', cell.size)
    draw = ImageDraw.Draw(area)
    for polygon in REGIONS[direction]:
        draw.polygon([(x, y+vertical_shift) for x, y in polygon], fill=255)
    for left, top, right, bottom in PROTECTED[direction]:
        draw.rectangle((left, top+vertical_shift, right, bottom+vertical_shift), fill=0)
    arr = np.array(cell)
    rgb = arr[..., :3].astype(np.int32)
    red, green, blue = (rgb[..., index] for index in range(3))
    # Warm blonde clusters; skin pinks, veil whites and dark outlines pass through.
    blonde = ((red >= 150) & (red > green) & (green > blue) &
              (red-blue >= 45) & (green-blue >= 27) &
              (2*(green-blue) >= red-green) & (arr[..., 3] > 128))
    return (np.array(area) > 0) & blonde


def run(source, target):
    source, target = source.resolve(), target.resolve()
    if target == source or target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError('Use a separate sibling output directory')
    if target.exists():
        raise ValueError('Output already exists; keep it and choose another directory')
    atlas = json.loads((source/'cleric-atlas.json').read_text())
    manifest = json.loads((source/'cleric-manifest.json').read_text())
    original_sha = sha(source/'cleric-atlas.png')
    assert original_sha == manifest['atlasSha256']
    image = Image.open(source/'cleric-atlas.png').convert('RGBA')
    engine = _engine('effects.recolor')
    target.mkdir(parents=True)
    for item in source.iterdir():
        if item.name in ('animations', 'cleric-atlas.png', 'cleric-atlas.json', 'cleric-manifest.json',
                         'verification.json', 'browser-verification.json', 'visual-review.json',
                         'pixi-preview.png', 'all-motion-review.png'):
            continue
        if item.is_dir():
            shutil.copytree(item, target/item.name)
        else:
            shutil.copy2(item, target/item.name)
    cells, report = [], {}
    overlay_cells = []
    palette = np.array(PALETTE, dtype=np.int32)
    for name, names in atlas['animations'].items():
        direction = manifest['animations'][name]['direction']
        source_cells = []
        for key in names:
            rect = atlas['frames'][key]['frame']
            assert (rect['w'], rect['h']) == (128, 160)
            source_cells.append(image.crop((rect['x'], rect['y'], rect['x']+128, rect['y']+160)))
        hood_columns = (62, 88) if direction == 'NW' else (50, 76)
        head, sole = head_and_sole(source_cells[0], hood_columns)
        factor = 112/(sole-head)
        frames, checks = [], []
        for index, cell in enumerate(source_cells):
            current_head, _ = head_and_sole(cell, hood_columns)
            mask = hair_mask(cell, direction, current_head-head)
            arr = np.array(cell)
            colors = np.unique(arr[mask, :3], axis=0).astype(np.int32)
            if not len(colors):
                raise ValueError(f'{name}/{index}: no hair colors in reviewed region')
            closest = ((colors[:, None, :]-palette[None, :, :])**2).sum(axis=2).argmin(axis=1)
            pairs = [(tuple(map(int, color)), PALETTE[int(level)]) for color, level in zip(colors, closest)]
            corrected, substitutions, covered = engine._bake_variant_exact(arr, mask, pairs)
            assert np.array_equal(arr[..., 3], corrected[..., 3])
            assert np.array_equal(arr[~mask], corrected[~mask])
            assert np.array_equal(covered, mask)
            assert set(map(tuple, corrected[mask, :3])).issubset(set(PALETTE))
            overlay = arr.copy(); overlay[mask, :3] = [255, 0, 200]
            overlay_cells.append(Image.fromarray(overlay))
            # One scale for the entire clip, around the existing common foot anchor.
            frame = Image.fromarray(corrected).transform((128, 160), Image.Transform.AFFINE,
                (1/factor, 0, 64-64/factor, 0, 1/factor, 148-148/factor), Image.Resampling.NEAREST)
            box = frame.getchannel('A').getbbox()
            if not box or min(box[0], box[1], 128-box[2], 160-box[3]) < 4:
                raise ValueError(f'{name}/{index}: corrected frame exceeds safe cell margin')
            frames.append(frame); cells.append(frame)
            checks.append({'changedHairPixels': int(np.any(arr != corrected, axis=2).sum()),
                           'maskPixels': int(mask.sum()), 'outsideMaskUnchanged': True,
                           'alphaPreservedByPalette': True, 'minimumMarginPx': min(box[0], box[1], 128-box[2], 160-box[3])})
        columns = tuple(round(64+(x-64)*factor) for x in hood_columns)
        corrected_head, corrected_sole = head_and_sole(frames[0], columns)
        assert abs(corrected_sole-corrected_head-112) <= 1, (name, corrected_head, corrected_sole)
        report[name] = {'hoodColumns': hood_columns, 'sourceHeadY': head, 'sourceSoleY': sole, 'sourceBodyHeight': sole-head,
                        'bodyScale': factor, 'perPoseFit': False,
                        'correctedFirstBodyHeight': corrected_sole-corrected_head, 'frames': checks}
        write_animation_formats(frames, manifest['animations'][name]['durationsMs'], True, target/'animations'/name)
    data, info = _sheet(cells, 8)
    if data is None:
        raise ValueError(info)
    assert len(cells) == manifest['frameCount'] == 128
    (target/'cleric-atlas.png').write_bytes(data)
    manifest['atlasSha256'] = sha(target/'cleric-atlas.png')
    manifest['harmonization'] = {'sourceAtlasSha256': original_sha, 'bodyHeight': 112,
        'bodyMeasurement': 'reviewed hood columns (NW 62:88, others 50:76) to boot bottom; equipment excluded',
        'hairPalette': PALETTE, 'sourceMotionUnchanged': True, 'perPoseFit': False,
        'report': 'harmonization.json'}
    for filename, value in [('cleric-atlas.json', atlas), ('cleric-manifest.json', manifest),
                            ('harmonization.json', {'status': 'passed', 'sourceAtlasSha256': original_sha,
                                'outputAtlasSha256': manifest['atlasSha256'], 'palette': PALETTE,
                                'regions': REGIONS, 'protected': PROTECTED, 'clips': report})]:
        (target/filename).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    for filename, images in [('all-motion-review.png', cells), ('hair-mask-review.png', overlay_cells)]:
        board = Image.new('RGB', (1024, 2560), '#24363a')
        for index, cell in enumerate(images):
            board.paste(cell, (index%8*128, index//8*160), cell)
        board.save(target/filename)
    guide = target/'README.md'
    guide.write_text('# SD 여성 신관 · 크기·머리색 보정본\n\n'
        '기존 GPT 기준 그림·Grok 영상에서 추출한 128프레임을 로컬에서 보정한 결과입니다. '
        '새 이미지·영상 생성이나 포즈 합성은 하지 않았습니다.\n\n'
        '- `cleric-atlas.png`: 투명 PNG, 128×160 셀, 8열×16행.\n'
        '- `cleric-atlas.json`: PixiJS 좌표·16개 동작 목록.\n'
        '- `cleric-manifest.json`: 방향·프레임 시간·원본 영상/기준 그림 해시·보정 출처.\n'
        '- `harmonization.json`: 방향별 몸 높이·고정 배율·머리색 영역·프레임 검증.\n'
        '- `hair-mask-review.png`: 색상 치환 대상만 마젠타로 표시한 검수 자료.\n\n'
        '지팡이를 제외한 후드 상단부터 부츠 하단까지 첫 포즈를 112px로 맞추고, '
        '클립 전체에 같은 배율을 적용했습니다. 발 기준점은 `(64,148)`입니다. '
        '동작 중 발·머리의 움직임은 보존하므로 모든 포즈가 같은 높이는 아닙니다. '
        '캐릭터별로 검수한 영역 안의 금발 주요 색상만 공통 6색으로 맞추고 '
        '어두운 외곽선과 보호한 경계 명암은 유지했습니다. 얼굴·장비·의상은 보호 영역입니다. '
        '이 영역 설정은 다른 캐릭터에 사용할 수 있는 자동 머리 인식기가 아닙니다.\n\n'
        '기존 동작의 순서·시간을 그대로 사용합니다: 걷기 1초·8장, 대기 3초·8장. '
        '이전 시트·원본 영상·기준 그림은 상위 `delivery/` 및 원본 폴더에 보존됩니다. '
        '새로 생성된 GPT 원본으로 해석하지 마세요.\n\n'
        '이 폴더에서 `python3 -m http.server 8782 --bind 127.0.0.1`을 실행하고 '
        '`http://127.0.0.1:8782/`를 엽니다. 방향키/WASD로 이동하고 키를 놓으면 대기합니다. '
        'PixiJS 번들과 MIT 라이선스를 포함합니다. 브라우저 검증은 실행 후 별도 기록됩니다.\n')
    assert sha(source/'cleric-atlas.png') == original_sha
    print(json.dumps({'status': 'passed', 'source': str(source), 'output': str(target),
                      'frames': len(cells), 'sha256': manifest['atlasSha256']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'output/cleric-quarterview-8way/delivery')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.out)
