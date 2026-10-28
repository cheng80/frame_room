"""Canonical-cell bridge for source restoration; receipts never promote edited pixels to source."""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import tempfile

from PIL import Image

from services.api import store as s

BRIDGE = 'frame-room-canonical-source-v1'


def policy():
    from alignment.pipeline import _engine
    r = _engine('video.restoration')
    paths = [Path(__file__), *[Path(__file__).with_name(n + '.py') for n in ('clip_tools', 'video_normalization', 'video_finish')],
             Path(__file__).resolve().parents[2] / 'alignment' / 'pipeline.py',
             Path(__file__).resolve().parents[2] / 'services' / 'worker' / 'clip_tools_task.py']
    root = Path(r.__file__).parent
    paths += [root / (n + '.py') for n in ('restoration', 'compare', 'source', 'repair', 'follow', 'interpolation_quality')]
    return dict(bridge=BRIDGE, metric_version=r.METRIC, policy_version=r.POLICY,
                repair_schema=r.REPAIR_SCHEMA, comparison_schema=r.COMPARISON_SCHEMA,
                cap_mode='exact-raw-projection-else-protect',
                implementation_sha256=s.digest(b''.join(p.read_bytes() for p in paths)))


def hashed(value):
    return s.digest(s.dumps(value).encode())


def pixels(cells):
    return [s.digest(im.convert('RGBA').tobytes()) for im in cells]


def identity(cells, durations, basis):
    record = dict(pixels=pixels(cells), durationsMs=durations, basis=basis)
    return dict(id=hashed(record), sha256=hashed(record), **record)


def _asset(snapshot, record):
    asset = next((a for a in snapshot['assets'] if a['assetId'] == record['assetId']), None)
    if not asset or asset['sha256'] != record['sha256']:
        raise ValueError('source-asset-identity-mismatch')
    blob = s.asset_path(asset['assetId']).read_bytes()
    if s.digest(blob) != record['sha256']:
        raise ValueError('source-asset-bytes-mismatch')
    with Image.open(io.BytesIO(blob)) as im:
        return im.convert('RGBA')


def _record(im, name, provenance, assets):
    buf = io.BytesIO(); im.save(buf, format='PNG')
    a = s.register_asset(buf.getvalue(), name, 'derived', provenance)
    assets.append(a)
    return dict(assetId=a['assetId'], sha256=a['sha256'])


def geometry(snapshot, clip):
    frames = {f['frameVersionId']: f for f in snapshot['frames']}
    rows = []
    for slot in clip['occurrences']:
        frame = frames[slot['frameVersionId']]
        group = next(g for g in snapshot['alignmentGroups'] if frame['frameVersionId'] in g['frameVersionIds'])
        alignment = snapshot['alignments'][frame['frameVersionId']]
        rows.append(dict(frame={k: frame.get(k) for k in ('sourceRect', 'sourceToFrameTransform', 'sourceFrameIndex', 'sourceTimeMs', 'interpolated', 'interpolation')},
                         group={k: group.get(k) for k in ('mode', 'sharedScale', 'cell', 'targetAnchor', 'bodyMeasurement', 'resampler', 'roundingVersion')},
                         alignment={k: alignment.get(k) for k in ('sourceAnchor', 'anchorSpace', 'contactMode', 'authoredOffsetPx', 'rootAnchor')},
                         transform=slot.get('transform'), pixelEdits=slot.get('pixelEdits')))
    return hashed(rows)


