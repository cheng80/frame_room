import {describe, expect, it} from 'vitest';
import {assetProvenanceLabel} from '../src/assetProvenance';
import type {Asset, Clip, Job, Snapshot, Video} from '../src/types';
import {
  approvedVideoReference, defaultVideoAssetId, defaultVideoProcessing, imageProviders,
  validateVideoUpload, VIDEO_UPLOAD_LIMIT, videoGenerationRequest, videoProcessingParams,
  videoProcessingRequest, videoProvenanceLabel, videoRetryLabel, type VideoGenerationSettings,
  videoBeforeFinishSnapshot, videoClipColorLabel, videoJobStep, videoRangeBoundary,
  videoBatchItem, videoBatchRequest, VIDEO_BATCH_LIMIT,
  videoMatchClips, videoHasExactTimes, videoRangeSource,
} from '../src/videoWorkflow';

const video = {videoId: 'v', frameCount: 73, fps: 24, durationMs: 3042, provenance: {kind: 'imported-video'}} as Video;
const snapshot = {
  assets: [{assetId: 'unreviewed'}, {assetId: 'approved'}], videos: [video], activeReferenceRevisionId: 'draft',
  references: [{referenceRevisionId: 'draft', identityAssetId: 'unreviewed', approval: 'draft'},
    {referenceRevisionId: 'ref', identityAssetId: 'approved', approval: 'approved'}],
} as Snapshot;
const generation = (): VideoGenerationSettings => ({assetId: 'approved', model: 'grok-imagine-video-1.5', durationSeconds: '3', resolution: '480p', direction: 'side', facing: 'right', motionPrompt: '', bodyPlan: '', equipment: ''});

