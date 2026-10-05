"""Local clip diagnostics and immutable, hash-checked follow publication."""
from __future__ import annotations

import copy
import io
from pathlib import Path

from PIL import Image

from alignment.animation_exports import write_animation_formats
from alignment.pipeline import _engine
from services.api import store as s

VERSION = 'clip-tools-v1'
MAX_PIXELS = 16_777_216


def validate_apply(snapshot, params, connection=None):
    if (not isinstance(params, dict) or set(params) != {'previewJobId'}
            or not isinstance(params['previewJobId'], str) or not 1 <= len(params['previewJobId']) <= 200):
        raise s.AppError('FOLLOW_PREVIEW_REQUIRED', '저장할 흔들림 미리보기 작업을 선택하세요.')
    preview = s.get_job(params['previewJobId'], connection)
    if preview.get('projectId') != snapshot['projectId']:
        raise s.AppError('FOLLOW_PREVIEW_PROJECT', '같은 프로젝트의 미리보기만 저장할 수 있습니다.', 404)
    if preview['operation'] != 'preview_follow' or preview['status'] != 'succeeded' or not preview.get('published'):
        raise s.AppError('FOLLOW_PREVIEW_INCOMPLETE', '성공한 흔들림 미리보기만 저장할 수 있습니다.', 409)
    result = preview.get('result', {})
    source = result.get('source', {})
    if result.get('version') != VERSION or result.get('tool') != 'follow' or source.get('projectId') != snapshot['projectId']:
        raise s.AppError('FOLLOW_PREVIEW_INVALID', '미리보기 출처가 유효하지 않습니다.', 424)
    s.check_revision(snapshot, source.get('projectRevision'))
    if result.get('sourceProjectRevision') != snapshot['revision'] or preview['inputRevision'] != snapshot['revision']:
        raise s.AppError('REVISION_CONFLICT', '프로젝트가 바뀌었습니다. 흔들림 미리보기를 다시 만드세요.', 409)
    clip = next((cl for cl in snapshot['clips'] if cl['clipId'] == source.get('clipId')), None)
    if not clip or clip['clipRevisionId'] != source.get('clipRevisionId'):
        raise s.AppError('FOLLOW_PREVIEW_INVALID', '미리보기 동작 버전이 다릅니다.', 409)
    return {'previewJobId': preview['jobId']}


def _check_cells(cells, durations):
    if (not 1 <= len(cells) <= 64 or len(cells) != len(durations)
            or any(type(d) is not int or not 1 <= d <= 60000 for d in durations)
            or sum(durations) > 60000):
        raise s.AppError('CLIP_TOOLS_TIMING', '64슬롯·60초 이하의 유효한 동작이 필요합니다.')
    if (any(min(im.size) < 1 or max(im.size) > 1024 or im.size != cells[0].size for im in cells)
            or sum(im.width * im.height for im in cells) > MAX_PIXELS):
        raise s.AppError('CLIP_TOOLS_SIZE', '출력 셀은 1024×1024·전체 16M 픽셀 이하여야 합니다.', 413)


def _write_cells(cells, durations, loop, out, prefix, source):
    directory = out / prefix
    exported = write_animation_formats(cells, durations, loop, directory)
    for key in ('webp', 'stripPng'):
        if exported['formats'][key]['status'] != 'created':
            raise s.AppError('CLIP_TOOLS_EXPORT', '정확한 WebP·PNG 미리보기를 만들 수 없습니다.', 424)
    records = []
    for index, (cell, duration) in enumerate(zip(cells, durations)):
        name = f'{prefix}/{index:03d}.png'
        cell.save(out / name, format='PNG')
        records.append({'name': name, 'sha256': s.digest((out / name).read_bytes()),
                        'index': index, 'durationMs': duration,
                        'occurrenceId': source['occurrenceIds'][index],
                        'frameVersionId': source['frameVersionIds'][index],
                        'sourceAssetId': source['sourceAssetIds'][index]})
    files = [f'{prefix}/{name}' for name in exported['files']] + [r['name'] for r in records]
    return files, records, f"{prefix}/{exported['formats']['webp']['file']}", f"{prefix}/{exported['formats']['stripPng']['file']}"


