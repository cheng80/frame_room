"""Build a compact 8/12/source-frame viewer from actual app replay outputs."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image
from build_recheck_review import HTML, app_variant, build_data, read_json, data_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    target = root/'walk-8-12.html'
    if target.exists():
        parser.error(f'Existing output preserved: {target}')
    data = build_data(root)
    report = read_json(root/'frame-room/report.json')
    cell = (data['cellWidth'], data['cellHeight'])
    variants = []
    checks = []
    original = read_json(root/'frame-room/default/processing.json')
    source_pngs = {f['sourceFrameIndex']: root/'frame-room/default/final-preview'/f'frame-{i:04d}.png'
                   for i, f in enumerate(original['frames'])}
    for key, label in [('walk-8', '게임용 · 8장'), ('walk-12', '게임용 · 12장'), ('default', '추출 기준 · 24장')]:
        variant, _, _ = app_variant(root, key, label, cell, report, Image)
        bounds = [0]
        for duration in variant['durationsMs']:
            bounds.append(bounds[-1]+duration)
        variant['boundaries'] = [v/bounds[-1] for v in bounds]
        variant['notes'] = '같은 한 사이클 · 1초 유지 · GIF 마무리 · 보간 없음'
        assert variant['durationMs'] == 1000
        assert len(variant['sourceIndices']) == len(set(variant['sourceIndices']))
        assert variant['start'] == 18 and variant['end'] == 42
        for i, source_index in enumerate(variant['sourceIndices']):
            output = root/'frame-room'/key/'final-preview'/f'frame-{i:04d}.png'
            assert Image.open(output).convert('RGBA').tobytes() == Image.open(source_pngs[source_index]).convert('RGBA').tobytes()
        preview = read_json(root/'frame-room'/key/'final-preview/preview.json')
        assert preview['formats']['webp']['fullRGBAParity']
        assert not preview['formats']['gif']['pixelLossDetected']
        checks.append(dict(variant=key, count=len(variant['images']), durationsMs=variant['durationsMs'],
                           sourceIndices=variant['sourceIndices'], durationMs=variant['durationMs'],
                           selectedPixelParity=True, formats=preview['formats']))
        variants.append(variant)
    data.update(variants=variants, modes=[dict(id='game-walk', label='걷기 한 사이클 · 8장 / 12장 / 24장',
        ids=[v['id'] for v in variants], note='장수만 비교합니다. 8장은 기본 후보, 12장은 더 촘촘한 후보입니다. 모두 같은 1초이며 공간 해상도·색상·앵커는 그대로입니다.')],
        provenance='기존 하늘 해적 영상 재사용 · 추가 생성 0회', diagnostic=None, alignment=None,
        optionalNote='24장은 자세 선택용 원본입니다. 게임용 결과는 8장 또는 12장으로 제한하며 첫 자세를 끝에 중복 추가하지 않습니다.')
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    payload = payload.replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    html = HTML.replace('__DATA__', payload).replace('두 번째 실제 영상 비교', '걷기 한 사이클 · 8장과 12장')
    links = []
    for n in [8, 12]:
        path = root/f'frame-room/walk-{n}/final-preview/strip.png'
        links.append(f'<a href="{data_url(path.read_bytes())}" download="walk-{n}-frames.png">{n}장 스프라이트 시트 PNG</a>')
    html = html.replace('<div class="raw">', '<p>'+' · '.join(links)+'</p><div class="raw">')
    target.write_text(html)
    (root/'frame-count-verification.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'viewer': str(target), 'variants': [{k: row[k] for k in ['count','sourceIndices','durationMs','selectedPixelParity']} for row in checks]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