def source_status(snapshot, clip):
    """Legacy source verification is independent of an unsupported legacy origin."""
    if clip.get('comparisonEvidence'):
        e = clip['comparisonEvidence']
        return dict(source='recorded-canonical-source', sourceId=e.get('source', {}).get('id'),
                    origin='recorded-immutable-origin', originId=e.get('origin', {}).get('id'))
    status = dict(source='unknown', origin='unsupported-legacy', reasons=['legacy-origin-not-recorded'])
    try:
        from services.api import videos
        from .video_processing import _valid_manifest
        with s.connect() as db:
            jobs = [json.loads(row[0]) for row in db.execute("SELECT body FROM jobs WHERE project_id=? AND operation IN ('generate_video','process_video')", (snapshot['projectId'],))]
        job = next(j for j in jobs if j.get('result', {}).get('clipId') == clip['clipId'] and j.get('published'))
        video = next(v for v in snapshot.get('videos', []) if v['videoId'] == job['result'].get('videoId'))
        if s.digest(videos.path_for(video['videoId']).read_bytes()) != video['sha256']: raise ValueError('legacy-video-hash-mismatch')
        attempt = (s.artifact_directory(job['jobId']) / job['attemptId']).resolve()
        root = s.project_folder(snapshot['projectId']).resolve()
        if not attempt.is_relative_to(root): raise ValueError('legacy-output-outside-project')
        complete = sorted(attempt.glob('processing/extractions/*/complete.json'))
        if len(complete) != 1 or not complete[0].resolve().is_relative_to(attempt): raise ValueError('legacy-extraction-missing')
        record = json.loads(complete[0].read_bytes()); manifest = record.get('manifest', [])
        names = [m['file'] for m in manifest]
        count = video['frameCount']
        if (len(set(names)) != len(names) or sum('/raw/' in n for n in names) != count
                or sum('/keyed/' in n for n in names) != count
                or not _valid_manifest((attempt / 'processing').resolve(), manifest)):
            raise ValueError('legacy-full-extraction-unverified')
        if record.get('options', {}).get('sourceSha256') != video['sha256']:
            raise ValueError('legacy-extraction-video-mismatch')
        status.update(source='verified-full-extraction', sourceId=hashed(dict(video=video['sha256'], manifest=manifest)),
                      rawFrames=count, keyedFrames=count, completeSha256=s.digest(complete[0].read_bytes()))
    except (StopIteration, KeyError, TypeError, ValueError, OSError) as exc:
        status['reasons'].append(str(exc) or 'legacy-source-evidence-unavailable')
    return status


