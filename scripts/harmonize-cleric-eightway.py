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
from adapters.spritegen.video_finish import finish_frames
from adapters.spritegen.video_processing import _write
from scripts.project_library import target_project, publish_delivery

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


def restore_w_blink(source, target, clip):
    record = json.loads((source.parent/'motions/idle_W/complete.json').read_text())
    assert record['sourceSha256'] == clip['sourceVideoSha256'] == '88a84c1dee306d23b3016d6e3899af6cb2e42e16eb3e96d06d90a0aed1f7da81'
    generation = json.loads((source.parent/'motions/idle_W/generation.json').read_text())
    assert sha(Path(generation['path'])) == record['sourceSha256']
    assert clip['sourceFrameIndices'] == [0, 9, 18, 27, 36, 45, 54, 63]
    # shortcut: 39 is closed with less facial droop than 41; review again for another take.
    frame_index, slot = 39, 4
    keyed = Path(record['frames'][0]['keyedPath']).with_name('frame-0040.png')
    assert sha(keyed) == '114189f4f0441e09ca9cf833337bbef839c570812a058aa817ea4a4b2891f471'
    recipe = record['normalization']; rect = recipe['sourceRect']
    crop = Image.open(keyed).convert('RGBA').crop((rect['x'], rect['y'], rect['x']+rect['width'], rect['y']+rect['height']))
    scaled = crop.resize((recipe['width'], recipe['height']), Image.Resampling.LANCZOS)
    normalized = Image.new('RGBA', scaled.size); normalized.alpha_composite(scaled)
    folder = target/'source-resampling/idle_W'; folder.mkdir(parents=True)
    normalized_path = folder/'frame-0039.png'; normalized.save(normalized_path)
    paths, _ = finish_frames([normalized_path], folder/'finished', mode='gif', cell_width=128, cell_height=160, save_metadata=_write)
    cell = Image.new('RGBA', (128, 160))
    anchor = recipe['anchor']; cell.alpha_composite(Image.open(paths[0]).convert('RGBA'), (round(64-anchor['x']), round(148-anchor['y'])))
    previous = clip['sourceFrameIndices'][slot]; clip['sourceFrameIndices'][slot] = frame_index
    boundaries = [round(record['source']['timesMs'][i]) for i in [*clip['sourceFrameIndices'], record['selection']['endFrame']]]
    # A short closure followed by fully open 45 avoids the sleepy-looking hold.
    clip['durationsMs'] = [375, 375, 375, 500, 125, 500, 375, 375]
    assert min(clip['durationsMs']) > 0 and sum(clip['durationsMs']) == clip['durationMs'] == 3000
    correction = {'kind': 'reviewed-closed-eye-source-frame', 'slot': slot, 'previousSourceFrame': previous,
                  'sourceFrame': frame_index, 'sourceTimeMs': record['source']['timesMs'][frame_index],
                  'keyedSha256': sha(keyed), 'normalizedSha256': sha(normalized_path),
                  'sourceSampleBoundariesMs': boundaries, 'playbackDurationsMs': clip['durationsMs'],
                  'retimed': True, 'closedBlinkDurationMs': 125,
                  'sourceVideoSha256': record['sourceSha256'], 'newGeneration': False}
    clip['selection']['samplingCorrection'] = correction
    return cell, correction


def replace_motion(record_path, clip):
    record = json.loads(record_path.read_text())
    assert record['name'] == f"{clip['state']}_{clip['direction']}" and record['baseSha256'] == clip['baseImageSha256']
    assert len(record['frames']) == 8 and record['selection']['loop']
    assert record['selection']['durationMs'] == clip['durationMs']
    checkpoint = Path(record['generationCheckpoint'])
    generation = json.loads((checkpoint.parent/'generation.json').read_text())
    assert sha(Path(generation['path'])) == record['sourceSha256']
    receipt = json.loads(checkpoint.read_text())
    assert receipt['phase'] == 'downloaded' and receipt['postCount'] == 1 and receipt['requestId'] == record['requestId']
    cells = []
    anchor = record['normalization']['anchor']
    for frame in record['frames']:
        cell = Image.new('RGBA', (128, 160))
        cell.alpha_composite(Image.open(frame['path']).convert('RGBA'), (round(64-anchor['x']), round(148-anchor['y'])))
        cells.append(cell)
    clip.update(durationsMs=[f['durationMs'] for f in record['frames']],
                sourceFrameIndices=[f['sourceFrameIndex'] for f in record['frames']],
                sourceVideoSha256=record['sourceSha256'], requestId=record['requestId'], selection=record['selection'])
    assert min(clip['durationsMs']) > 0 and sum(clip['durationsMs']) == clip['durationMs']
    return cells, {'kind': 'Grok-motion-retake', 'recordPath': str(record_path), 'take': record['take'],
                   'sourceVideoSha256': record['sourceSha256'], 'requestId': record['requestId'], 'newGeneration': True}


