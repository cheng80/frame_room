"""Generate a separate eight-way deliverable through the project's existing engine.

Original project files are read-only. Receipts prevent accidental re-submission;
local processing can be repeated without generating another image or video.
"""
import argparse
import concurrent.futures
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image
from alignment.pipeline import _engine
from alignment.animation_exports import _sheet, write_animation_formats
from adapters.spritegen import video_provider as vp, video_processing as processing
from adapters.spritegen.video_normalization import normalize_frames
from adapters.spritegen.video_finish import finish_frames

VIEWS = {'N': ('back', 'right'), 'NE': ('back_diagonal', 'right'),
         'E': ('side', 'right'), 'SE': ('front_diagonal', 'right'),
         'S': ('front', 'right'), 'SW': ('front_diagonal', 'left'),
         'W': ('side', 'left'), 'NW': ('back_diagonal', 'left')}
ORDER = ['SE', 'S', 'E', 'NE', 'N', 'NW', 'W', 'SW']
SOURCE = ROOT / 'output/healer-walk/cleric-side-no-effects.png'

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def bases(out, directions):
    gen = _engine('gen')
    reference = out / 'source/cleric-original-no-effects.png'
    reference.parent.mkdir(parents=True, exist_ok=True)
    if not reference.exists(): shutil.copyfile(SOURCE, reference)
    if sha(reference) != sha(SOURCE): raise ValueError('The source changed; preserve the existing run.')
    for direction in directions:
        folder = out / 'bases' / direction
        folder.mkdir(parents=True, exist_ok=True)
        receipt, marker, image = folder / 'generation.json', folder / 'submission.json', folder / 'anchor.png'
        if receipt.exists():
            if sha(image) != json.loads(receipt.read_text())['sha256']: raise ValueError('Anchor changed')
            print('BASE_REUSED', direction, flush=True); continue
        if marker.exists(): raise ValueError(f'{direction}: image request already started; inspect its saved session before retrying.')
        view, facing = VIEWS[direction]
        prompt = (
            'Create ONE single-pose full-body game character image of the exact female cleric in the reference. '
            'Preserve her three-head-tall SD chibi proportions, long golden-blonde hair, amber eyes, '
            'white hood/veil with golden crosses, white and gold cleric dress, belt, boots, and ornate golden staff. '
            'This is an eight-direction ISOMETRIC / QUARTER-VIEW RPG asset: camera elevated about 30 degrees '
            'above the ground, orthographic projection looking slightly downward, with the top of her hood '
            'and shoulders visible. This elevated camera stays identical for every direction. '
            'Change the body facing, not the camera. Preserve flat 2D pixel-art rendering with crisp clusters '
            'and restrained shading. No 3D render, perspective lens or realistic lighting. '
            'A relaxed balanced standing stance with BOTH feet planted, separated, a very small stagger, '
            'knees relaxed; no raised foot. Staff vertical in front of her torso, gripped by her own RIGHT hand, '
            'with the right elbow bent and forearm extending forward; never trailing behind her back. '
            'Her free left hand rests naturally. The circular staff orb is solid pale golden yellow and UNLIT. '
            'No glow, aura, particles, magic, shadows, floor, captions or extra character. '
            'Full head, feet and entire staff inside the canvas with generous empty margin. '
            'Keep the same costume construction and three-head-tall proportions from the design reference. '
        )
        refs = [reference]
        if direction != 'SE' and (out / 'bases/SE/anchor.png').exists():
            refs.append(out / 'bases/SE/anchor.png')
            prompt += 'The second reference locks the elevated camera, outfit and pixel art style; rotate her body to the requested direction. '
        save(marker, {'provider': 'codex', 'model': 'gpt-6-sol', 'direction': direction, 'refs': [str(p) for p in refs], 'prompt': prompt})
        print('BASE_START', direction, flush=True)
        result = gen.generate_image('codex', prompt, image, refs=refs, model='gpt-6-sol',
            transparent=True, alpha_mode='native', trim_alpha=False,
            view=view, facing=facing if view not in ('front','back') else None, facing_fix='none',
            handed=gen.handed_mod.parse_all(['the golden staff=right hand']),
            keep_session=True, workdir=folder / 'provider')
        save(receipt, {**result.to_dict(), 'directionCode': direction, 'sha256': sha(image)})
        print('BASE_DONE', direction, round(result.elapsed_seconds), flush=True)