def capture_video(snapshot, clip, cells, rendered, items, assets, video, normalization, finish, extraction, out, *, selection=None):
    """Retain exact original keyed projections at the delivered geometry, outside disposable caches."""
    from .video_finish import finish_frames
    from alignment.pipeline import render_occurrence, _engine
    extraction = {**copy.deepcopy(extraction.get('sourceReceipt', {})),
                  **{k: copy.deepcopy(extraction.get(k)) for k in ('spill', 'options', 'manifest') if k in extraction}}
    extraction['options'] = {k: v for k, v in extraction.get('options', {}).items() if k != 'referencePath'}
    extraction['spill'] = {k: v for k, v in (extraction.get('spill') or {}).items() if k != 'reference'}
    extraction['key'] = extraction.get('options', {}).get('key')
    rect = normalization['sourceRect']
    box = (rect['x'], rect['y'], rect['x'] + rect['width'], rect['y'] + rect['height'])
    size = normalization['width'], normalization['height']
    source_paths, crops, keyed = [], [], []
    directory = out / 'source-projection'; directory.mkdir(parents=True, exist_ok=True)
    for i, item in enumerate(items):
        with Image.open(item.get('originalKeyedPath', item['keyedPath'])) as im:
            original = im.convert('RGBA'); crop = original.crop(box)
        crops.append(crop)
        keyed.append(_record(original, f'복원 원본 keyed {i + 1}.png', {'kind': 'video-source-keyed', 'sourceVideoId': video['videoId']}, assets))
        scaled = (crop.resize(size, Image.Resampling.LANCZOS) if finish['mode'] == 'gif'
                  else _engine('video.loop').resize_cell(crop, size))
        image = Image.new('RGBA', size); image.alpha_composite(scaled)
        path = directory / f'{i:03d}.png'; image.save(path); source_paths.append(path)
    finished, _ = finish_frames(source_paths, directory / 'finished', mode=finish['mode'],
                              cell_width=finish['cellWidth'], cell_height=finish['cellHeight'])
    references = []
    frames = {f['frameVersionId']: f for f in snapshot['frames']}
    for slot, path in zip(clip['occurrences'], finished):
        fid = slot['frameVersionId']; frame = frames[fid]
        with Image.open(path) as im:
            a = _record(im.convert('RGBA'), '복원용 마무리.png', {'kind': 'video-source-projection', 'sourceVideoId': video['videoId']}, assets)
        shadow = {**snapshot, 'frames': [{**f, 'imageAssetId': a['assetId']} if f['frameVersionId'] == fid else f for f in snapshot['frames']],
                  'assets': list({a['assetId']: a for a in snapshot['assets'] + assets}.values())}
        references.append(render_occurrence(shadow, clip, slot, s.asset_path, include_outline=False)[0])
    durations = [o['durationMs'] for o in clip['occurrences']]
    basis = dict(cell=list(cells[0].size), anchors=[qa['anchor'] for _, qa in rendered],
                 facing=clip.get('facing'), direction=clip.get('direction'), projectionGeometry=geometry(snapshot, clip),
                 sourceRange=dict(startFrame=(selection or {}).get('startFrame', 0),
                                  endFrame=(selection or {}).get('endFrame', video['frameCount'])),
                 sourceRect=rect, normalization=normalization, finish=finish, loop=clip['loop'],
                 samples=[dict(index=f['sourceFrameIndex'], timeMs=f['sourceTimeMs'],
                               interpolation=f.get('interpolation'), processing=f.get('processing')) for f in items])
    source_records = [_record(im, f'복원 원본 셀 {i + 1}.png', {'kind': 'video-source-cell', 'sourceVideoId': video['videoId']}, assets) for i, im in enumerate(references)]
    origin_records = [_record(im, f'최초 복원 전 셀 {i + 1}.png', {'kind': 'video-origin-cell', 'sourceVideoId': video['videoId']}, assets) for i, im in enumerate(cells)]
    by_asset = {a['assetId']: a for a in snapshot['assets']}
    raw_records = [dict(assetId=frames[o['frameVersionId']]['rawAssetId'], sha256=by_asset[frames[o['frameVersionId']]['rawAssetId']]['sha256']) for o in clip['occurrences']]
    prepared_id = video.get('provenance', {}).get('referenceAssetId')
    prepared = None
    if prepared_id:
        prepared_asset = next(a for a in s.get_project(snapshot['projectId'])['assets'] if a['assetId'] == prepared_id)
        prepared = dict(assetId=prepared_id, sha256=prepared_asset['sha256'])
    for lane, images in (('source', references), ('origin', cells)):
        (directory / lane).mkdir(exist_ok=True)
        for i, image in enumerate(images): image.save(directory / lane / f'{i:03d}.png')
    source_id = identity(references, durations, basis)
    source_id['videoSha256'] = video['sha256']
    source_id['keyedSha256'] = [r['sha256'] for r in keyed]
    source_id['rawSha256'] = [r['sha256'] for r in raw_records]
    source_id['preparedSha256'] = prepared['sha256'] if prepared else None
    source_id['extractionSha256'] = hashed(extraction)
    source_id['id'] = source_id['sha256'] = hashed({k: v for k, v in source_id.items() if k not in ('id', 'sha256')})
    clip['comparisonEvidence'] = dict(schemaVersion=1, policy=policy(), source=source_id,
        origin=identity(cells, durations, basis), basis=basis, durationsMs=durations,
        sourceCells=source_records, originCells=origin_records, keyedFrames=keyed, rawFrames=raw_records, preparedImage=prepared,
        slotIds=[o['occurrenceId'] for o in clip['occurrences']],
        videoId=video['videoId'], extraction=extraction, applied=[],
        currentPixels=pixels(cells), geometry=geometry(snapshot, clip), facing=clip.get('facing'), key=extraction.get('key'),
        projection=dict(frames=copy.deepcopy([frames[o['frameVersionId']] for o in clip['occurrences']]),
                        groups=copy.deepcopy(snapshot['alignmentGroups']), alignments=copy.deepcopy(snapshot['alignments']),
                        clip=copy.deepcopy(clip)),
        unsupported='interpolated-source-sample' if any(f.get('interpolated') for f in items) else None)
    s.atomic_bytes(directory / 'source-manifest.json', s.dumps(clip['comparisonEvidence']).encode())


