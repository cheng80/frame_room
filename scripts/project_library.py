"""Save standalone sprite results into a bound project before reporting completion."""
import argparse
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image
from services.api import store as s, videos, project_folders
from adapters.spritegen.video_processing import _write

DIRECTIONS = dict(zip(('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'),
                      ('북', '북동', '동', '남동', '남', '남서', '서', '북서')))


def target_project(run, project_id=None):
    """A missing/unregistered target fails before any provider request."""
    run = Path(run).resolve()
    binding = run / 'project-library.json'
    saved = json.loads(binding.read_text()) if binding.exists() else None
    if saved and (Path(saved['dataDirectory']).resolve() != s.DATA or
                  project_id not in (None, saved['projectId'])):
        raise s.AppError('LIBRARY_TARGET_CONFLICT', '다른 프로젝트에 연결된 출력 폴더입니다. 원본을 보존하고 별도 폴더를 사용하세요.')
    project_id = project_id or (saved or {}).get('projectId')
    if not project_id:
        raise s.AppError('LIBRARY_TARGET_REQUIRED', '라이브러리에 저장할 --project-id를 지정하세요. 생성은 실행하지 않았습니다.')
    p = s.get_project(project_id)
    project_folders.flush([project_id])
    project_folders.folder_for(project_id)
    if not saved:
        _write(binding, {'projectId': project_id, 'dataDirectory': str(s.DATA)})
    return p['projectId']


def _record(run, name, record_path=None):
    path = Path(record_path) if record_path else run / 'motions' / name / 'complete.json'
    record = json.loads(path.read_text())
    checkpoint = Path(record.get('generationCheckpoint', run / 'motions' / name / 'checkpoint.json'))
    generation = json.loads((checkpoint.parent / 'generation.json').read_text())
    video = Path(generation['path'])
    base = run / 'bases' / record['direction'] / 'anchor.png'
    if (s.digest(video.read_bytes()) != record['sourceSha256'] or
            s.digest(base.read_bytes()) != record['baseSha256']):
        raise s.AppError('LIBRARY_SOURCE_HASH', '기준 그림 또는 영상 원본이 변경됐습니다. 저장하지 않았습니다.', 424)
    return record, base, video


def _same_clip(p, clip, spec):
    slots = clip['occurrences']
    if clip['stateId'] != spec['key'] or clip['facing'] != spec['facing'] or clip['loop'] != spec['loop'] or len(slots) != len(spec['cells']):
        return False
    assets = {a['assetId']: a for a in p['assets']}
    frames = {f['frameVersionId']: f for f in p['frames']}
    groups = {g['alignmentGroupId']: g for g in p['alignmentGroups']}
    video = next((v for v in p['videos'] if v['videoId'] == clip.get('sourceVideoId')), {})
    ref = next((r for r in p['references'] if r['referenceRevisionId'] == clip.get('referenceRevisionId')), {})
    if video.get('sha256') != spec['videoMeta']['sha256'] or assets.get(ref.get('identityAssetId'), {}).get('sha256') != spec['baseMeta']['sha256']:
        return False
    for slot, cell, duration, source_index in zip(slots, spec['cells'], spec['durations'], spec['indices']):
        f = frames[slot['frameVersionId']]; group = groups[f['nativeScaleGroupId']]; al = p['alignments'][f['frameVersionId']]
        tr = slot['transform']
        if (slot['durationMs'] != duration or slot.get('pixelEdits') or
                f.get('sourceFrameIndex') != source_index or f.get('sourceTimeMs') != spec['times'][source_index] or
                any(tr.get(k, 0) != 0 for k in ('dx', 'dy', 'rotationDeg', 'shearX', 'shearY')) or
                any(tr.get(k, 1) != 1 for k in ('scaleX', 'scaleY')) or tr.get('flipX') or tr.get('flipY') or
                group['sharedScale'] != 1 or group['targetAnchor'] != spec['anchor'] or
                al['sourceAnchor'] != spec['anchor'] or al.get('anchorSpace') != 'crop' or
                al.get('contactMode') != 'grounded' or al['authoredOffsetPx'] != {'x': 0, 'y': 0} or
                (group['cell']['width'], group['cell']['height']) != cell.size or
                assets[f['imageAssetId']]['decodedHash'] != s.digest(cell.tobytes())):
            return False
        s.asset_path(f['imageAssetId'])
    return True