def execute_clip_tools(j, out):
    from adapters.spritegen import clip_tools

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if j['operation'] == 'apply_follow':
        return _prepare_apply(j, out)
    snapshot = j['snapshot']
    params = clip_tools.validate_params(snapshot, j['operation'], j['request']['params'])
    cells, durations, source = clip_tools.render_clip(snapshot, params, s.asset_path)
    _check_cells(cells, durations)
    clip = next(cl for cl in snapshot['clips'] if cl['clipId'] == source['clipId'])
    files, before, animation, strip = _write_cells(cells, durations, clip['loop'], out, 'before', source)
    preview = {'width': cells[0].width, 'height': cells[0].height, 'frameCount': len(cells),
               'durationsMs': durations, 'before': animation, 'beforeStrip': strip, 'firstFrame': before[0]['name']}
    result = {'tool': 'follow' if j['operation'] == 'preview_follow' else 'handed', 'version': VERSION,
              'source': source, 'sourceProjectRevision': snapshot['revision'], 'settings': params,
              'preview': preview, 'cellFiles': {'before': before}, 'files': files}
    if j['operation'] == 'preview_follow':
        after, report = clip_tools.follow_frames(cells, durations, params)
        _check_cells(after, durations)
        if after[0].size != cells[0].size:
            raise s.AppError('CLIP_TOOLS_SIZE', '흔들림 결과의 셀 크기가 변경되었습니다.', 424)
        outputs, records, animation, strip = _write_cells(after, durations, clip['loop'], out, 'after', source)
        files.extend(outputs)
        result['cellFiles']['after'] = records
        preview.update(after=animation, afterStrip=strip)
    else:
        references = None
        if params.get('referenceAssetId'):
            asset = next(a for a in snapshot['assets'] if a['assetId'] == params['referenceAssetId'])
            data = s.asset_path(asset['assetId']).read_bytes()
            if s.digest(data) != asset['sha256']:
                raise s.AppError('ASSET_HASH', '기준 그림의 해시가 변경되었습니다.', 424)
            with Image.open(io.BytesIO(data)) as image:
                references = [image.convert('RGBA')]
        report = clip_tools.check_frames(cells, params, references=references)
        for suspect in report.get('suspectFrames', []):
            suspect['occurrenceId'] = source['occurrenceIds'][suspect['index']]
        # Bound the diagnostic board too, including very wide/short cells.
        height = min(240, cells[0].height, max(1, round(480 * cells[0].height / cells[0].width)))
        _engine('qa.handed').board(cells, report['engineReport'], out / 'handed-board.png', height=height)
        preview['board'] = 'handed-board.png'
        files.append('handed-board.png')
    result['report'] = report
    s.atomic_bytes(out / 'report.json', s.dumps({k: v for k, v in result.items() if k != 'files'}).encode())
    files.append('report.json')
    result['fileHashes'] = [{'name': name, 'sha256': s.digest((out / name).read_bytes())} for name in files]
    return result


def _safe_file(root, name):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise s.AppError('FOLLOW_PREVIEW_INVALID', '미리보기 파일 경로가 잘못되었습니다.', 424)
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise s.AppError('FOLLOW_PREVIEW_MISSING', '미리보기 파일이 없습니다.', 424)
    return path


def _after_cells(result, snapshot):
    source = result['source']
    clip = next(cl for cl in snapshot['clips'] if cl['clipId'] == source['clipId'])
    slots = clip['occurrences']
    frames = {f['frameVersionId']: f for f in snapshot['frames']}
    records = result.get('cellFiles', {}).get('after', [])
    preview = result['preview']
    expected_ids = [o['occurrenceId'] for o in slots]
    if (source.get('occurrenceIds') != expected_ids or len(records) != len(slots)
            or preview['frameCount'] != len(slots) or len(source.get('anchors', [])) != len(slots)
            or preview['durationsMs'] != [o['durationMs'] for o in slots]):
        raise s.AppError('FOLLOW_PREVIEW_INVALID', '미리보기 슬롯·시간·앵커가 원본과 다릅니다.', 424)
    names = set()
    for index, (record, slot) in enumerate(zip(records, slots)):
        frame = frames[slot['frameVersionId']]
        if (record.get('index') != index or record.get('occurrenceId') != slot['occurrenceId']
                or record.get('frameVersionId') != frame['frameVersionId']
                or record.get('sourceAssetId') != frame['imageAssetId']
                or record.get('durationMs') != slot['durationMs'] or record.get('name') in names):
            raise s.AppError('FOLLOW_PREVIEW_INVALID', '미리보기 프레임 출처가 원본과 다릅니다.', 424)
        names.add(record['name'])
    return clip, records