describe('video request boundaries', () => {
  it('defaults to game eight while preserving twelve and explicit legacy frame counts', () => {
    expect(defaultVideoProcessing()).toMatchObject({maxFrames: '8', finishMode: 'gif', repairMode: 'off', between: 'auto', startFoot: 'auto', startIndex: ''});
    for (const n of [4, 8, 12, 32, 64]) expect(videoProcessingParams({...defaultVideoProcessing(), maxFrames: String(n)}).maxFrames).toBe(n);
  });
  it('sends phase and interpolation controls independently of jump repair', () => {
    const params = videoProcessingParams({...defaultVideoProcessing(), between: 'off', startFoot: 'left', startIndex: '0'});
    expect(params).toMatchObject({repairMode: 'off', between: 'off', startFoot: 'left', startIndex: 0});
    expect(videoProcessingParams(defaultVideoProcessing())).not.toHaveProperty('startIndex');
  });
  it.each(['-1', '1.5', '64', 'NaN', 'Infinity', '9007199254740992'])('rejects invalid phase %s before enqueue', startIndex => {
    expect(() => videoProcessingParams({...defaultVideoProcessing(), startIndex})).toThrow('수동 시작 위치');
  });
  it('restricts manual phase to existing video and rejects positions outside the requested output', () => {
    const settings = {...defaultVideoProcessing(), startIndex: '7'};
    expect(() => videoGenerationRequest(snapshot, generation(), settings)).toThrow('기존 영상 처리');
    expect(videoProcessingRequest(snapshot, 'v', settings).params.startIndex).toBe(7);
    expect(() => videoProcessingRequest(snapshot, 'v', {...settings, startIndex: '8'})).toThrow('0~7');
    const manual = {...settings, loopMode: 'manual', startFrame: '0', endFrame: '4'};
    expect(() => videoProcessingRequest(snapshot, 'v', manual)).toThrow('0~3');
  });
  it('rejects unsupported enums and preserves structured prompts for backend validation', () => {
    expect(() => videoProcessingParams({...defaultVideoProcessing(), between: 'rife' as any})).toThrow('주기 보간');
    expect(() => videoProcessingParams({...defaultVideoProcessing(), startFoot: 'near' as any})).toThrow('시작 발');
    expect(videoGenerationRequest(snapshot, {...generation(), bodyPlan: ' the rider=biped; the horse=quadruped ', equipment: ' sword:right; shield:left '}, defaultVideoProcessing()).params)
      .toMatchObject({bodyPlan: 'the rider=biped; the horse=quadruped', equipment: 'sword:right; shield:left'});
  });
  it('defaults to an approved identity even when the active reference is a draft', () => {
    expect(defaultVideoAssetId(snapshot)).toBe('approved');
    expect(approvedVideoReference(snapshot)?.referenceRevisionId).toBe('ref');
  });
  it('builds exactly one generation operation with an approved reference and low default settings', () => {
    expect(videoGenerationRequest(snapshot, generation(), defaultVideoProcessing())).toEqual({
      operation: 'generate_video', assetIds: ['approved'], params: {
        state: 'walk', key: 'auto', loopMode: 'auto', maxFrames: 8, bodyHeight: 94, cellWidth: 64, cellHeight: 128, finishMode: 'gif', repairMode: 'off', between: 'auto', startFoot: 'auto',
        model: 'grok-imagine-video-1.5', durationSeconds: 3, resolution: '480p', direction: 'side', facing: 'right',
        motionPrompt: '', bodyPlan: '', equipment: '', referenceRevisionId: 'ref',
      },
    });
  });
  it('does not attach an unrelated or unapproved reference when another image is selected', () => {
    const request = videoGenerationRequest(snapshot, {...generation(), assetId: 'unreviewed'}, defaultVideoProcessing());
    expect(request.params).not.toHaveProperty('referenceRevisionId');
    expect(request.assetIds).toEqual(['unreviewed']);
  });
  it.each(['gif', 'rgba'] as const)('sends %s color finishing into the actual generate and process requests', finishMode => {
    const settings = {...defaultVideoProcessing(), finishMode};
    expect(videoGenerationRequest(snapshot, generation(), settings).params.finishMode).toBe(finishMode);
    expect(videoProcessingRequest(snapshot, 'v', settings).params.finishMode).toBe(finishMode);
  });
  it('rejects an unsupported finish mode instead of silently switching image colors', () => {
    expect(() => videoProcessingParams({...defaultVideoProcessing(), finishMode: 'unknown' as any})).toThrow('색상 마무리');
  });
  it.each(['front_diagonal', 'back_diagonal'])('uses the confirmed public direction spelling %s', direction => {
    expect(videoGenerationRequest(snapshot, {...generation(), direction}, defaultVideoProcessing()).params.direction).toBe(direction);
  });
  it.each(['cheer', 'wave', 'dance'])('accepts the supported %s motion', state => {
    expect(videoGenerationRequest(snapshot, generation(), {...defaultVideoProcessing(), state}).params.state).toBe(state);
  });
  it.each(['off', 'auto', 'on'] as const)('sends the explicit %s repair setting', repairMode => {
    expect(videoProcessingRequest(snapshot, 'v', {...defaultVideoProcessing(), repairMode}).params.repairMode).toBe(repairMode);
  });
  it('rejects unconfirmed direction aliases', () => {
    expect(() => videoGenerationRequest(snapshot, {...generation(), direction: 'front-diagonal'}, defaultVideoProcessing())).toThrow('보기 방향');
  });
  it.each(['auto', 'full'])('processes existing video in %s mode without any generation settings', loopMode => {
    const request = videoProcessingRequest(snapshot, 'v', {...defaultVideoProcessing(), loopMode});
    expect(request.operation).toBe('process_video'); expect(request.assetIds).toEqual([]);
    expect(request.params).toMatchObject({videoId: 'v', loopMode});
    for (const key of ['model', 'durationSeconds', 'resolution', 'referenceRevisionId', 'motionPrompt']) expect(request.params).not.toHaveProperty(key);
  });
  it('sends an explicitly selected spill reference belonging to the current project', () => {
    const request = videoProcessingRequest(snapshot, 'v', {...defaultVideoProcessing(), spillReferenceAssetId: 'unreviewed'});
    expect(request.operation).toBe('process_video');
    expect(request.assetIds).toEqual([]);
    expect(request.params).toMatchObject({videoId: 'v', spillReferenceAssetId: 'unreviewed'});
  });
  it.each([undefined, 'approved'])('leaves the default spill reference to video provenance (%s), without choosing the first asset', referenceAssetId => {
    const project = {...snapshot, videos: [{...video, provenance: {kind: 'imported-video', referenceAssetId}}]};
    expect(defaultVideoProcessing().spillReferenceAssetId).toBe('');
    expect(videoProcessingRequest(project, 'v', defaultVideoProcessing()).params).not.toHaveProperty('spillReferenceAssetId');
  });
  it('rejects an explicit spill reference removed from the current snapshot instead of silently weakening correction', () => {
    const settings = {...defaultVideoProcessing(), spillReferenceAssetId: 'approved'};
    const latest = {...snapshot, assets: snapshot.assets.filter(a => a.assetId !== 'approved')};
    expect(() => videoProcessingRequest(latest, 'v', settings)).toThrow('색 번짐 판정 기준 이미지가 현재 프로젝트에 없습니다.');
  });
  it.each(['unreviewed', 'removed'])('never forwards the processing spill reference (%s) to video generation', spillReferenceAssetId => {
    const request = videoGenerationRequest(snapshot, generation(), {...defaultVideoProcessing(), spillReferenceAssetId});
    expect(request.assetIds).toEqual(['approved']);
    expect(request.params.referenceRevisionId).toBe('ref');
    expect(request.params).not.toHaveProperty('spillReferenceAssetId');
  });
  it('sends the manual range as zero-based, end-exclusive frame indices without changing time', () => {
    const params = videoProcessingParams({...defaultVideoProcessing(), loopMode: 'manual', startFrame: '7', endFrame: '35'}, video);
    expect(params).toMatchObject({startFrame: 7, endFrame: 35});
    expect(params).not.toHaveProperty('fps');
    expect(videoProcessingParams({...defaultVideoProcessing(), loopMode: 'manual'}, video).endFrame).toBe(73);
  });
  it.each([['7', '7'], ['9', '3'], ['-1', '20'], ['0', '74'], ['1.5', '4']])('rejects invalid manual range [%s, %s)', (startFrame, endFrame) => {
    expect(() => videoProcessingParams({...defaultVideoProcessing(), loopMode: 'manual', startFrame, endFrame}, video)).toThrow();
  });
  it.each([['maxFrames', '65'], ['maxFrames', ''], ['bodyHeight', 'NaN'], ['cellWidth', '0'], ['cellHeight', '94']])('rejects invalid processing field %s=%s', (key, value) => {
    expect(() => videoProcessingParams({...defaultVideoProcessing(), [key]: value})).toThrow();
  });
  it('never constructs a generation request with manual video ranges or unsupported model', () => {
    expect(() => videoGenerationRequest(snapshot, generation(), {...defaultVideoProcessing(), loopMode: 'manual'})).toThrow();
    expect(() => videoGenerationRequest(snapshot, {...generation(), model: 'other'}, defaultVideoProcessing())).toThrow();
  });
  it('supports schema 1 projects without videos and rejects stale video/image IDs', () => {
    expect(defaultVideoAssetId({...snapshot, videos: undefined})).toBe('approved');
    expect(() => videoProcessingRequest({...snapshot, videos: undefined}, 'v', defaultVideoProcessing())).toThrow();
    expect(() => videoGenerationRequest(snapshot, {...generation(), assetId: 'gone'}, defaultVideoProcessing())).toThrow();
  });
  it('separates video capabilities from legacy image providers', () => {
    expect(imageProviders([{providerId: 'grok-video', mediaKind: 'video'}, {providerId: 'codex'}, {providerId: 'image', mediaKind: 'image'}]).map(p => p.providerId)).toEqual(['codex', 'image']);
  });
  it('checks MP4 type, emptiness, and the precise 64MiB upload boundary', () => {
    expect(() => validateVideoUpload({name: 'walk.MP4', type: '', size: VIDEO_UPLOAD_LIMIT})).not.toThrow();
    for (const f of [{name: 'a.png', type: 'image/png', size: 1}, {name: 'a.mp4', type: 'video/webm', size: 1}, {name: 'a.mp4', type: 'video/mp4', size: 0}, {name: 'a.mp4', type: '', size: VIDEO_UPLOAD_LIMIT + 1}]) expect(() => validateVideoUpload(f)).toThrow();
  });
});