def clip(out, direction, state, *, take=None):
    published = out / 'motions' / f'{state}_{direction}'
    folder = published / take if take else published
    folder.mkdir(parents=True, exist_ok=True)
    complete = published / 'complete.json'
    if complete.exists():
        record = json.loads(complete.read_text())
        if record['baseSha256'] != sha(out / 'bases' / direction / 'anchor.png'):
            raise ValueError(f'{state}_{direction}: archive the previous completed draft before replacing its base.')
        return record
    view, facing = VIEWS[direction]
    source = out / 'bases' / direction / 'anchor.png'
    deadline = time.monotonic()+900
    while not (source.parent / 'generation.json').exists():
        if time.monotonic()>deadline: raise ValueError(f'{direction}: direction anchor is not ready.')
        time.sleep(2)
    motion = ('A calm natural WALK in place, alternating small low steps at a regular pace. '
              'No running or hopping. Keep the same heading, no pivot or travelling. ' if state == 'walk' else
              'Stand IDLE in place, BOTH feet planted for the entire clip. Only subtle breathing, '
              'one blink and small settling of hair and robe. Never step, shuffle or walk. ')
    motion += ('Preserve the input isometric QUARTER-VIEW camera looking downward from 30 degrees, '
               'orthographic view, and the exact body facing and flat pixel-art design. '
               'Preserve the exact shoulder-arm-hand connection from the input: the golden staff stays '
               'vertical in her own RIGHT hand, held ahead of her torso with a bent right elbow. '
               'Never swap hands or move the staff behind her hips/back. Solid UNLIT yellow orb; '
               'no glow, light effects, particles, aura or shadows. Head, boots, hair and staff stay inside '
               'the frame. Fixed camera and constant scale. Return to the exact starting pose.')
    if take:
        motion = ('The background MUST remain exactly solid bright MAGENTA #FF00FF in EVERY frame, '
                  'including the middle and the last frame. Never transition to yellow, gold, pink, '
                  'white or any other background color. No background animation or color fade. ')+motion
    params = vp.validate_params({'state': state, 'direction': view, 'facing': facing,
        'bodyPlan': 'biped', 'equipment': 'staff:right', 'model': 'grok-imagine-video-1.5',
        'durationSeconds': 3, 'resolution': '480p', 'maxFrames': 8,
        'bodyHeight': 112, 'cellWidth': 128, 'cellHeight': 160,
        'finishMode': 'gif', 'repairMode': 'off', 'motionPrompt': motion}, generation=True)
    save(folder / 'request.json', params)
    digest = hashlib.sha256((json.dumps(params, sort_keys=True) + sha(source)).encode()).hexdigest()
    print('VIDEO_START', state, direction, flush=True)
    result = vp.generate(source, folder / 'provider', params, folder / 'checkpoint.json', digest)
    save(folder / 'generation.json', {**result, 'path': str(result['path'])})
    processed = processing.process_clip(result['path'], folder / 'processing',
        {**params, 'key': 'magenta', 'referencePath': str(folder / 'provider/input-canvas.png')})
    paths, normalization = normalize_frames(processed['frames'], processed['standingHeight'], 112,
        folder / 'normalized', bounds_paths=processed['boundsPaths'], source_anchor=processed['anchor'])
    paths, finish = finish_frames(paths, folder / 'finished', mode='gif', cell_width=128, cell_height=160)
    record = {'name': f'{state}_{direction}', 'direction': direction, 'state': state,
        'sourceSha256': sha(result['path']), 'baseSha256': sha(source), 'requestId': result['receipt']['requestId'],
        'frames': [dict(f, path=str(p)) for f,p in zip(processed['frames'], paths)],
        'normalization': normalization, 'finish': finish, 'selection': processed['selection'],
        'source': processed['source'], 'processingReport': processed['files'],
        'generationCheckpoint':str(folder/'checkpoint.json'), 'take':take or 'original'}
    save(complete, record)
    print('VIDEO_DONE', state, direction, len(paths), processed['selection']['durationMs'], flush=True)
    return record

def clips(out, directions):
    # Isolated adapter output root; never write to the user's application database.
    vp.s.DATA = out
    vp.login_credential()
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        tasks = {executor.submit(clip, out, d, s): f'{s}_{d}' for d in directions for s in ('walk', 'idle')}
        for future in concurrent.futures.as_completed(tasks):
            try: future.result()
            except BaseException as exc:
                name = tasks[future]
                save(out / 'motions' / name / 'failure.json', {'code': getattr(exc,'code',type(exc).__name__), 'message': str(exc), 'details': getattr(exc,'details',{})})
                failures.append(name); print('FAILED', name, type(exc).__name__, str(exc), flush=True)
    if failures: raise SystemExit('Unfinished motions: ' + ', '.join(failures))

def match_walks(out):
    vp.s.DATA = out
    for direction in VIEWS:
        published = out / 'motions' / f'walk_{direction}'
        complete = published / 'complete.json'
        record = json.loads(complete.read_text())
        aligned = record['selection'].get('cycleAlignment', {})
        if aligned.get('durationMs') == 1000 and len(record['frames']) == 8:
            continue
        provider = Path(record.get('generationCheckpoint', published / 'checkpoint.json')).parent
        params = json.loads((provider / 'request.json').read_text())
        generation = json.loads((provider / 'generation.json').read_text())
        folder = published / ('cycle-matched-' + record['baseSha256'][:12])
        processed = processing.process_clip(Path(generation['path']), folder / 'processing',
            {**params, 'key': 'magenta', 'referencePath': str(provider / 'provider/input-canvas.png'),
             'targetFrameCount': 8, 'targetDurationMs': 1000, 'between': 'off'})
        paths, normalization = normalize_frames(processed['frames'], processed['standingHeight'], 112,
            folder / 'normalized', bounds_paths=processed['boundsPaths'], source_anchor=processed['anchor'])
        paths, finish = finish_frames(paths, folder / 'finished', mode='gif', cell_width=128, cell_height=160)
        backup = published / ('before-cycle-match-' + record['baseSha256'][:12] + '.json')
        if not backup.exists(): shutil.copy2(complete, backup)
        save(complete, {**record, 'frames': [dict(f, path=str(p)) for f,p in zip(processed['frames'],paths)],
            'normalization': normalization, 'finish': finish, 'selection': processed['selection'],
            'source': processed['source'], 'processingReport': processed['files']})
        print('CYCLE_MATCHED', direction, len(paths), 1000, flush=True)