def _prepare_apply(j, out):
    # The queued snapshot and the live project must both still match the preview.
    settings = validate_apply(j['snapshot'], j['request']['params'])
    s.check_revision(s.get_project(j['projectId']), j['inputRevision'])
    job = s.get_job(settings['previewJobId'])
    result = copy.deepcopy(job['result'])
    _, records = _after_cells(result, j['snapshot'])
    expected = {r['name']: r['sha256'] for r in result['fileHashes']}
    artifacts = {a['name']: a for a in job['artifacts']}
    if set(expected) != set(artifacts) or any(expected.get(r['name']) != r['sha256'] for r in records):
        raise s.AppError('FOLLOW_PREVIEW_INVALID', '미리보기 산출물 목록이 다릅니다.', 424)
    root = s.artifact_directory(job['jobId']) / job['attemptId']
    # Verify every artifact before copying, and every cell before registration.
    contents = {}
    for name, sha in expected.items():
        data = _safe_file(root, name).read_bytes()
        if sha != artifacts[name]['sha256'] or s.digest(data) != sha:
            raise s.AppError('FOLLOW_PREVIEW_HASH', '미리보기 파일이 변경되었습니다. 다시 미리보기를 만드세요.', 424)
        contents[name] = data
    _decode_cells(result, contents)
    for name, data in contents.items():
        s.atomic_bytes(out / name, data)
    result.update(previewJobId=job['jobId'], files=list(contents), status='needs_review')
    result.pop('publicationHashes', None)
    return result


def _decode_cells(result, contents):
    cells = []
    for record in result['cellFiles']['after']:
        data = contents[record['name']]
        if s.digest(data) != record['sha256']:
            raise s.AppError('FOLLOW_PREVIEW_HASH', '미리보기 PNG 해시가 다릅니다.', 424)
        try:
            with Image.open(io.BytesIO(data)) as im:
                if im.format != 'PNG' or im.size != (result['preview']['width'], result['preview']['height']):
                    raise s.AppError('FOLLOW_PREVIEW_INVALID', '미리보기 PNG 크기·형식이 다릅니다.', 424)
                if max(im.size) > 1024:
                    raise s.AppError('CLIP_TOOLS_SIZE', '출력 셀은 1024×1024 이하여야 합니다.', 413)
                cells.append(im.convert('RGBA'))
        except (OSError, ValueError) as exc:
            raise s.AppError('FOLLOW_PREVIEW_INVALID', '미리보기 PNG를 읽을 수 없습니다.', 424) from exc
    _check_cells(cells, result['preview']['durationsMs'])
    return cells


def _point(value):
    return dict(value) if isinstance(value, dict) else {'x': value[0], 'y': value[1]}


def _candidate(source):
    # Approval belongs to the old pixels/version, retained only in lineage.
    return {key: copy.deepcopy(value) for key, value in source.items()
            if not key.startswith(('review', 'approval', 'approved'))}


