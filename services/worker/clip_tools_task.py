"""Local clip diagnostics and immutable, hash-checked follow publication."""
from __future__ import annotations

import copy
import io
import json
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
    if preview['operation'] not in ('preview_follow', 'preview_restore', 'compare_clips') or preview['status'] != 'succeeded' or not preview.get('published'):
        raise s.AppError('FOLLOW_PREVIEW_INCOMPLETE', '성공한 흔들림 미리보기만 저장할 수 있습니다.', 409)
    result = preview.get('result', {})
    source = result.get('source', {})
    if result.get('version') != VERSION or result.get('tool') not in ('follow', 'restore', 'compare') or source.get('projectId') != snapshot['projectId']:
        raise s.AppError('FOLLOW_PREVIEW_INVALID', '미리보기 출처가 유효하지 않습니다.', 424)
    if result.get('report', {}).get('canApply') is False:
        raise s.AppError('CLIP_TOOL_UNCERTAIN', '대응 또는 복원을 증명하지 못한 결과는 저장할 수 없습니다.', 409)
    if result.get('policy'):
        from adapters.spritegen.clip_comparison import policy
        if result['policy'] != policy():
            raise s.AppError('CLIP_TOOL_POLICY', '처리 정책이 바뀌었습니다. 다시 미리보기하세요.', 409)
    s.check_revision(snapshot, source.get('projectRevision'))
    if result.get('sourceProjectRevision') != snapshot['revision'] or preview['inputRevision'] != snapshot['revision']:
        raise s.AppError('REVISION_CONFLICT', '프로젝트가 바뀌었습니다. 흔들림 미리보기를 다시 만드세요.', 409)
    clip = next((cl for cl in snapshot['clips'] if cl['clipId'] == source.get('clipId')), None)
    if not clip or clip['clipRevisionId'] != source.get('clipRevisionId'):
        raise s.AppError('FOLLOW_PREVIEW_INVALID', '미리보기 동작 버전이 다릅니다.', 409)
    from adapters.spritegen import clip_comparison as comparison, clip_tools
    report = result.get('report', {})
    if result['tool'] in ('restore', 'compare'):
        restoration = result['tool'] == 'restore'
        if (result.get('policy') != comparison.policy() or report.get('bridge_policy') != comparison.policy()
                or report.get('schema_version') != (4 if restoration else 1)
                or report.get('metric_version') != ('source-restoration-v5' if restoration else 'same-sample-defects-v1')
                or report.get('canApply') is not True or report.get('verdict') not in ('improved', 'non_regressing')
                or restoration and (report.get('comparison_schema') != 6 or report.get('policy_version') != comparison.policy()['policy_version']
                    or report.get('comparison', {}).get('schema_version') != 6
                    or any(report.get('comparison', {}).get(k) != report.get(k) for k in ('metric_version', 'policy_version', 'verdict', 'source', 'origin', 'baseline', 'candidate')))):
            raise s.AppError('CLIP_TOOL_POLICY', '증거 형식·정책·판정이 유효하지 않습니다.', 424)
    cells, durations, actual_source = clip_tools.render_clip(snapshot, {'clipId': clip['clipId'], 'clipRevisionId': clip['clipRevisionId']}, s.asset_path)
    if any(source.get(k) != value for k, value in actual_source.items() if k != 'pixelHashes'):
        raise s.AppError('FOLLOW_PREVIEW_INVALID', '미리보기의 원본 좌표·슬롯 출처가 현재 동작과 다릅니다.', 424)
    if source.get('pixelHashes') and source['pixelHashes'] != comparison.pixels(cells):
        raise s.AppError('FOLLOW_PREVIEW_HASH', '미리보기 입력 픽셀이 변경되었습니다.', 424)
    if result['settings'].get('readOnClipId'):
        origin_clip = next(c for c in snapshot['clips'] if c['clipId'] == result['settings']['readOnClipId'])
        origin_cells, _, _ = clip_tools.render_clip(snapshot, {'clipId': origin_clip['clipId'], 'clipRevisionId': origin_clip['clipRevisionId']}, s.asset_path)
        if comparison.pixels(origin_cells) != source.get('readOnSource', {}).get('pixelHashes'):
            raise s.AppError('FOLLOW_PREVIEW_HASH', '영역을 읽은 동작이 변경되었습니다.', 424)
    if result['tool'] in ('restore', 'compare'):
        try:
            read = comparison.read_evidence if result['tool'] == 'restore' else comparison.read_comparison_evidence
            evidence, _, _, _ = read(snapshot, clip, cells, durations)
            after = _decode_cells(result, _preview_contents(preview, result, snapshot))
            actual = dict(source=evidence['source'], origin=evidence['origin'],
                          baseline=comparison.identity(cells, durations, evidence['basis']),
                          candidate=comparison.identity(after, durations, evidence['basis']))
            if result['tool'] == 'restore' and (actual['baseline'] == actual['candidate'] or report['verdict'] != 'improved'):
                raise ValueError('unchanged-restoration-is-not-an-accepted-proposal')
            if result['tool'] == 'compare':
                candidate = next(c for c in snapshot['clips'] if c['clipId'] == result['settings']['candidateClipId'])
                selected, times, _ = clip_tools.render_clip(snapshot, {'clipId': candidate['clipId'], 'clipRevisionId': candidate['clipRevisionId']}, s.asset_path)
                chosen, _, _, _ = comparison.read_comparison_evidence(snapshot, candidate, selected, times)
                if (chosen['source'] != evidence['source'] or chosen['origin'] != evidence['origin']
                        or comparison.identity(selected, times, chosen['basis']) != actual['candidate']):
                    raise ValueError('candidate-source-or-pixels-changed')
            reports = [report, report['comparison']] if result['tool'] == 'restore' else [report]
            if any(row.get(key) != value for row in reports for key, value in actual.items()):
                raise ValueError('comparison-identity-does-not-match-actual-cells')
        except (ValueError, KeyError, TypeError, OSError) as exc:
            raise s.AppError('CLIP_TOOL_SOURCE', '원본·최초 결과 증거가 변경되었습니다. 다시 미리보기하세요.', 424) from exc
    else:
        _preview_contents(preview, result, snapshot)
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
    cells, durations, source = clip_tools.render_clip(snapshot, params, s.asset_path,
        allow_render_errors=j['operation'] in ('preview_restore', 'compare_clips'))
    _check_cells(cells, durations)
    clip = next(cl for cl in snapshot['clips'] if cl['clipId'] == source['clipId'])
    files, before, animation, strip = _write_cells(cells, durations, clip['loop'], out, 'before', source)
    preview = {'width': cells[0].width, 'height': cells[0].height, 'frameCount': len(cells),
               'durationsMs': durations, 'before': animation, 'beforeStrip': strip, 'firstFrame': before[0]['name']}
    from adapters.spritegen import clip_comparison as comparison
    result = {'tool': {'preview_follow': 'follow', 'preview_restore': 'restore', 'compare_clips': 'compare'}.get(j['operation'], 'handed'), 'version': VERSION,
              'source': source, 'sourceProjectRevision': snapshot['revision'], 'settings': params,
              'policy': comparison.policy(), 'preview': preview, 'cellFiles': {'before': before}, 'files': files}
    source['stripSha256'] = s.digest((out / strip).read_bytes())
    if j['operation'] in ('preview_follow', 'preview_restore', 'compare_clips'):
        if j['operation'] == 'preview_restore':
            after, report = comparison.restore(snapshot, clip, cells, durations)
            report['sourceStatus'] = comparison.source_status(snapshot, clip)
            if source.get('renderErrors'):
                report.update(verdict='unknown', canApply=False, reasons=['canonical-render-errors'])
                report['comparison'].update(verdict='unknown', reasons=['canonical-render-errors'])
        elif j['operation'] == 'compare_clips':
            candidate_params = {'clipId': params['candidateClipId'], 'clipRevisionId': params['candidateClipRevisionId']}
            candidate_cells, candidate_durations, candidate_source = clip_tools.render_clip(snapshot, candidate_params, s.asset_path, allow_render_errors=True)
            candidate_clip = next(c for c in snapshot['clips'] if c['clipId'] == params['candidateClipId'])
            try:
                e, _, _, _ = comparison.read_comparison_evidence(snapshot, clip, cells, durations)
                ce, _, _, _ = comparison.read_comparison_evidence(snapshot, candidate_clip, candidate_cells, candidate_durations)
                basis, candidate_basis = e['basis'], ce['basis']
                comparable = e['source'] == ce['source'] and e['origin'] == ce['origin'] and not source.get('renderErrors') and not candidate_source.get('renderErrors')
            except (ValueError, KeyError, TypeError, OSError):
                basis = candidate_basis = {}; comparable = False
            report = comparison.compare_cells(cells, candidate_cells, durations, candidate_durations, basis, candidate_basis, comparable=comparable)
            if comparable: report.update(source=e['source'], origin=e['origin'])
            report['canApply'] = comparable and report['verdict'] in ('improved', 'non_regressing')
            after = candidate_cells if len(candidate_cells) == len(cells) and candidate_cells[0].size == cells[0].size and candidate_durations == durations else [c.copy() for c in cells]
            report['candidateClipId'] = candidate_clip['clipId']
        elif params.get('readOnClipId'):
            origin_clip = next(c for c in snapshot['clips'] if c['clipId'] == params['readOnClipId'])
            origin_cells, origin_durations, origin_source = clip_tools.render_clip(snapshot,
                {'clipId': origin_clip['clipId'], 'clipRevisionId': origin_clip['clipRevisionId']}, s.asset_path)
            source['readOnSource'] = origin_source
            origin_files, _, _, origin_strip = _write_cells(origin_cells, origin_durations, origin_clip['loop'], out, 'read-on', origin_source)
            files.extend(origin_files)
            strip_bytes = (out / origin_strip).read_bytes(); sha = s.digest(strip_bytes)
            try:
                if params.get('readOn') and params['readOn'] != sha: raise ValueError('read-on-strip-hash-mismatch')
                motion = clip_tools.transported_reading(snapshot, clip, cells, durations, origin_clip, origin_cells, origin_durations, strip_bytes)
                after, report = clip_tools.follow_frames(cells, durations, params, motion=motion)
                report['readOn'] = {'relation': 'transported', 'sha256': sha, 'sourceCells': motion[4]}
            except (ValueError, KeyError, TypeError, OSError, SystemExit) as exc:
                after = [c.copy() for c in cells]
                report = dict(canApply=False, gainRequested=params['gain'], gainApplied=0, foldLimited=False,
                    unchanged=True, readOn={'relation': 'uncertain', 'reason': str(exc)})
        elif params.get('readOn') and params['readOn'] != source['stripSha256']:
            after = [c.copy() for c in cells]
            report = dict(canApply=False, gainRequested=params['gain'], gainApplied=0, foldLimited=False,
                          unchanged=True, readOn={'relation': 'uncertain', 'reason': 'strip-hash-or-sample-mapping-unverified'})
        else:
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
    contents = _preview_contents(job, result, j['snapshot'])
    for name, data in contents.items():
        s.atomic_bytes(out / name, data)
    result.update(previewJobId=job['jobId'], files=list(contents), status='needs_review')
    result.pop('publicationHashes', None)
    return result


