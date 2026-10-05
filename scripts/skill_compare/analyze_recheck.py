"""Measure the second saved comparison, including strict WebP and shared RIFE.

No generation. Requires the two engines' outputs; does not write product data.
"""
import argparse
import io
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def read(path):
    return json.loads(path.read_text())


def images(directory):
    return [Image.open(p).convert('RGBA') for p in sorted(directory.glob('frame-*.png'))]


def cells(directory):
    meta = read(directory/'walk.strip.json')
    sheet = Image.open(directory/'walk.strip.png').convert('RGBA')
    return [sheet.crop((i*meta['w'], 0, (i+1)*meta['w'], meta['h'])) for i in range(meta['frames'])]


def difference(a, b):
    changed = foreground = 0
    assert len(a) == len(b)
    for left, right in zip(a, b, strict=True):
        assert left.size == right.size
        x, y = np.asarray(left), np.asarray(right)
        fg = (x[..., 3] > 0) | (y[..., 3] > 0)
        changed += int((np.any(x != y, axis=2) & fg).sum())
        foreground += int(fg.sum())
    return dict(changedForegroundPixels=changed, foregroundPixels=foreground,
                equalForegroundFraction=1-changed/max(1, foreground))


def contact(root, series, indices, title, name):
    font = ImageFont.truetype('/System/Library/Fonts/AppleSDGothicNeo.ttc', 22)
    small = ImageFont.truetype('/System/Library/Fonts/AppleSDGothicNeo.ttc', 17)
    zoom, column, row_height = 3, 256, 344
    sheet = Image.new('RGB', (column*len(series)+20, 82+row_height*len(indices)), '#151b24')
    draw = ImageDraw.Draw(sheet)
    draw.text((20, 12), title, font=font, fill='white')
    draw.text((20, 44), '실제 PNG · nearest 3배 확대 · 추가 블러/샤프닝 없음 · 공통 마무리는 실험 조합', font=small, fill='#c2cad5')
    for row, index in enumerate(indices):
        top = 82+row*row_height
        for col, (label, frames) in enumerate(series.items()):
            x = 20+col*column
            draw.text((x, top), f'{label} · {index}', font=small, fill='white')
            im = frames[index]
            bg = Image.new('RGBA', im.size, (216, 220, 227, 255))
            bg.alpha_composite(im)
            sheet.paste(bg.convert('RGB').resize((im.width*zoom, im.height*zoom), Image.Resampling.NEAREST), (x, top+30))
    sheet.save(root/'analysis'/name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('--latest-engine', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    out = root/'analysis'
    out.mkdir(exist_ok=True)
    proc = read(root/'frame-room/default/processing.json')
    results = {'scope': 'Saved third clip; comparison only, no product modifications.'}
    keyed_old = images(Path(proc['extraction']['keyedDir']))
    keyed_new = images(root/'upstream/frames/keyed')
    assert len(keyed_old) == len(keyed_new) == 73
    results['keyed'] = dict(frames=73, allRGBAEqual=all(a.tobytes() == b.tobytes() for a, b in zip(keyed_old, keyed_new, strict=True)))
    source_series = {
        '현재 기본': images(root/'frame-room/default/finished'),
        '현재 RGBA': images(root/'frame-room/rgba/finished'),
        '최신 RGBA': cells(root/'upstream/fixed'),
        '최신 + 현재 마무리': images(out/'common-finish/latest-fixed/finished'),
    }
    results['finish'] = {}
    for label, frames in source_series.items():
        partial = sum(int(((a[..., 3] > 0) & (a[..., 3] < 255)).sum()) for a in map(np.asarray, frames))
        results['finish'][label] = dict(frames=len(frames), meanPartialAlphaPixels=partial/len(frames))
    results['rgbaDifferenceNativeCrop'] = difference(source_series['현재 RGBA'], source_series['최신 RGBA'])
    results['rgbaDifferenceNativeCrop']['qualification'] = 'Latest speck removal shifts the left crop boundary by 2 source pixels, changing the resize grid. Not a quality score.'
    results['rgbaDifferenceMatchedBounds'] = difference(source_series['현재 RGBA'], images(out/'common-finish/latest-fixed-matched-rgba/finished'))
    results['sameFinishDifference'] = difference(source_series['현재 기본'], source_series['최신 + 현재 마무리'])
    contact(root, source_series, [0, 6, 12], '하늘 해적 · 같은 구간, 같은 자세 비교 (원본 시작 18)', 'contact.png')

    from alignment.animation_exports import _verify_animation
    results['webp'] = {}
    for mode in ['rgba', 'repaired']:
        folder = root/'frame-room'/mode/'final-preview'
        paths = sorted(folder.glob('frame-*.png'))
        frames = images(folder)
        timing = [f['durationMs'] for f in read(root/'frame-room'/mode/'processing.json')['frames']]
        stream = io.BytesIO()
        frames[0].save(stream, 'WEBP', save_all=True, append_images=frames[1:], duration=timing,
                       loop=0, lossless=True, quality=100, method=4, exact=True,
                       background=(0, 0, 0, 0), allow_mixed=False)
        encoded = Image.open(io.BytesIO(stream.getvalue()))
        assert encoded.n_frames == len(frames)
        counts = dict(visibleRGB=0, alpha=0, hiddenRGB=0)
        for index, frame in enumerate(frames):
            encoded.seek(index); encoded.load()
            assert encoded.info['duration'] == timing[index]
            a, b = np.asarray(frame), np.asarray(encoded.convert('RGBA'))
            rgb = np.any(a[..., :3] != b[..., :3], axis=2)
            counts['visibleRGB'] += int((rgb & (a[..., 3] > 0)).sum())
            counts['hiddenRGB'] += int((rgb & (a[..., 3] == 0)).sum())
            counts['alpha'] += int((a[..., 3] != b[..., 3]).sum())
        target = out/f'{mode}-exact-diagnostic.webp'
        command = ['img2webp', '-loop', '0', '-lossless', '-exact']
        for path, duration in zip(paths, timing, strict=True):
            command += ['-d', str(duration), str(path)]
        command += ['-o', str(target)]
        subprocess.run(command, check=True, capture_output=True)
        exact = _verify_animation(target.read_bytes(), frames, timing, True, 'WEBP')
        results['webp'][mode] = dict(pillowChangedPixels=counts, sameTime=True, exactDiagnostic=exact)

    sys.path.insert(0, str(args.latest_engine.resolve()))
    from sprite_gen.video import rife, align
    original = images(root/'upstream/fixed/cycle')
    results['sharedRife'] = {}
    shared_inputs = []
    for name in ['frame-room', 'upstream']:
        folder = root/'shared-rife'/name
        record = read(folder/'resample.json')
        shared_inputs.append((record['inputSha256'], record['interpolator']))
        frames = images(folder)
        per_frame = []
        for k, frame in enumerate(frames):
            position = k*len(original)/len(frames)
            i = int(position); fraction = position-i
            if fraction == 0:
                continue
            measure = rife.smear(frame, original[i], original[(i+1) % len(original)])
            per_frame.append(dict(index=k, **measure, faults=align.faults(measure)))
        facts = record['facts']
        holds = [i for i in range(len(frames)) if frames[i].tobytes() == frames[(i+1) % len(frames)].tobytes()]
        results['sharedRife'][name] = dict(made=facts['made_by_rife'], fallback=len(facts.get('nearest_at', [])),
            nearestAt=facts.get('nearest_at', []), flagged=sum(bool(f['faults']) for f in per_frame),
            maxDarkExcess=max(f['dark_excess'] for f in per_frame),
            exactDuplicateAdjacentPairs=holds, measuredWithLatestHeuristic=per_frame)
    assert shared_inputs[0] == shared_inputs[1], 'Input frames or RIFE binary/model differ'
    old_measures = results['sharedRife']['frame-room']['measuredWithLatestHeuristic']
    worst = sorted(old_measures, key=lambda x: x['dark_excess'], reverse=True)[:3]
    indices = [v['index'] for v in worst]
    contact(root, {
        '현재 RIFE · RGBA': cells(root/'shared-rife/frame-room'),
        '최신 RIFE · RGBA': cells(root/'shared-rife/upstream'),
        '현재 RIFE · GIF 마무리': images(out/'common-finish/rife-current/finished'),
        '최신 RIFE · GIF 마무리': images(out/'common-finish/rife-latest/finished'),
    }, indices, '동일 24장 → 32장 · 원본 시간 1초 유지 · 검은 번짐 진단 상위 슬롯', 'rife-contact.png')
    results['sharedRife']['qualification'] = 'Same latest heuristic used to remeasure both outputs. Not independent visual proof. Duplicate adjacent pairs include wrap.'
    (out/'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:v for k,v in results.items() if k not in ['sharedRife','webp']}, ensure_ascii=False))
    print(json.dumps({name:{k:v for k,v in d.items() if k!='measuredWithLatestHeuristic'} for name,d in results['sharedRife'].items() if isinstance(d,dict)},ensure_ascii=False))
    print(json.dumps({name:d['pillowChangedPixels'] for name,d in results['webp'].items()}))


if __name__ == '__main__':
    main()
