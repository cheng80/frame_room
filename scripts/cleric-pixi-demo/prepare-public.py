"""Prepare only the cleric demo runtime; keep generation records private."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

DEMO = Path(__file__).resolve().parent


def prepare(source):
    source = source.resolve()
    atlas = json.loads((source / 'cleric-atlas.json').read_text())
    manifest = json.loads((source / 'cleric-manifest.json').read_text())
    assert hashlib.sha256((source / 'cleric-atlas.png').read_bytes()).hexdigest() == manifest['atlasSha256']
    directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    expected = {f'{state}_{direction}' for state in ('walk', 'idle') for direction in directions}
    assert manifest['directions'] == directions
    assert set(atlas['animations']) == set(manifest['animations']) == expected
    assert len(atlas['frames']) == manifest['frameCount'] == 128
    assert atlas['meta']['image'] == 'cleric-atlas.png'
    public = {key: manifest[key] for key in ('character', 'directions', 'camera', 'cell', 'anchor')}
    public['animations'] = {}
    for name, clip in manifest['animations'].items():
        assert clip['frameNames'] == atlas['animations'][name]
        assert len(clip['frameNames']) == len(clip['durationsMs']) == 8
        assert min(clip['durationsMs']) > 0
        assert sum(clip['durationsMs']) == clip['durationMs'] == (1000 if clip['state'] == 'walk' else 3000)
        assert clip['loop'] and name == f"{clip['state']}_{clip['direction']}"
        for key, duration in zip(clip['frameNames'], clip['durationsMs']):
            assert atlas['frames'][key]['duration'] == duration
        public['animations'][name] = {key: clip[key] for key in
            ('frameNames', 'durationsMs', 'durationMs', 'loop', 'direction', 'state')}
    data = json.dumps(public, ensure_ascii=False, indent=2) + '\n'
    assert not any(value in data for value in ('/Users/', 'requestId', 'recordPath', 'sourceVideo', 'selection'))
    out = DEMO / 'dist'
    out.mkdir()  # Refuse to overwrite an earlier package.
    for name in ('index.html', 'main.js', 'controls.js', 'vendor/pixi.min.js', 'vendor/LICENSE.txt'):
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(DEMO / name, target)
    for name in ('cleric-atlas.png', 'cleric-atlas.json'):
        shutil.copy2(source / name, out / name)
    (out / 'cleric-manifest.json').write_text(data)
    (out / '_headers').write_text('/*\n  Cache-Control: no-cache\n  X-Content-Type-Options: nosniff\n')
    assert len([path for path in out.rglob('*') if path.is_file()]) == 9
    print(f'PUBLIC_PACKAGE_PASS {out}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Verified delivery directory')
    prepare(parser.parse_args().source)
