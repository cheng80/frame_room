"""One checkpointed E walk retake from the preserved GPT anchor; review before release."""
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

OUT = ROOT / 'output/cleric-quarterview-8way/walk-E-right-hand-v1'
BASE = OUT.parent / 'bases/E/anchor.png'
BASE_SHA = '8075d10156a49ddc0ebb40d0f00fcb677b118e07f4f546c13685510875570f50'
save = processing._write


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def verify_originals():
    assert sha(BASE) == BASE_SHA, 'E anchor changed'
    baseline = OUT / 'original-hashes.json'
    if not baseline.exists():
        assert not (OUT / 'checkpoint.json').exists(), 'Missing preservation baseline'
        paths = sorted(p for name in ('bases', 'motions', 'source')
                       for p in (OUT.parent / name).rglob('*') if p.is_file())
        assert len(paths) >= 514
        save(baseline, {str(p): sha(p) for p in paths})
    originals = read(baseline)
    for path, digest in originals.items():
        assert sha(path) == digest, f'Original changed: {path}'
    return len(originals)


def contacts(paths, prefix, crop=None, per_page=24):
    for start in range(0, len(paths), per_page):
        page = paths[start:start + per_page]
        width, height = 230, 350
        sheet = Image.new('RGB', (width * 6, ((len(page) + 5) // 6) * (height + 22)), '#363a43')
        draw = ImageDraw.Draw(sheet)
        for k, path in enumerate(page):
            with Image.open(path) as source:
                im = source.convert('RGBA')
            if crop:
                im = im.crop(crop)
            scale = min(width / im.width, height / im.height)
            im = im.resize((round(im.width * scale), round(im.height * scale)), Image.Resampling.NEAREST)
            x, y = k % 6 * width, k // 6 * (height + 22)
            sheet.paste(im, (x, y), im)
            draw.text((x + 4, y + height + 3), str(start + k), fill='white')
        sheet.save(OUT / f'{prefix}-{start:02d}.png')


def generate():
    verify_originals()
    prompt = (
        'Animate this EXACT right-facing female cleric for 3 seconds, natural calm WALK IN PLACE. '
        'CRITICAL: her anatomical RIGHT arm is the NEAR arm, closest to camera, exactly as the input. '
        'Keep that visible near RIGHT shoulder, upper arm, bent elbow, white sleeve, forearm and gripping '
        'fist continuously connected. This SAME RIGHT FOREARM remains IN THE FOREGROUND ACROSS THE '
        'TORSO, visibly OVERLAPPING the chest and waist, clasping the gold staff throughout EVERY frame. '
        'Keep the near right elbow bent and the hand forward at chest/waist height. Never lower this '
        'near arm into an empty swinging hand. There is ONLY ONE visible hand: the near RIGHT hand '
        'holding the staff. The free LEFT arm is on the FAR side, completely HIDDEN BEHIND the torso, '
        'occluded throughout. No free hand may cross or swing in front of the body. No second visible '
        'arm. Staff stays vertical IN FRONT of the torso, ahead of her toes, never behind her body, '
        'back, hips or sleeve. Preserve the input arm layering and grip, no hand swap. '
        'Walk with relaxed alternating low steps, regular heel-to-toe weight transfer, about one '
        'complete left-right stride per second, repeating smoothly three times. Subtle vertical '
        'body bob and gentle hair and robe follow-through. No running, hopping, sliding, travelling, '
        'pivoting or exaggerated arm swing. Keep head, torso, hips and boots facing screen RIGHT. '
        'Preserve the exact elevated orthographic quarter-view camera looking down 30 degrees, '
        'fixed scale and position, three-head-tall proportions, costume and flat crisp pixel-art. '
        'Do not mirror the body. Entire head, boots and staff remain inside the frame. Orb solid '
        'UNLIT yellow, no glow, particles, aura, shadows or floor. Background exactly solid bright '
        'MAGENTA #FF00FF in EVERY frame. Return naturally to the starting pose.'
    )
    params = vp.validate_params(dict(state='walk', direction='side', facing='right',
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
        on_progress=lambda stage, message: print(stage, message, flush=True))
    save(OUT / 'generation.json', {**result, 'path': str(result['path'])})
    assert read(OUT / 'checkpoint.json')['postCount'] == 1
    if (OUT / 'candidate.json').exists():
        assert read(OUT / 'candidate.json')['sourceSha256'] == sha(result['path'])
        return
    processed = processing.process_clip(result['path'], OUT / 'processing',
        {**params, 'referencePath': str(OUT / 'provider/input-canvas.png'),
         'targetFrameCount': 8, 'targetDurationMs': 1000, 'between': 'off'},
        on_progress=lambda stage, message: print(stage, message, flush=True))
    save(OUT / 'processed.json', processed)
    paths, normalization = normalize_frames(processed['frames'], processed['standingHeight'], 112,
        OUT / 'normalized', bounds_paths=processed['boundsPaths'], source_anchor=processed['anchor'])
    paths, finish = finish_frames(paths, OUT / 'finished', mode='gif', cell_width=128, cell_height=160)
    frames = [dict(f, path=str(p)) for f, p in zip(processed['frames'], paths)]
    source_sha = sha(result['path'])
    record = dict(name='walk_E', direction='E', state='walk', take='right-hand-v1',
        sourceSha256=source_sha, sourceVideoSha256=source_sha, baseSha256=sha(BASE),
        requestId=result['receipt']['requestId'], frames=frames, normalization=normalization,
        finish=finish, selection=processed['selection'], source=processed['source'],
        processingReport=processed['files'], generationCheckpoint=str(OUT / 'checkpoint.json'),
        sourceVideoPath=str(result['path']), processingRoot=str(OUT / 'processing'),
        sourceProvenance=dict(baseImagePath=str(BASE), baseProvider='codex',
            baseGenerationRecord=str(BASE.parent / 'generation.json'),
            baseGenerationRecordSha256=sha(BASE.parent / 'generation.json'),
            motionProvider='grok-video', model=params['model'], postCount=1,
            mirrored=False, interpolation=False))
    validate(record)
    save(OUT / 'candidate.json', record)
    raw = sorted(Path(processed['extraction']['rawDir']).glob('frame-*.png'))
    keyed = sorted(Path(processed['extraction']['keyedDir']).glob('frame-*.png'))
    boxes = []
    for path in keyed:
        with Image.open(path) as image:
            box = image.getchannel('A').getbbox()
        if box:
            boxes.append(box)
    crop = (min(b[0] for b in boxes)-6, min(b[1] for b in boxes)-6,
            max(b[2] for b in boxes)+6, max(b[3] for b in boxes)+6)
    contacts(raw, 'source-full')
    contacts(raw, 'source-detail', crop)
    contacts([f['rawPath'] for f in frames], 'selected-source', crop)
    contacts(paths, 'finished')
    preview = processing._preview([dict(f, keyedPath=f['path']) for f in frames], OUT, True)
    save(OUT / 'selected-preview.json', preview)
    verify_originals()
    print('INSPECTION_READY', len(raw), 'source frames;', str(OUT / 'candidate.json'), flush=True)


def validate(record):
    checkpoint = read(OUT / 'checkpoint.json')
    assert checkpoint['postCount'] == 1 and checkpoint['phase'] == 'downloaded'
    assert checkpoint['requestId'] == record['requestId']
    assert checkpoint['receipt']['sha256'] == record['sourceSha256'] == sha(record['sourceVideoPath'])
    assert record['baseSha256'] == BASE_SHA == sha(BASE)
    assert record['name'] == 'walk_E' and record['state'] == 'walk' and record['direction'] == 'E'
    assert record['selection']['loop'] and record['selection']['cycleAlignment']['durationMs'] == 1000
    frames = record['frames']
    assert len(frames) == 8 and sum(f['durationMs'] for f in frames) == 1000
    assert len({f['sourceFrameIndex'] for f in frames}) == 8
    assert len({sha(f['path']) for f in frames}) == 8
    for frame in frames:
        assert frame['durationMs'] == 125 and not frame['interpolated']
        with Image.open(frame['path']) as image:
            assert image.width <= 128 and image.height <= 160 and image.getchannel('A').getbbox()


def finalize():
    count = verify_originals()
    record, review = read(OUT / 'candidate.json'), read(OUT / 'visual-review.json')
    validate(record)
    assert review['sourceSha256'] == record['sourceSha256']
    assert review['accepted'] and review['fullSourceReviewed'] and review['gaitFramesReviewed'] == list(range(8))
    record['visualReview'] = review
    record['preservation'] = dict(verifiedFiles=count, baseline=str(OUT / 'original-hashes.json'))
    save(OUT / 'complete.json', record)
    print('COMPLETE', str(OUT / 'complete.json'), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['generate', 'finalize'])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    vp.s.DATA = OUT
    assert not (OUT / 'complete.json').exists(), 'Completed take is immutable'
    {'generate': generate, 'finalize': finalize}[args.stage]()
