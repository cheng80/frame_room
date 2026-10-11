"""One checkpointed S idle retake; inspect, then finalize eight source frames.

Requires original-hashes.json captured before source inspection; refuses to
generate without that preservation baseline. Never creates a second request.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw
from adapters.spritegen import video_provider as vp, video_processing as processing
from adapters.spritegen.video_normalization import normalize_frames
from adapters.spritegen.video_finish import finish_frames

OUT = ROOT / 'output/cleric-quarterview-8way/idle-S-breathing-v1'
BASE = OUT.parent / 'bases/S/anchor.png'
BASE_SHA = 'd571fcefd95ec576aff6161f99fff7d00c8685fc2e219b8963937f9ce5d77094'
save = processing._write


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def verify_originals():
    assert sha(BASE) == BASE_SHA, 'S anchor changed'
    for path, digest in read(OUT / 'original-hashes.json').items():
        assert sha(path) == digest, f'Original changed: {path}'


def contacts(paths, prefix, crop=None, size=(150, 228), per_page=24, directory=OUT):
    for start in range(0, len(paths), per_page):
        page = paths[start:start + per_page]
        sheet = Image.new('RGB', (size[0] * 6, ((len(page) + 5) // 6) * (size[1] + 22)), '#363a43')
        draw = ImageDraw.Draw(sheet)
        for k, path in enumerate(page):
            with Image.open(path) as source:
                im = source.convert('RGBA')
            if crop:
                im = im.crop(crop)
            im.thumbnail(size, Image.Resampling.NEAREST)
            x, y = k % 6 * size[0], k // 6 * (size[1] + 22)
            sheet.paste(im, (x, y), im)
            draw.text((x + 4, y + size[1] + 3), str(start + k), fill='white')
        sheet.save(directory / f'{prefix}-{start:02d}.png')


def generate():
    verify_originals()
    vp.s.DATA = OUT
    prompt = (
        'Animate this exact female cleric in a 3-second standing idle with clearly visible but restrained '
        'secondary motion throughout, not just an eye blink. One slow breathing cycle: gently lift her '
        'chest and shoulders by about 2 percent of body height during the first half, then relax them '
        'back down during the second half. Her long golden hair tips visibly sway a small distance '
        'outward and inward with a slight delay behind the breathing. The white and gold robe hem '
        'and loose sleeves softly sway and settle, with visibly changing folds. Make these motions '
        'readable at small game sprite size while keeping the exact design and proportions. '
        'Both boots remain firmly planted at their original screen positions at all times; no stepping, '
        'shuffling, sliding, foot lifting, jumping, travelling or turning. One brief fully closed blink '
        'around 1.5 seconds, reopen promptly. Her own RIGHT hand keeps the same golden staff grip, '
        'elbow connection and equipment placement; no hand swap, no new gear. Staff stays nearly still, '
        'orb solid unlit gold. Same elevated orthographic quarter-view S front camera as the input, '
        'looking down 30 degrees, locked camera and constant scale. No glow, effects, particles, '
        'shadows or floor. Flat solid bright magenta #FF00FF background in every frame. '
        'Return naturally to the exact starting pose at 3 seconds for a smooth loop.'
    )
    params = vp.validate_params(dict(state='idle', direction='front', facing='right',
        bodyPlan='biped', equipment='staff:right', model='grok-imagine-video-1.5',
        durationSeconds=3, resolution='480p', maxFrames=8, bodyHeight=112,
        cellWidth=128, cellHeight=160, finishMode='gif', repairMode='off',
        between='off', key='magenta', motionPrompt=prompt), generation=True)
    request = OUT / 'request.json'
    if request.exists():
        assert read(request) == params, 'Saved request differs; do not submit again'
    else:
        save(request, params)
    digest = hashlib.sha256((json.dumps(params, sort_keys=True) + BASE_SHA).encode()).hexdigest()
    result = vp.generate(BASE, OUT / 'provider', params, OUT / 'checkpoint.json', digest,
        credential=vp.login_credential(),
        on_progress=lambda stage, message: print(stage, message, flush=True))
    save(OUT / 'generation.json', {**result, 'path': str(result['path'])})
    assert read(OUT / 'checkpoint.json')['postCount'] == 1
    if (OUT / 'processed.json').exists():
        processed = read(OUT / 'processed.json')
        assert processed['sourceSha256'] == sha(result['path'])
    else:
        processed = processing.process_clip(result['path'], OUT / 'processing',
            {**params, 'loopMode': 'manual', 'startFrame': 0, 'endFrame': 72,
             'referencePath': str(OUT / 'provider/input-canvas.png')})
        save(OUT / 'processed.json', processed)
    assert processed['source']['fps'] == 24
    assert processed['selection']['durationMs'] == 3000
    keyed = sorted(Path(processed['extraction']['keyedDir']).glob('frame-*.png'))
    raw = sorted(Path(processed['extraction']['rawDir']).glob('frame-*.png'))
    boxes = [Image.open(p).getchannel('A').getbbox() for p in keyed]
    crop = (min(b[0] for b in boxes)-6, min(b[1] for b in boxes)-6,
            max(b[2] for b in boxes)+6, max(b[3] for b in boxes)+6)
    contacts(keyed, 'new-keyed', crop)
    contacts(raw, 'new-raw', size=(180, 180))
    verify_originals()
    print('INSPECTION_READY', str(OUT / 'processed.json'), flush=True)


def finalize(indices, closed, directory=OUT, durations=None):
    verify_originals()
    assert len(indices) == 8 and indices == sorted(set(indices))
    assert indices[0] == 0 and indices[-1] < 72
    assert closed and set(closed) & set(indices), 'Include a visually verified closed blink'
    processed, result = read(OUT / 'processed.json'), read(OUT / 'generation.json')
    raw = sorted(Path(processed['extraction']['rawDir']).glob('frame-*.png'))
    keyed = sorted(Path(processed['extraction']['keyedDir']).glob('frame-*.png'))
    times = processed['source']['timesMs']
    boundaries = [processing._round(times[i]) for i in [*indices, 72]]
    if durations is not None:
        assert len(durations) == len(indices) and min(durations) > 0 and sum(durations) == 3000
    directory.mkdir(parents=True, exist_ok=True)
    frames = [dict(rawPath=str(raw[i]), keyedPath=str(keyed[i]), originalKeyedPath=str(keyed[i]),
        sourceFrameIndex=i, outputFrameIndex=k, sourceTimeMs=times[i],
        durationMs=durations[k] if durations is not None else boundaries[k+1]-boundaries[k], interpolated=False,
        processing={'kind': 'chroma-key', 'sourceCoordinateSpace': 'decoded-video-canvas',
                    'coordinateSpace': 'decoded-video-canvas'}) for k, i in enumerate(indices)]
    assert all(f['durationMs'] > 0 for f in frames)
    assert sum(f['durationMs'] for f in frames) == 3000
    paths, normalization = normalize_frames(frames, processed['standingHeight'], 112,
        directory / 'normalized', bounds_paths=keyed[:72], source_anchor=processed['anchor'])
    paths, finish = finish_frames(paths, directory / 'finished', mode='gif', cell_width=128, cell_height=160)
    for frame, path in zip(frames, paths):
        frame['path'] = str(path)
        with Image.open(path) as image:
            assert image.getchannel('A').getbbox()
            assert image.width <= 128 and image.height <= 160
    selection = {**processed['selection'], 'sampledFrameCount': 8, 'durationMs': 3000,
        'sourceDurationMs': 3000, 'sourceFrameCount': 72,
        'manualSourceFrameIndices': indices, 'closedBlinkSourceFrameIndices': closed,
        'sampleBoundariesMs': boundaries, 'sampling': 'visually-reviewed-source-boundaries'}
    if durations is not None:
        selection.update(sampling='reviewed-low-motion-source-frames-retimed',
            playbackDurationsMs=durations, sourceSampleBoundariesMs=selection.pop('sampleBoundariesMs'))
    record = dict(name='idle_S', direction='S', state='idle',
        sourceSha256=sha(result['path']), baseSha256=sha(BASE), requestId=result['receipt']['requestId'],
        frames=frames, normalization=normalization, finish=finish, selection=selection,
        source=processed['source'], processingReport=processed['files'],
        generationCheckpoint=str(OUT / 'checkpoint.json'), take='quiet-selection' if durations is not None else 'breathing-v1',
        sourceVideoPath=result['path'], processingRoot=str(OUT / 'processing'))
    save(directory / 'complete.json', record)
    preview = processing._preview(frames, directory, True)
    save(directory / 'selected-preview.json', preview)
    contacts(paths, 'finished', size=(216, 345), directory=directory)
    verify_originals()
    print('COMPLETE', str(directory / 'complete.json'), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['generate', 'finalize', 'quieten'])
    parser.add_argument('--indices', type=lambda s: [int(i) for i in s.split(',')])
    parser.add_argument('--closed', type=lambda s: [int(i) for i in s.split(',')])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    vp.s.DATA = OUT
    if args.stage == 'generate':
        generate()
    elif args.stage == 'quieten':
        directory = OUT / 'quiet-selection'
        assert not directory.exists(), 'Keep the previous selection'
        # Reviewed low-sway phases skip the three flares; retiming keeps the blink brief.
        finalize([0, 18, 20, 35, 38, 51, 54, 63], [38], directory,
                 [375, 375, 375, 500, 167, 458, 375, 375])
    else:
        assert args.indices is not None and args.closed is not None
        finalize(args.indices, args.closed)