def pack(out):
    target = out / 'delivery'
    target.mkdir(parents=True, exist_ok=True)
    for state in ('walk', 'idle'):
        for direction in VIEWS:
            record = json.loads((out / 'motions' / f'{state}_{direction}' / 'complete.json').read_text())
            if record['baseSha256'] != sha(out / 'bases' / direction / 'anchor.png'):
                raise ValueError(f'{state}_{direction}: motion uses an older base image.')
    if (target / 'animations').exists():
        history = out / 'delivery-history' / str(time.time_ns())
        history.mkdir(parents=True)
        (target / 'animations').rename(history / 'animations')
        for name in ('cleric-atlas.png', 'cleric-atlas.json', 'cleric-manifest.json'):
            if (target / name).exists(): shutil.copy2(target / name, history / name)
    cells, frame_data, animations, manifest = [], {}, {}, {}
    for state in ('walk', 'idle'):
        for direction in VIEWS:
            name = f'{state}_{direction}'
            record = json.loads((out / 'motions' / name / 'complete.json').read_text())
            anchor = record['normalization']['anchor']
            names, durations, images = [], [], []
            for i, frame in enumerate(record['frames']):
                sprite = Image.open(frame['path']).convert('RGBA')
                x,y = round(64-anchor['x']), round(148-anchor['y'])
                box = sprite.getchannel('A').getbbox()
                if not box or min(box[0]+x,box[1]+y,128-box[2]-x,160-box[3]-y)<4:
                    raise ValueError(f'{name}/{i}: sprite needs more cell margin; preserve source and enlarge the common cell.')
                cell = Image.new('RGBA',(128,160)); cell.alpha_composite(sprite,(x,y))
                key = f'{name}_{i:02d}'; index = len(cells)
                frame_data[key] = {'frame': {'x': index%8*128,'y': index//8*160,'w':128,'h':160},
                    'rotated':False, 'trimmed':False, 'spriteSourceSize':{'x':0,'y':0,'w':128,'h':160},
                    'sourceSize':{'w':128,'h':160}, 'anchor':{'x':.5,'y':148/160}, 'duration':frame['durationMs']}
                names.append(key); durations.append(frame['durationMs']); images.append(cell); cells.append(cell)
            animations[name] = names
            manifest[name] = {'frameNames':names,'durationsMs':durations,'durationMs':sum(durations),
                'loop':True,'direction':direction,'state':state,'sourceVideoSha256':record['sourceSha256'],
                'baseImageSha256':record['baseSha256'],
                'requestId':record['requestId'], 'sourceFrameIndices':[f['sourceFrameIndex'] for f in record['frames']],
                'selection':record['selection']}
            write_animation_formats(images,durations,True,target / 'animations' / name)
    data, sheet_info = _sheet(cells,8)
    if data is None: raise ValueError(sheet_info)
    (target / 'cleric-atlas.png').write_bytes(data)
    save(target / 'cleric-atlas.json', {'frames':frame_data,'animations':animations,
        'meta':{'app':'FrameRoom project engine','version':'1','image':'cleric-atlas.png','format':'RGBA8888',
                'size':{'w':sheet_info['width'],'h':sheet_info['height']},'scale':'1'}})
    save(target / 'cleric-manifest.json', {'character':'SD 여성 신관 · 효과 없음', 'directions':list(VIEWS),
        'camera':'orthographic quarter view, 30-degree elevation', 'cell':{'width':128,'height':160},
        'anchor':{'x':.5,'y':148/160}, 'animations':manifest, 'frameCount':len(cells),
        'mirroredDirections':[], 'imageProvider':'GPT ImageGen via Codex subscription',
        'motionProvider':'Grok video Pro via account login', 'atlasSha256':sha(target/'cleric-atlas.png')})
    print('PACK_DONE',len(cells),sheet_info,flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage',choices=['bases','clips','match-walks','pack'],required=True)
    parser.add_argument('--directions',default=','.join(ORDER))
    parser.add_argument('--out',type=Path,default=ROOT/'output/cleric-quarterview-8way')
    args = parser.parse_args(); args.out=args.out.resolve()
    dirs=args.directions.split(',')
    if len(dirs)!=len(set(dirs)) or any(d not in VIEWS for d in dirs): parser.error('Use unique N,NE,E,SE,S,SW,W,NW directions')
    {'bases':lambda:bases(args.out,dirs),'clips':lambda:clips(args.out,dirs),
     'match-walks':lambda:match_walks(args.out),'pack':lambda:pack(args.out)}[args.stage]()