def publish(project_id, specs, receipt_path):
    """Append new versions, preserve edits, and make retrying identical results harmless."""
    if not specs or len({v['key'] for v in specs}) != len(specs):
        raise s.AppError('LIBRARY_ANIMATIONS_REQUIRED', '저장할 동작이 없거나 중복되었습니다.')
    for spec in specs:
        if (not spec['cells'] or len(spec['cells']) != len(spec['durations']) or
                len(spec['cells']) != len(spec['indices']) or
                any(type(d) is not int or not 1 <= d <= 60000 for d in spec['durations'])):
            raise s.AppError('LIBRARY_TIMING_INVALID', '동작 프레임과 표시 시간을 확인하세요.')
        size = spec['cells'][0].size
        if any(c.mode != 'RGBA' or c.size != size or not c.getchannel('A').getbbox() for c in spec['cells']):
            raise s.AppError('LIBRARY_FRAMES_INVALID', '동작 셀의 크기·투명도·빈 이미지를 확인하세요.')
        spec['baseMeta'] = s.validate_image(spec['base'].read_bytes(), spec['base'].name)
        spec['videoMeta'] = videos.validate(spec['video'].read_bytes(), spec['video'].name)
        spec['videoMeta']['timesMs'] = spec['times']
        if any(type(i) is not int or not 0 <= i < spec['videoMeta']['frameCount'] or i >= len(spec['times']) for i in spec['indices']):
            raise s.AppError('LIBRARY_FRAME_INDEX_INVALID', '원본 영상의 프레임 시각을 확인하세요.')
    saved_ids = []; added = 0
    with s.project_scope(project_id), s.transaction() as db:
        p = s.get_project(project_id, db)
        for spec in specs:
            previous = next((cl for cl in p['clips'] if _same_clip(p, cl, spec)), None)
            if previous:
                saved_ids.append(previous['clipId']); continue
            d = spec['direction']; base_sha = spec['baseMeta']['sha256']
            ref = next((r for r in p['references'] if any(a['assetId'] == r['identityAssetId'] and a['sha256'] == base_sha for a in p['assets'])), None)
            if ref is None:
                base = s.register_asset(spec['base'].read_bytes(), f'{d}-anchor.png', 'identity',
                    {'kind': 'real-provider', 'providerId': 'codex', 'directionCode': d}, spec['baseMeta'], db)
                base['name'] = f'{DIRECTIONS.get(d, d)}({d}) · 기준 그림'
                p['assets'].append(base)
                ref = dict(referenceRevisionId=s.uid(), name=base['name'], identityAssetId=base['assetId'],
                    styleAssetIds=[], poseAssetIds=[], fixedTraits='', allowedChanges='', forbiddenTransfers='',
                    facing=spec['facing'], bodyMeasurement=None, approval='draft')
                p['references'].append(ref)
                if not p.get('activeReferenceRevisionId'): p['activeReferenceRevisionId'] = ref['referenceRevisionId']
            video = next((v for v in p['videos'] if v['sha256'] == spec['videoMeta']['sha256']), None)
            if video is None:
                video = videos.register(spec['video'].read_bytes(), spec['video'].name,
                    {'kind': 'real-provider-video', 'providerId': 'grok-video', 'baseAssetId': ref['identityAssetId'],
                     'referenceRevisionId': ref['referenceRevisionId'], 'requestId': spec.get('requestId')}, spec['videoMeta'], db)
                p['videos'].append(video)
            w, h = spec['cells'][0].size
            group = dict(alignmentGroupId=s.uid(), groupRevisionId=s.uid(), frameVersionIds=[],
                mode='preserve-source-scale', sharedScale=1, cell={'width': w, 'height': h, 'edge': 4},
                targetAnchor=spec['anchor'], bodyMeasurement=None, resampler='nearest', roundingVersion='js-round-v1')
            occurrences = []
            for i, (cell, duration, source_index) in enumerate(zip(spec['cells'], spec['durations'], spec['indices'])):
                stream = io.BytesIO(); cell.save(stream, format='PNG')
                asset = s.register_asset(stream.getvalue(), f"{spec['key']}_{i:02d}.png", 'derived',
                    {'kind': 'video-frame', 'processing': 'video-finish', 'sourceVideoId': video['videoId'],
                     'sourceFrameIndex': source_index, 'sourceTimeMs': spec['times'][source_index],
                     'baseAssetId': ref['identityAssetId'], 'librarySource': spec['key']}, c=db)
                p['assets'].append(asset); fid = s.uid()
                p['frames'].append(dict(frameId=s.uid(), frameVersionId=fid, rawAssetId=asset['assetId'], imageAssetId=asset['assetId'],
                    sourceRect={'x': 0, 'y': 0, 'width': w, 'height': h},
                    sourceToFrameTransform={'scaleX': 1, 'scaleY': 1, 'offsetX': 0, 'offsetY': 0},
                    extractionVersion='standalone-library-v1', nativeScaleGroupId=group['alignmentGroupId'], review='pending', hidden=False,
                    sourceVideoId=video['videoId'], sourceFrameIndex=source_index, sourceTimeMs=spec['times'][source_index]))
                group['frameVersionIds'].append(fid)
                p['alignments'][fid] = dict(frameVersionId=fid, groupRevisionId=group['groupRevisionId'],
                    sourceAnchor=spec['anchor'], anchorSpace='crop', method='manual', contactMode='grounded',
                    authoredOffsetPx={'x': 0, 'y': 0}, approval='pending')
                occurrences.append(dict(occurrenceId=s.uid(), frameVersionId=fid, durationMs=duration, timingMode='explicit', pixelEdits=[],
                    transform={'dx': 0, 'dy': 0, 'scaleX': 1, 'scaleY': 1, 'rotationDeg': 0, 'shearX': 0, 'shearY': 0, 'flipX': False, 'flipY': False}))
            p['alignmentGroups'].append(group)
            version = sum(cl['stateId'] == spec['key'] for cl in p['clips']) + 1
            clip = dict(clipId=s.uid(), clipRevisionId=s.uid(), name=spec['name'] + (f' · 보정 {version}' if version > 1 else ''),
                stateId=spec['key'], facing=spec['facing'], referenceRevisionId=ref['referenceRevisionId'], sourceVideoId=video['videoId'],
                loop=spec['loop'], endBehavior='hold-last', defaultFps=min(60, max(1, round(len(occurrences) * 1000 / sum(spec['durations'])))),
                occurrences=occurrences, review='pending', libraryProcessing=spec.get('processing', {}))
            p['clips'].append(clip); saved_ids.append(clip['clipId']); added += 1
        s.validate_snapshot(p)
        if added: s.write_project(db, p, '별도 생성·보정 동작 라이브러리 저장')
    project_folders.flush([project_id])
    _, portable = project_folders._read(s.project_folder(project_id))
    for clip_id, spec in zip(saved_ids, specs):
        clip = next(cl for cl in portable['clips'] if cl['clipId'] == clip_id)
        if not _same_clip(portable, clip, spec):
            raise s.AppError('LIBRARY_SAVE_UNCONFIRMED', '프로젝트 폴더의 동작 저장을 확인하지 못했습니다. 원본은 보존됩니다.', 424)
    receipt = {'status': 'saved', 'projectId': project_id, 'savedRevision': portable['revision'],
               'clipIds': saved_ids, 'addedClips': added, 'folderVerified': True}
    _write(Path(receipt_path), receipt)
    return receipt