def run(source, target, idle_s_record=None, walk_e_record=None):
    target_project(source.resolve().parent)
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
                         'pixi-preview.png', 'all-motion-review.png', 'library-publication.json'):
            continue
        if item.is_dir():
            shutil.copytree(item, target/item.name)
        else:
            shutil.copy2(item, target/item.name)
    for name in ('index.html', 'main.js', 'controls.js'):
        shutil.copy2(ROOT/'scripts/cleric-pixi-demo'/name, target/name)
    cells, report = [], {}
    overlay_cells = []
    motion_corrections = {}
    palette = np.array(PALETTE, dtype=np.int32)
    for name, names in atlas['animations'].items():
        direction = manifest['animations'][name]['direction']
        source_cells = []
        for key in names:
            rect = atlas['frames'][key]['frame']
            assert (rect['w'], rect['h']) == (128, 160)
            source_cells.append(image.crop((rect['x'], rect['y'], rect['x']+128, rect['y']+160)))
        if name == 'idle_W':
            source_cells[4], motion_corrections[name] = restore_w_blink(source, target, manifest['animations'][name])
        replacement = idle_s_record if name == 'idle_S' else walk_e_record if name == 'walk_E' else None
        if replacement is not None:
            source_cells, motion_corrections[name] = replace_motion(replacement, manifest['animations'][name])
        if name in motion_corrections:
            for key, duration in zip(names, manifest['animations'][name]['durationsMs']):
                atlas['frames'][key]['duration'] = duration
        hood_columns = (62, 88) if direction == 'NW' else (50, 76)
        head, sole = head_and_sole(source_cells[0], hood_columns)
        # The narrow rear silhouette needs a small visual adjustment after height matching.
        visual_scale = 1.06 if direction == 'N' else 1.0
        target_height = 112 * visual_scale
        factor = target_height/(sole-head)
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
        assert abs(corrected_sole-corrected_head-target_height) <= 1, (name, corrected_head, corrected_sole)
        report[name] = {'hoodColumns': hood_columns, 'sourceHeadY': head, 'sourceSoleY': sole, 'sourceBodyHeight': sole-head,
                        'bodyScale': factor, 'visualScale': visual_scale, 'targetBodyHeight': target_height, 'perPoseFit': False,
                        'correctedFirstBodyHeight': corrected_sole-corrected_head, 'frames': checks}
        write_animation_formats(frames, manifest['animations'][name]['durationsMs'], True, target/'animations'/name)
    data, info = _sheet(cells, 8)
    if data is None:
        raise ValueError(info)
    assert len(cells) == manifest['frameCount'] == 128
    (target/'cleric-atlas.png').write_bytes(data)
    manifest['atlasSha256'] = sha(target/'cleric-atlas.png')
    manifest['harmonization'] = {'sourceAtlasSha256': original_sha, 'bodyHeight': 112,
        'directionVisualScale': {'N': 1.06},
        'bodyMeasurement': 'reviewed hood columns (NW 62:88, others 50:76) to boot bottom; equipment excluded',
        'hairPalette': PALETTE, 'sourceVideosPreserved': True, 'motionCorrections': motion_corrections, 'perPoseFit': False,
        'report': 'harmonization.json'}
    for filename, value in [('cleric-atlas.json', atlas), ('cleric-manifest.json', manifest),
                            ('harmonization.json', {'status': 'passed', 'sourceAtlasSha256': original_sha,
                                'outputAtlasSha256': manifest['atlasSha256'], 'palette': PALETTE,
                                'motionCorrections': motion_corrections,
                                'regions': REGIONS, 'protected': PROTECTED, 'clips': report})]:
        (target/filename).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    for filename, images in [('all-motion-review.png', cells), ('hair-mask-review.png', overlay_cells)]:
        board = Image.new('RGB', (1024, 2560), '#24363a')
        for index, cell in enumerate(images):
            board.paste(cell, (index%8*128, index//8*160), cell)
        board.save(target/filename)
    guide = target/'README.md'
    guide.write_text('# SD 여성 신관 · 크기·머리색 보정본\n\n'
        'GPT 기준 그림·Grok 영상에서 추출한 128프레임을 보정한 결과입니다. '
        + ('일부 동작은 별도 Grok 영상에서 검수한 프레임을 사용합니다. 기준 그림은 보존했습니다.\n\n'
           if idle_s_record is not None or walk_e_record is not None else '새 이미지·영상 생성이나 포즈 합성은 하지 않았습니다.\n\n') +
        '- `cleric-atlas.png`: 투명 PNG, 128×160 셀, 8열×16행.\n'
        '- `cleric-atlas.json`: PixiJS 좌표·16개 동작 목록.\n'
        '- `cleric-manifest.json`: 방향·프레임 시간·원본 영상/기준 그림 해시·보정 출처.\n'
        '- `harmonization.json`: 방향별 몸 높이·고정 배율·머리색 영역·프레임 검증.\n'
        '- `hair-mask-review.png`: 색상 치환 대상만 마젠타로 표시한 검수 자료.\n\n'
        '지팡이를 제외한 후드 상단부터 부츠 하단까지 첫 포즈를 112px 기준으로 맞추고, '
        '폭이 좁아 작게 보이는 N 방향은 걷기·대기 모두 6% 확대했습니다(목표 높이 118.72px). '
        '클립 전체에 같은 배율을 적용했습니다. 발 기준점은 `(64,148)`입니다. '
        '동작 중 발·머리의 움직임은 보존하므로 모든 포즈가 같은 높이는 아닙니다. '
        '캐릭터별로 검수한 영역 안의 금발 주요 색상만 공통 6색으로 맞추고 '
        '어두운 외곽선과 보호한 경계 명암은 유지했습니다. 얼굴·장비·의상은 보호 영역입니다. '
        '이 영역 설정은 다른 캐릭터에 사용할 수 있는 자동 머리 인식기가 아닙니다.\n\n'
        '걷기 1초·8장, 대기 3초·8장과 전체 반복 시간을 유지합니다. '
        'W 대기는 얼굴 처짐이 적은 원본 39번의 감긴 눈을 125ms 표시하고 45번의 뜬 눈으로 돌아옵니다. '
        + ('S 대기의 프레임 선택·재생 시간은 manifest의 selection에 기록합니다. '
           if idle_s_record is not None else '') +
        ('E 걷기는 같은 기준 그림으로 오른손 팔 연결을 유지해 다시 생성한 Grok 영상입니다. '
         if walk_e_record is not None else '') +
        '이전 시트·원본 영상·기준 그림은 상위 `delivery/` 및 원본 폴더에 보존됩니다. '
        '새로 생성된 GPT 원본으로 해석하지 마세요.\n\n'
        '이 폴더에서 `python3 -m http.server 8784 --bind 127.0.0.1`을 실행하고 '
        '`http://127.0.0.1:8784/`를 엽니다. 방향키/WASD로 이동하고 키를 놓으면 대기합니다. '
        'PixiJS 번들과 MIT 라이선스를 포함합니다. 브라우저 검증은 실행 후 별도 기록됩니다.\n')
    assert sha(source/'cleric-atlas.png') == original_sha
    publication = publish_delivery(source.resolve().parent, target)
    print(json.dumps({'status': 'passed', 'source': str(source), 'output': str(target),
                      'frames': len(cells), 'sha256': manifest['atlasSha256'], 'library': publication}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'output/cleric-quarterview-8way/delivery')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--project-id', help='Reuse the source run binding, or bind it explicitly')
    parser.add_argument('--idle-s-record', type=Path, help='Preserved complete.json of the new S idle Grok take')
    parser.add_argument('--walk-e-record', type=Path, help='Preserved complete.json of the right-hand E walk Grok take')
    args = parser.parse_args()
    target_project(args.source.resolve().parent, args.project_id)
    run(args.source, args.out, args.idle_s_record, args.walk_e_record)