describe('atomic video batch planning', () => {
  it('freezes each item from the same validated parameters as a single generation', () => {
    const g = generation(), processing = defaultVideoProcessing();
    const first = videoBatchItem(snapshot, g, processing);
    const expected = videoGenerationRequest(snapshot, g, processing);
    expect(first).toEqual({assetId: expected.assetIds[0], params: expected.params});
    g.direction = 'back_diagonal'; g.bodyPlan = 'quadruped'; g.equipment = 'sword:right'; processing.finishMode = 'rgba'; processing.maxFrames = '12';
    const second = videoBatchItem(snapshot, g, processing);
    const body = videoBatchRequest({...snapshot, revision: 12}, [first, second], 'stable-key');
    expect(body).toMatchObject({inputRevision: 12, idempotencyKey: 'stable-key'});
    expect(body.items[0].params).toMatchObject({direction: 'side', finishMode: 'gif', bodyPlan: '', equipment: '', maxFrames: 8});
    expect(body.items[0].params).not.toHaveProperty('startIndex');
    expect(body.items[1].params).toMatchObject({direction: 'back_diagonal', finishMode: 'rgba', bodyPlan: 'quadruped', equipment: 'sword:right', maxFrames: 12});
    expect(body.items[0].params).not.toHaveProperty('spillReferenceAssetId');
  });
  it('accepts at most 16 coherent items and rejects an empty plan', () => {
    const item = videoBatchItem(snapshot, generation(), defaultVideoProcessing());
    expect(videoBatchRequest(snapshot, Array(VIDEO_BATCH_LIMIT).fill(item), 'key').items).toHaveLength(16);
    expect(() => videoBatchRequest(snapshot, Array(17).fill(item), 'key')).toThrow('1~16');
    expect(() => videoBatchRequest(snapshot, [], 'key')).toThrow('1~16');
  });
  it('requires current project assets and valid captured reference approval before first submission', () => {
    const item = videoBatchItem(snapshot, generation(), defaultVideoProcessing());
    expect(() => videoBatchRequest({...snapshot, assets: []}, [item], 'key')).toThrow('기준 이미지');
    expect(() => videoBatchRequest({...snapshot, references: []}, [item], 'key')).toThrow('승인');
    expect(() => videoBatchRequest(snapshot, [item], '')).toThrow('식별자');
  });
});