def _spec(record, base, video, cells, anchor):
    state, d = record['state'], record['direction']
    selection = record['selection']
    processing = {'normalization': record.get('normalization'), 'finish': record.get('finish'),
        'take': record.get('take'), 'selection': {k: selection[k] for k in
        ('kind', 'startFrame', 'endFrame', 'sourceDurationMs', 'durationMs', 'sampling',
         'manualSourceFrameIndices', 'sourceSampleBoundariesMs', 'sampleBoundariesMs',
         'playbackDurationsMs', 'closedBlinkSourceFrameIndices') if k in selection}}
    return {'key': record['name'], 'name': f"{'걷기' if state == 'walk' else '대기'} · {DIRECTIONS.get(d, d)}({d})",
            'direction': d, 'facing': 'left' if d in ('SW', 'W', 'NW') else 'right',
            'cells': cells, 'anchor': anchor, 'durations': [f['durationMs'] for f in record['frames']],
            'indices': [f['sourceFrameIndex'] for f in record['frames']], 'times': record['source']['timesMs'],
            'loop': record['selection']['loop'], 'base': base, 'video': video, 'requestId': record['requestId'],
            'processing': processing}


def publish_record(run, record_path, project_id=None):
    run, path = Path(run).resolve(), Path(record_path).resolve()
    pid = target_project(run, project_id)
    name = json.loads(path.read_text())['name']
    record, base, video = _record(run, name, path)
    anchor = record['normalization']['anchor']; cells = []
    for f in record['frames']:
        cell = Image.new('RGBA', (128, 160))
        cell.alpha_composite(Image.open(f['path']).convert('RGBA'), (round(64-anchor['x']), round(148-anchor['y'])))
        pixels = bytearray(cell.tobytes())
        for i in range(0, len(pixels), 4):
            if not pixels[i+3]: pixels[i:i+3] = b'\0\0\0'
        cells.append(Image.frombytes('RGBA', cell.size, bytes(pixels)))
    return publish(pid, [_spec(record, base, video, cells, {'x': 64, 'y': 148})], path.parent / 'library-publication.json')