def _preview_contents(job, result, snapshot):
    """Bind DB metadata to verified bytes at API admission, execution and publication."""
    _, records = _after_cells(result, snapshot)
    expected = {r['name']: r['sha256'] for r in result['fileHashes']}
    artifacts = {a['name']: a for a in job['artifacts']}
    if (len(expected) != len(result['fileHashes']) or set(expected) != set(artifacts)
            or any(expected.get(r['name']) != r['sha256'] for r in records)):
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
    try:
        metadata = json.loads(contents['report.json'])
        recorded = {k: v for k, v in result.items() if k not in ('fileHashes', 'publicationHashes', 'files')}
        if metadata != recorded: raise ValueError('preview-metadata-does-not-match-report-artifact')
    except (ValueError, KeyError, TypeError) as exc:
        raise s.AppError('FOLLOW_PREVIEW_INVALID', '미리보기 보고서와 보존 산출물의 내용이 다릅니다.', 424) from exc
    return contents


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
    for key in ('version', 'tool', 'source', 'sourceProjectRevision', 'settings', 'report', 'preview', 'cellFiles', 'fileHashes', 'policy'):
        if result.get(key) != approved_preview.get(key):
            raise s.AppError('FOLLOW_PREVIEW_INVALID', '저장 결과가 성공한 미리보기와 다릅니다.', 424)
    original, records = _after_cells(result, snapshot)
    contents = {r['name']: _safe_file(directory, r['name']).read_bytes() for r in records}
    after_cells = _decode_cells(result, contents)
    source = result['source']
    width, height = result['preview']['width'], result['preview']['height']
    group_id, group_revision = s.uid(), s.uid()
    target = _point(source['anchors'][0])
    group = dict(alignmentGroupId=group_id, groupRevisionId=group_revision, frameVersionIds=[],
                 mode='preserve-source-scale', sharedScale=1, cell={'width': width, 'height': height, 'edge': 0},
                 targetAnchor=target, bodyMeasurement=None, resampler='nearest', roundingVersion='js-round-v1')
    assets, frames, alignments, occurrences = [], [], {}, []
    by_frame = {f['frameVersionId']: f for f in snapshot['frames']}
    lineage = {'kind': 'clip-' + result['tool'], 'version': VERSION, 'source': copy.deepcopy(source),
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
        asset = s.register_asset(contents[record['name']], f"{result['tool']}-{index + 1}.png", 'derived', provenance,
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
    if original.get('comparisonEvidence'):
        from adapters.spritegen import clip_comparison as comparison, clip_tools
        evidence = copy.deepcopy(original['comparisonEvidence'])
        if result['tool'] == 'compare':
            selected = next(c for c in snapshot['clips'] if c['clipId'] == result['report']['candidateClipId'])
            evidence = copy.deepcopy(selected['comparisonEvidence'])
        if result['tool'] == 'restore':
            evidence['applied'] = result['report']['applied']
        elif result['tool'] == 'follow':
            try:
                before, durations, _ = clip_tools.render_clip(snapshot, original, s.asset_path)
                comparison.read_comparison_evidence(snapshot, original, before, durations)
                if comparison.pixels(after_cells) != comparison.pixels(before):
                    evidence['unsupported'] = 'follow-source-warp-unverified'
                    evidence['followProof'] = dict(schemaVersion=1, parent=comparison.saved_render(snapshot, original),
                                                  settings=copy.deepcopy(result['settings']))
                    if result['settings'].get('readOnClipId'):
                        reading = next(c for c in snapshot['clips'] if c['clipId'] == result['settings']['readOnClipId'])
                        evidence['followProof']['reading'] = comparison.saved_render(snapshot, reading)
            except (ValueError, KeyError, TypeError, OSError, s.AppError):
                evidence['unsupported'] = evidence.get('unsupported') or 'parent-source-evidence-unverified'
                evidence.pop('followProof', None)
        evidence['currentPixels'] = comparison.pixels(after_cells)
        evidence['slotIds'] = [o['occurrenceId'] for o in occurrences]
        evidence['geometry'] = comparison.geometry({**snapshot, 'frames': snapshot['frames'] + frames,
            'alignmentGroups': snapshot['alignmentGroups'] + [group], 'alignments': {**snapshot['alignments'], **alignments}}, clip)
        clip['comparisonEvidence'] = evidence
    label = {'follow': '부위 흔들림', 'restore': '원본 복원', 'compare': '비교 선택'}[result['tool']]
    clip['name'] = original['name'] + ' · ' + label + ' · 검수 대기'
    clip['sourceProcessing']['kind'] = 'clip-' + result['tool']
    result.update(assets=assets, frames=frames, alignmentGroups=[group], alignments=alignments, clips=[clip],
                  clipId=clip['clipId'], frameVersionIds=group['frameVersionIds'], status='needs_review')