describe('matching another clip cycle', () => {
  const target = {clipId: 'target', loop: true, occurrences: Array.from({length: 4}, () => ({durationMs: 100}))} as Clip;
  const project = {...snapshot, clips: [target]};
  it('restricts targets to valid loops with 4–64 frames and at most 60 seconds', () => {
    const candidates = [target, {...target, clipId: 'one-shot', loop: false}, {...target, clipId: 'short', occurrences: target.occurrences.slice(0, 3)},
      {...target, clipId: 'many', occurrences: Array(65).fill(target.occurrences[0])},
      {...target, clipId: 'long', occurrences: Array(4).fill({...target.occurrences[0], durationMs: 15001})}];
    expect(videoMatchClips({...project, clips: candidates}).map(clip => clip.clipId)).toEqual(['target']);
  });
  it('sends the same optional target for generation, processing, and batch creation', () => {
    const settings = {...defaultVideoProcessing(), matchClipId: 'target'};
    expect(videoGenerationRequest(project, generation(), settings).params).toMatchObject({matchClipId: 'target'});
    expect(videoProcessingRequest(project, 'v', settings).params).toMatchObject({matchClipId: 'target'});
    expect(videoBatchRequest(project, [videoBatchItem(project, generation(), settings)], 'key').items[0].params.matchClipId).toBe('target');
    expect(videoProcessingRequest(project, 'v', defaultVideoProcessing()).params).not.toHaveProperty('matchClipId');
  });
  it('rejects full-video matching and a target removed or made non-looping before submission', () => {
    const settings = {...defaultVideoProcessing(), matchClipId: 'target'};
    expect(() => videoProcessingRequest(project, 'v', {...settings, loopMode: 'full'})).toThrow('전체 영상');
    expect(() => videoGenerationRequest({...project, clips: []}, generation(), settings)).toThrow('주기를 맞출 동작');
    const item = videoBatchItem(project, generation(), settings);
    expect(() => videoBatchRequest({...project, clips: [{...target, loop: false}]}, [item], 'key')).toThrow('주기를 맞출 동작');
  });
});