def publish_delivery(run, delivery, project_id=None):
    run, delivery = Path(run).resolve(), Path(delivery).resolve()
    pid = target_project(run, project_id)
    manifest = json.loads((delivery / 'cleric-manifest.json').read_text())
    atlas = json.loads((delivery / 'cleric-atlas.json').read_text())
    data = (delivery / 'cleric-atlas.png').read_bytes()
    if s.digest(data) != manifest['atlasSha256'] or set(manifest['animations']) != set(atlas['animations']):
        raise s.AppError('LIBRARY_ATLAS_INVALID', '시트와 동작 목록이 일치하지 않습니다.')
    sheet = Image.open(io.BytesIO(data)).convert('RGBA'); specs = []
    for name, clip in manifest['animations'].items():
        correction = manifest.get('harmonization', {}).get('motionCorrections', {}).get(name, {})
        record, base, video = _record(run, name, ROOT / correction['recordPath'] if correction.get('recordPath') else None)
        if clip['sourceVideoSha256'] != record['sourceSha256'] or clip['baseImageSha256'] != record['baseSha256']:
            raise s.AppError('LIBRARY_SOURCE_HASH', '시트와 원본 영상의 출처가 일치하지 않습니다.')
        if clip['frameNames'] != atlas['animations'][name] or sum(clip['durationsMs']) != clip['durationMs']:
            raise s.AppError('LIBRARY_TIMING_INVALID', '시트와 동작의 순서·시간이 일치하지 않습니다.')
        cells = []
        for key, duration in zip(clip['frameNames'], clip['durationsMs']):
            r = atlas['frames'][key]['frame']
            if atlas['frames'][key]['duration'] != duration or not (0 <= r['x'] < r['x']+r['w'] <= sheet.width and 0 <= r['y'] < r['y']+r['h'] <= sheet.height):
                raise s.AppError('LIBRARY_ATLAS_INVALID', '시트 프레임 영역·시간을 확인하세요.')
            cells.append(sheet.crop((r['x'], r['y'], r['x']+r['w'], r['y']+r['h'])))
        anchor = {'x': manifest['anchor']['x']*cells[0].width, 'y': manifest['anchor']['y']*cells[0].height}
        spec = _spec(record, base, video, cells, anchor)
        spec.update(durations=clip['durationsMs'], indices=clip['sourceFrameIndices'], loop=clip['loop'])
        spec['processing'].update(atlasSha256=manifest['atlasSha256'],
            harmonization={k: v for k, v in manifest.get('harmonization', {}).items() if k not in ('report', 'motionCorrections')},
            motionCorrection={k: v for k, v in correction.items() if k != 'recordPath'})
        spec['processing']['selection'].update({k: clip['selection'][k] for k in
            ('samplingCorrection', 'sourceSampleBoundariesMs', 'playbackDurationsMs') if k in clip.get('selection', {})})
        specs.append(spec)
    return publish(pid, specs, delivery / 'library-publication.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--project-id')
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--delivery', type=Path)
    choice.add_argument('--record', type=Path)
    args = parser.parse_args()
    result = publish_delivery(args.run, args.delivery, args.project_id) if args.delivery else publish_record(args.run, args.record, args.project_id)
    print(json.dumps(result, ensure_ascii=False))