def read_evidence(snapshot, clip, cells, durations, *, comparison=False, depth=0):
    e = clip.get('comparisonEvidence')
    if not isinstance(e, dict):
        raise ValueError('source-unknown/origin-unsupported-legacy')
    if e.get('schemaVersion') != 1 or e.get('policy') != policy():
        raise ValueError('source-policy-or-schema-mismatch')
    if e.get('unsupported') and not (comparison and e['unsupported'] == 'follow-source-warp-unverified'):
        raise ValueError(e['unsupported'])
    if any(len(e.get(key, [])) != len(cells) for key in ('sourceCells', 'originCells', 'keyedFrames', 'rawFrames', 'durationsMs', 'currentPixels')):
        raise ValueError('source-sample-count-mismatch')
    if durations != e['durationsMs'] or pixels(cells) != e['currentPixels']:
        raise ValueError('baseline-edited-or-schedule-changed')
    if geometry(snapshot, clip) != e.get('geometry'):
        raise ValueError('baseline-coordinate-or-sample-mapping-changed')
    basis = e['basis']
    if (e.get('key') != e['extraction'].get('key') or e.get('facing') != basis.get('facing')
            or clip.get('facing') != basis.get('facing') or clip.get('direction') != basis.get('direction')
            or e['projection']['clip'].get('facing') != basis.get('facing')):
        raise ValueError('source-key-or-facing-identity-mismatch')
    if list(cells[0].size) != basis['cell'] or clip['loop'] != basis['loop']:
        raise ValueError('baseline-coordinate-or-playback-changed')
    # Reordering even identical drawings cannot change their source time unnoticed.
    lineage = e.get('slotIds')
    if lineage and lineage != [o['occurrenceId'] for o in clip['occurrences']]:
        raise ValueError('baseline-sample-order-changed')
    source_cells = [_asset(snapshot, r) for r in e['sourceCells']]
    origin = [_asset(snapshot, r) for r in e['originCells']]
    keyed = [_asset(snapshot, r) for r in e['keyedFrames']]
    for record in e['rawFrames']: _asset(snapshot, record)
    if e['preparedImage']: _asset(snapshot, e['preparedImage'])
    if identity(origin, durations, basis) != e['origin']:
        raise ValueError('origin-changed')
    expected = identity(source_cells, durations, basis)
    expected.update(videoSha256=e['source']['videoSha256'], keyedSha256=[r['sha256'] for r in e['keyedFrames']],
                    rawSha256=[r['sha256'] for r in e['rawFrames']], preparedSha256=e['preparedImage']['sha256'] if e['preparedImage'] else None,
                    extractionSha256=hashed(e['extraction']))
    expected['id'] = expected['sha256'] = hashed({k: v for k, v in expected.items() if k not in ('id', 'sha256')})
    if expected != e['source']:
        raise ValueError('source-changed')
    # Reproject the retained keyed bytes; a supplied source-cell receipt alone proves no correspondence.
    from .video_finish import finish_frames
    from alignment.pipeline import render_occurrence, _engine
    projection = e['projection']; norm = basis['normalization']; finish = basis['finish']; rect = norm['sourceRect']
    box = (rect['x'], rect['y'], rect['x'] + rect['width'], rect['y'] + rect['height'])
    size = norm['width'], norm['height']
    with tempfile.TemporaryDirectory(prefix='frame-room-source-proof-') as tmp:
        folder = Path(tmp); paths = []
        for i, original in enumerate(keyed):
            crop = original.crop(box)
            scaled = crop.resize(size, Image.Resampling.LANCZOS) if finish['mode'] == 'gif' else _engine('video.loop').resize_cell(crop, size)
            canvas = Image.new('RGBA', size); canvas.alpha_composite(scaled)
            path = folder / f'{i:03d}.png'; canvas.save(path); paths.append(path)
        finished, _ = finish_frames(paths, folder / 'finished', mode=finish['mode'], cell_width=finish['cellWidth'],
            cell_height=finish['cellHeight'], save_metadata=lambda path, value: path.write_text(s.dumps(value)))
        shadow = {**snapshot, 'frames': projection['frames'], 'alignmentGroups': projection['groups'], 'alignments': projection['alignments']}
        if geometry(shadow, projection['clip']) != basis['projectionGeometry']:
            raise ValueError('source-projection-geometry-changed')
        source_paths = {f['imageAssetId']: path for f, path in zip(projection['frames'], finished)}
        source_assets = {a['assetId']: a for a in snapshot['assets']}
        for aid, path in source_paths.items():
            source_assets[aid] = {**source_assets[aid], **s.validate_image(path.read_bytes(), 'projection.png'), 'sha256': s.digest(path.read_bytes())}
        shadow['assets'] = list(source_assets.values())
        projected = [render_occurrence(shadow, projection['clip'], slot, lambda aid: source_paths[aid], include_outline=False)[0]
                     for slot in projection['clip']['occurrences']]
        if pixels(projected) != pixels(source_cells): raise ValueError('source-projection-not-reproduced')
    from services.api import videos
    video = next((v for v in snapshot.get('videos', []) if v['videoId'] == e['videoId']), None)
    if not video or video['sha256'] != expected['videoSha256'] or s.digest(videos.path_for(e['videoId']).read_bytes()) != video['sha256']:
        raise ValueError('source-video-changed-or-missing')
    if comparison:
        if e.get('unsupported'):
            _verify_follow(snapshot, e, cells, durations, depth)
        else:
            rebuilt = _restoration_state(e, source_cells, origin, keyed)[0] if e.get('applied') else origin
            if pixels(rebuilt) != pixels(cells): raise ValueError('baseline-does-not-match-origin-chain')
    return e, source_cells, origin, keyed