def publish_follow(j, result, directory, snapshot, connection):
    """Called inside the revision-checked publication transaction, never by preview."""
    validate_apply(snapshot, {'previewJobId': result['previewJobId']}, connection)
    approved_preview = s.get_job(result['previewJobId'], connection)['result']
    for key in ('version', 'tool', 'source', 'sourceProjectRevision', 'settings', 'report', 'preview', 'cellFiles', 'fileHashes'):
        if result.get(key) != approved_preview.get(key):
            raise s.AppError('FOLLOW_PREVIEW_INVALID', '저장 결과가 성공한 미리보기와 다릅니다.', 424)
    original, records = _after_cells(result, snapshot)
    contents = {r['name']: _safe_file(directory, r['name']).read_bytes() for r in records}
    _decode_cells(result, contents)
    source = result['source']
    width, height = result['preview']['width'], result['preview']['height']
    group_id, group_revision = s.uid(), s.uid()
    target = _point(source['anchors'][0])
    group = dict(alignmentGroupId=group_id, groupRevisionId=group_revision, frameVersionIds=[],
                 mode='preserve-source-scale', sharedScale=1, cell={'width': width, 'height': height, 'edge': 0},
                 targetAnchor=target, bodyMeasurement=None, resampler='nearest', roundingVersion='js-round-v1')
    assets, frames, alignments, occurrences = [], [], {}, []
    by_frame = {f['frameVersionId']: f for f in snapshot['frames']}
    lineage = {'kind': 'clip-follow', 'version': VERSION, 'source': copy.deepcopy(source),
               'settings': copy.deepcopy(result['settings']), 'report': copy.deepcopy(result['report']),
               'previewJobId': result['previewJobId'], 'preview': copy.deepcopy(result['preview']),
               'previewFiles': copy.deepcopy(result['fileHashes'])}
    for index, (record, slot) in enumerate(zip(records, original['occurrences'])):
        previous = by_frame[slot['frameVersionId']]
        old_alignment = snapshot['alignments'][previous['frameVersionId']]
        old_group = next(g for g in snapshot['alignmentGroups'] if previous['frameVersionId'] in g['frameVersionIds'])
        provenance = {**lineage, 'parentAssetId': previous['imageAssetId'], 'sourceFrame': copy.deepcopy(previous),
                      'sourceOccurrence': copy.deepcopy(slot), 'sourceAlignment': copy.deepcopy(old_alignment),
                      'sourceGroup': copy.deepcopy(old_group), 'previewCell': copy.deepcopy(record)}
        asset = s.register_asset(contents[record['name']], f'흔들림-{index + 1}.png', 'derived', provenance,
                                 c=connection, project_id=j['projectId'])
        assets.append(asset)
        fid = s.uid()
        frame = {**_candidate(previous), 'frameId': s.uid(), 'frameVersionId': fid,
                 'parentFrameVersionId': previous['frameVersionId'], 'rawAssetId': asset['assetId'], 'imageAssetId': asset['assetId'],
                 'sourceRect': {'x': 0, 'y': 0, 'width': width, 'height': height},
                 'sourceToFrameTransform': {'scaleX': 1, 'scaleY': 1, 'offsetX': 0, 'offsetY': 0},
                 'extractionVersion': VERSION, 'nativeScaleGroupId': group_id, 'review': 'pending',
                 'hidden': False, 'sourceProcessing': provenance}
        frames.append(frame)
        group['frameVersionIds'].append(fid)
        anchor = _point(source['anchors'][index])
        alignment = dict(frameVersionId=fid, groupRevisionId=group_revision, sourceAnchor=anchor,
                         anchorSpace='crop', method='automatic', contactMode=old_alignment.get('contactMode', 'grounded'),
                         authoredOffsetPx={'x': anchor['x'] - target['x'], 'y': anchor['y'] - target['y']}, approval='pending')
        if alignment['contactMode'] == 'airborne':
            alignment['rootAnchor'] = dict(anchor)
        alignments[fid] = alignment
        occurrences.append(dict(occurrenceId=s.uid(), frameVersionId=fid, durationMs=slot['durationMs'],
                                timingMode=slot.get('timingMode', 'explicit'), pixelEdits=[],
                                transform={'dx': 0, 'dy': 0, 'scaleX': 1, 'scaleY': 1, 'rotationDeg': 0,
                                           'shearX': 0, 'shearY': 0, 'flipX': False, 'flipY': False}))
    clip = {**_candidate(original), 'clipId': s.uid(), 'clipRevisionId': s.uid(),
            'name': original['name'] + ' · 부위 흔들림 · 검수 대기', 'review': 'pending', 'occurrences': occurrences,
            'sourceProcessing': {**lineage, 'sourceClip': copy.deepcopy(original)}}
    result.update(assets=assets, frames=frames, alignmentGroups=[group], alignments=alignments, clips=[clip],
                  clipId=clip['clipId'], frameVersionIds=group['frameVersionIds'], status='needs_review')