describe('safe resume and source provenance', () => {
  it('explains the PNG finishing stage separately from extraction', () => {
    expect(videoJobStep({operation: 'process_video', status: 'running', step: 'finish_frames'} as Job)).toBe('편집·출력용 색상과 투명도 마무리');
  });
  it('offers GET resume only when the server explicitly marks a known request resumable', () => {
    const j = {operation: 'generate_video', status: 'interrupted'} as Job;
    expect(videoRetryLabel(j)).toBeNull();
    expect(videoRetryLabel({...j, resumable: false})).toBeNull();
    expect(videoRetryLabel({...j, resumable: true})).toBe('접수한 요청 조회 재개');
    expect(videoRetryLabel({...j, resumable: true, result: {videoId: 'v'}})).toBe('기존 영상 처리 재개');
    expect(videoRetryLabel({...j, resumable: true, status: 'provider_outcome_unknown'})).toBeNull();
  });
  it('distinguishes raw video frames, keyed frames, and interpolated frames', () => {
    const raw = {assetId: 'raw', role: 'derived', provenance: {kind: 'video-frame-raw', sourceVideoId: 'v', interpolated: false}} as Asset;
    const keyed = {...raw, assetId: 'keyed', provenance: {...raw.provenance as object, kind: 'video-frame', processing: 'chroma-key', parentAssetId: 'raw'}};
    const assets = new Map([[raw.assetId, raw], [keyed.assetId, keyed]]), videos = new Map([['v', video]]);
    expect(assetProvenanceLabel(raw, assets, videos)).toMatchObject({label: '영상 원본 프레임', originLabel: '가져온 영상에서 파생'});
    expect(assetProvenanceLabel(keyed, assets, videos)).toMatchObject({label: '영상 배경 제거 프레임', originLabel: '가져온 영상에서 파생'});
    expect(assetProvenanceLabel({...keyed, provenance: {...keyed.provenance, processing: undefined}}, assets, videos).label).toBe('영상 배경 제거 프레임');
    expect(assetProvenanceLabel({...keyed, provenance: {...keyed.provenance, interpolated: true}}, assets).label).toBe('영상 보간 프레임');
    expect(assetProvenanceLabel({...keyed, provenance: {...keyed.provenance, processing: 'video-finish'}}, assets).label).toBe('영상 색상 마무리 프레임');
    expect(assetProvenanceLabel({...keyed, provenance: {...keyed.provenance, processing: 'video-finish', interpolated: true}}, assets).label).toBe('영상 보간·색상 마무리 프레임');
    expect(assetProvenanceLabel({...keyed, provenance: {...keyed.provenance, processing: 'video-finish', interpolated: true, interpolation: {method: 'rife-ncnn-vulkan', fraction: .5, sourceFrameIndices: [1, 3]}}}, assets).label).toBe('RIFE 보간·색상 마무리 프레임');
    expect(assetProvenanceLabel(keyed, assets, new Map([['v', {...video, provenance: {kind: 'real-provider-video'}}]]))).toMatchObject({originLabel: 'AI 생성 영상에서 파생'});
  });
  it('does not label imported or unknown videos as generated based on filenames', () => {
    expect(videoProvenanceLabel({...video, originalFilename: 'Grok-walk.mp4'})).toBe('가져온 원본 영상');
    expect(videoProvenanceLabel({...video, provenance: {}})).toBe('원본 영상 · 출처 확인 필요');
  });
});