def read_comparison_evidence(snapshot, clip, cells, durations, *, depth=0):
    try:
        return read_evidence(snapshot, clip, cells, durations, comparison=True, depth=depth)
    except (s.AppError, IndexError, StopIteration) as exc:
        raise ValueError('follow-lineage-unverified') from exc


def saved_render(snapshot, clip):
    """Retain render inputs, not mutable jobs/caches, for portable follow verification."""
    ids = {o['frameVersionId'] for o in clip['occurrences']}
    clean = lambda row: {k: copy.deepcopy(v) for k, v in row.items() if k != 'sourceProcessing'}
    return dict(clip=clean(clip), frames=[clean(f) for f in snapshot['frames'] if f['frameVersionId'] in ids],
                alignmentGroups=copy.deepcopy([g for g in snapshot['alignmentGroups'] if ids.intersection(g['frameVersionIds'])]),
                alignments={fid: copy.deepcopy(snapshot['alignments'][fid]) for fid in ids})


def _verify_follow(snapshot, e, cells, durations, depth):
    from . import clip_tools
    from alignment.animation_exports import _sheet
    proof = e.get('followProof')
    if depth >= 64 or not isinstance(proof, dict) or proof.get('schemaVersion') != 1:
        raise ValueError('follow-lineage-unverified')
    parent = proof['parent']; clip = parent['clip']
    shadow = {**snapshot, **parent, 'clips': [clip]}
    before, times, _ = clip_tools.render_clip(shadow, clip, s.asset_path)
    pe, _, _, _ = read_comparison_evidence(shadow, clip, before, times, depth=depth + 1)
    if any(e[k] != pe[k] for k in ('source', 'origin', 'basis', 'applied')) or times != durations:
        raise ValueError('follow-parent-source-or-samples-changed')
    params = proof['settings']; motion = None
    if params.get('readOnClipId'):
        reading = proof['reading']; old_clip = reading['clip']
        old = {**snapshot, **reading, 'clips': [old_clip]}
        old_cells, old_times, _ = clip_tools.render_clip(old, old_clip, s.asset_path)
        # transported_reading also proves the exact native sample mapping and whole-cell relation.
        joined = {**shadow, 'frames': list({f['frameVersionId']: f for f in parent['frames'] + reading['frames']}.values()),
                  'alignmentGroups': list({g['alignmentGroupId']: g for g in parent['alignmentGroups'] + reading['alignmentGroups']}.values()),
                  'alignments': {**parent['alignments'], **reading['alignments']}, 'clips': [clip, old_clip]}
        motion = clip_tools.transported_reading(joined, clip, before, times,
            old_clip, old_cells, old_times, _sheet(old_cells, len(old_cells))[0])
        shadow['clips'].append(old_clip)
    settings = clip_tools.validate_params(shadow, 'preview_follow', params)
    if settings != params: raise ValueError('follow-settings-changed')
    reading_cells = old_cells if motion is not None else before
    if params.get('readOn') and params['readOn'] != s.digest(_sheet(reading_cells, len(reading_cells))[0]):
        raise ValueError('follow-reading-hash-changed')
    replayed, report = clip_tools.follow_frames(before, times, settings, motion=motion)
    if not report.get('canApply') or pixels(replayed) != pixels(cells):
        raise ValueError('follow-output-not-reproduced')


def _restoration_state(e, ref, origin, keyed):
    from alignment.pipeline import _engine
    r = _engine('video.restoration'); iq = _engine('video.interpolation_quality')
    key = e['key'] or (e['extraction'].get('spill') or {}).get('key')
    if key == 'auto': key = (e['extraction'].get('spill') or {}).get('key')
    if key not in ('green', 'magenta'): raise ValueError('source-key-unsupported')
    rebuilt = [im.copy() for im in origin]
    rect = e['basis']['sourceRect']; box = (rect['x'], rect['y'], rect['x'] + rect['width'], rect['y'] + rect['height'])
    crops = [im.crop(box) for im in keyed]; screen = iq.ghost_screen(crops)
    def partial(index):
        # Raw caps require identical final coordinates, including palette and padding.
        norm = e['basis']['normalization']
        projected = _engine('video.loop').resize_cell(crops[index], (norm['width'], norm['height']))
        canvas = Image.new('RGBA', projected.size); canvas.alpha_composite(projected)
        exact = e['basis']['finish']['mode'] == 'rgba' and canvas.size == ref[index].size and canvas.tobytes() == ref[index].tobytes()
        return r.partial(origin[index], ref[index], crops[index] if exact else ref[index], key)
    for index in e['applied']:
        if type(index) is not int or not 0 <= index < len(origin): raise ValueError('repair-evidence-invalid')
        part = partial(index)
        candidate = [im.copy() for im in rebuilt]; candidate[index] = part.frame
        check = r.judge(rebuilt, candidate, ref, key, e['facing'], screen)
        if part.alpha_conflict or check['verdict'] != 'improved': raise ValueError('repair-evidence-unreproducible')
        rebuilt = candidate
    return rebuilt, key, screen, partial