describe('actual PNG comparison and range controls', () => {
  it('uses exact VFR boundaries when available and takes them only from the selected video', () => {
    const vfr = {...video, frameCount: 3, fps: 30, durationMs: 400};
    const job = {result: {videoId: 'v', processing: {source: {timesMs: [0, 100, 125, 400], streamIndex: 1}}}} as Job;
    const timed = videoRangeSource(vfr, [job]);
    expect(videoHasExactTimes(timed)).toBe(true);
    expect(videoRangeBoundary(timed, .12, 'start')).toBe('1');
    expect(videoRangeBoundary(timed, .125, 'start')).toBe('2');
    expect(videoRangeBoundary(timed, .4, 'end')).toBe('3');
    expect(videoRangeSource({...vfr, videoId: 'other'}, [job]).timesMs).toBeUndefined();
    expect(vfr).not.toHaveProperty('timesMs');
    expect(videoHasExactTimes({...vfr, timesMs: [0, 100, 100, 400]})).toBe(false);
    expect(videoHasExactTimes({...vfr, timesMs: [0, 100, 125]})).toBe(false);
    expect(videoRangeBoundary({...timed, fps: 0}, .1, 'start')).toBe('1');
  });
  const clip = {clipId: 'clip', occurrences: [{occurrenceId: 'slot', frameVersionId: 'frame', durationMs: 42, pixelEdits: [{x: 1, y: 2, color: [255, 0, 0, 255]}]}]} as unknown as Clip;
  const stored = {...snapshot,
    assets: [{assetId: 'finished', width: 60, height: 100, provenance: {processing: 'video-finish', parentAssetId: 'normalized', finish: {mode: 'gif'}}}, {assetId: 'normalized', width: 60, height: 100}],
    frames: [{frameVersionId: 'frame', imageAssetId: 'finished'}], clips: [clip],
  } as Snapshot;
  it('shows stored color treatment and never treats an old clip as freshly finished', () => {
    expect(videoClipColorLabel(stored, clip)).toContain('최대 255색');
    const rgba = {...stored, assets: stored.assets.map(a => a.assetId === 'finished' ? {...a, provenance: {finish: {mode: 'rgba'}}} : a)};
    expect(videoClipColorLabel(rgba, clip)).toBe('반투명 원본 유지 · RGBA PNG');
    expect(videoClipColorLabel({...stored, assets: []}, clip)).toContain('기록 없음');
    const mixed = {...clip, occurrences: [...clip.occurrences, {...clip.occurrences[0], frameVersionId: 'missing'}]};
    expect(videoClipColorLabel(stored, mixed)).toContain('섞인 동작');
  });
  it('compares normalization parents without changing the project, geometry, time, or user edits', () => {
    const original = structuredClone(stored), before = videoBeforeFinishSnapshot(stored, clip)!;
    expect(before.frames[0].imageAssetId).toBe('normalized');
    expect(before.frames[0]).toEqual({...stored.frames[0], imageAssetId: 'normalized'});
    expect(before.clips).toBe(stored.clips);
    expect(before.assets).toBe(stored.assets);
    expect(stored).toEqual(original);
  });
  it('does not show a misleading comparison when source geometry or links do not match', () => {
    expect(videoBeforeFinishSnapshot({...stored, assets: stored.assets.slice(0, 1)}, clip)).toBeNull();
    expect(videoBeforeFinishSnapshot({...stored, assets: stored.assets.map(a => a.assetId === 'normalized' ? {...a, width: 61} : a)}, clip)).toBeNull();
    expect(videoBeforeFinishSnapshot({...stored, frames: []}, clip)).toBeNull();
    expect(videoBeforeFinishSnapshot(stored, {...clip, occurrences: []})).toBeNull();
  });
  it('maps video positions to bounded inclusive-start/exclusive-end frame numbers', () => {
    expect(videoRangeBoundary(video, 1.5, 'start')).toBe('36');
    expect(videoRangeBoundary(video, 1.5, 'end')).toBe('37');
    expect(videoRangeBoundary(video, video.durationMs / 1000, 'end')).toBe('73');
    expect(videoRangeBoundary(video, 100, 'start')).toBe('72');
    expect(videoRangeBoundary(video, NaN, 'start')).toBeNull();
    expect(videoRangeBoundary({...video, fps: 0}, 1, 'end')).toBeNull();
  });
});

it('keeps stored imported-video direction unless explicitly overridden for foot analysis', () => {
  const defaults = defaultVideoProcessing();
  const old = videoProcessingParams(defaults);
  expect(old).not.toHaveProperty('direction');
  expect(old).not.toHaveProperty('facing');
  const explicit = videoProcessingParams({...defaults, direction: 'back_diagonal', facing: 'left'});
  expect(explicit).toMatchObject({direction: 'back_diagonal', facing: 'left'});
});