def restore(snapshot, clip, cells, durations):
    from alignment.pipeline import _engine
    r = _engine('video.restoration')
    iq = _engine('video.interpolation_quality')
    report = dict(kind=r.KIND, schema_version=r.REPAIR_SCHEMA, metric_version=r.METRIC,
                  policy_version=r.POLICY, comparison_schema=r.COMPARISON_SCHEMA, bridge_policy=policy(),
                  verdict='unknown', reasons=[], canApply=False, applied=[])
    def finish_report():
        report['comparison'] = dict(kind='sprite-gen-video-loop-comparison', schema_version=6,
            metric_version=r.METRIC, policy_version=r.POLICY, bridge_policy=policy(),
            **{k: copy.deepcopy(report[k]) for k in ('verdict', 'reasons', 'axes', 'source', 'origin', 'baseline', 'candidate') if k in report})
        return report
    try:
        e, ref, origin, keyed = read_evidence(snapshot, clip, cells, durations)
        report.update(source=e['source'], origin=e['origin'], baseline=identity(cells, durations, e['basis']))
        # Rebuild every accepted repair from immutable origin; a saved receipt is no authority by itself.
        rebuilt, key, screen, partial = _restoration_state(e, ref, origin, keyed)
        if pixels(rebuilt) != pixels(cells): raise ValueError('baseline-does-not-match-origin-chain')
        shown = r.measure(cells, cells, screen['reads'])
        attempts = []
        for index in range(len(cells)):
            if index in e['applied'] or index in [g['frame'] for g in screen['ghosts']] or not iq.faults(shown[index]): continue
            part = partial(index)
            if part.alpha_conflict or not (part.copied | part.capped).any(): continue
            after = [im.copy() for im in cells]; after[index] = part.frame
            judged = r.judge(cells, after, ref, key, e['facing'], screen)
            attempts.append(dict(cell=index, **judged))
            if judged['verdict'] != 'improved': continue
            report.update(judged, canApply=True, applied=[*e['applied'], index], attempts=attempts,
                          candidate=identity(after, durations, e['basis']))
            return after, finish_report()
        report.update(verdict='non_regressing', reasons=['no-accepted-source-restoration'], attempts=attempts,
                      candidate=identity(cells, durations, e['basis']))
    except (ValueError, KeyError, TypeError, OSError, IndexError) as exc:
        report.update(verdict='unknown', reasons=[str(exc)])
    return [im.copy() for im in cells], finish_report()


def compare_cells(a, b, durations, candidate_durations, basis, candidate_basis, *, comparable=True):
    """Use upstream same-sample ordering after the app proves its individual clock and coordinates."""
    from alignment.pipeline import _engine
    m = _engine('video.compare')
    class Canonical(m.Loop):
        def timing_issue(self): return None
        def provenance_issue(self): return None
    meta = dict(source_cut=basis, w=a[0].width, h=a[0].height, source_rect=[0, 0, a[0].width, a[0].height], scale=1, foot_anchor='none')
    aa = Canonical(a, meta, {}, {}, durations[-1])
    bb = Canonical(b, {**meta, 'source_cut': candidate_basis}, {}, {}, candidate_durations[-1])
    if not comparable or durations != candidate_durations or basis != candidate_basis or len(a) != len(b) or any(x.size != y.size for x, y in zip(a, b)):
        return dict(kind=m.KIND, schema_version=1, metric_version=m.METRIC_VERSION, bridge_policy=policy(), verdict='unknown', reasons=['sample-time-coordinate-unverified'], axes={})
    report = m.compare(aa, bb)
    report.update(bridge_policy=policy(), baseline=identity(a, durations, basis), candidate=identity(b, durations, basis))
    return report
