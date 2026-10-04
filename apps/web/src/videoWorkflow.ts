import type {Clip, Job, Provider, Snapshot, Video} from './types';

export const VIDEO_MODELS = [
  {id: 'grok-imagine-video-1.5', label: 'Pro'},
  {id: 'grok-imagine-video-1.5-lite', label: 'Lite'},
] as const;
export const VIDEO_STATES = [
  {id: 'idle', label: '대기'}, {id: 'walk', label: '걷기'}, {id: 'run', label: '달리기'},
  {id: 'jump', label: '점프'}, {id: 'attack', label: '공격'},
  {id: 'cheer', label: '환호'}, {id: 'wave', label: '손 흔들기'}, {id: 'dance', label: '춤'},
] as const;
export const VIDEO_DIRECTIONS = [
  {id: 'side', label: '측면'}, {id: 'front', label: '정면'}, {id: 'back', label: '뒷면'},
  {id: 'front_diagonal', label: '앞 대각선'}, {id: 'back_diagonal', label: '뒤 대각선'},
] as const;
export const VIDEO_UPLOAD_LIMIT = 64 * 1024 * 1024;
export const VIDEO_BATCH_LIMIT = 16;
export interface VideoProcessingSettings {
  state: string;
  key: string;
  loopMode: string;
  startFrame: string;
  endFrame: string;
  maxFrames: string;
  bodyHeight: string;
  cellWidth: string;
  cellHeight: string;
  spillReferenceAssetId: string;
  finishMode: 'gif' | 'rgba';
  repairMode: 'off' | 'auto' | 'on';
  matchClipId: string;
}
export interface VideoGenerationSettings {
  assetId: string;
  model: string;
  durationSeconds: string;
  resolution: string;
  direction: string;
  facing: string;
  motionPrompt: string;
}
export const defaultVideoProcessing = (): VideoProcessingSettings => ({
  state: 'walk', key: 'auto', loopMode: 'auto', startFrame: '0', endFrame: '',
  maxFrames: '32', bodyHeight: '94', cellWidth: '64', cellHeight: '128',
  spillReferenceAssetId: '', finishMode: 'gif', repairMode: 'off', matchClipId: '',
});
export const imageProviders = (providers: Provider[]) => providers.filter(p => p.mediaKind !== 'video');
export function approvedVideoReference(snapshot: Snapshot, assetId?: string) {
  const references = snapshot.references.filter(r => r.approval === 'approved' &&
    (!assetId || r.identityAssetId === assetId) && snapshot.assets.some(a => a.assetId === r.identityAssetId));
  return references.find(r => r.referenceRevisionId === snapshot.activeReferenceRevisionId) ?? references.at(-1);
}
export function defaultVideoAssetId(snapshot: Snapshot) {
  return approvedVideoReference(snapshot)?.identityAssetId ?? snapshot.assets[0]?.assetId ?? '';
}
function integer(value: string, min: number, max: number, label: string) {
  const n = Number(value);
  if (!value.trim() || !Number.isInteger(n) || n < min || n > max) {
    throw new Error(`${label}: ${min}~${max} 사이의 정수를 입력해 주세요.`);
  }
  return n;
}
function oneOf(value: string, choices: readonly string[], label: string) {
  if (!choices.includes(value)) throw new Error(`${label}을 다시 선택해 주세요.`);
  return value;
}
export function videoProcessingParams(settings: VideoProcessingSettings, video?: Video): Record<string, unknown> {
  const params: Record<string, unknown> = {
    state: oneOf(settings.state, VIDEO_STATES.map(s => s.id), '동작'),
    key: oneOf(settings.key, ['auto', 'green', 'magenta', 'cyan', 'white'], '배경색'),
    loopMode: oneOf(settings.loopMode, ['auto', 'full', 'manual'], '추출 구간'),
    maxFrames: integer(settings.maxFrames, 4, 64, '최대 후보 수'),
    bodyHeight: integer(settings.bodyHeight, 16, 512, '공통 몸 높이'),
    cellWidth: integer(settings.cellWidth, 32, 1024, '셀 너비'),
    cellHeight: integer(settings.cellHeight, 32, 1024, '셀 높이'),
    finishMode: oneOf(settings.finishMode, ['gif', 'rgba'], '색상 마무리'),
    repairMode: oneOf(settings.repairMode, ['off', 'auto', 'on'], '동작 흔들림 보정'),
  };
  if (Number(settings.bodyHeight) > Number(settings.cellHeight) - 4) throw new Error('셀 높이는 공통 몸 높이보다 4px 이상 크게 지정해 주세요.');
  if (settings.loopMode === 'manual') {
    if (!video) throw new Error('수동 구간은 등록한 영상을 선택한 뒤 지정해 주세요.');
    const start = integer(settings.startFrame, 0, video.frameCount - 1, '시작 프레임');
    const end = integer(settings.endFrame || String(video.frameCount), 1, video.frameCount, '끝 프레임');
    if (end <= start) throw new Error('끝 프레임은 시작 프레임보다 커야 합니다.');
    params.startFrame = start;
    params.endFrame = end;
  }
  if (settings.matchClipId) {
    if (settings.loopMode === 'full') throw new Error('전체 영상은 반복 주기를 맞출 수 없습니다. 자동 또는 수동 구간을 선택해 주세요.');
    params.matchClipId = settings.matchClipId;
  }
  return params;
}
export function videoMatchClips(snapshot: Snapshot) {
  return snapshot.clips.filter(clip => clip.loop && clip.occurrences.length >= 4 && clip.occurrences.length <= 64 &&
    clip.occurrences.every(occurrence => Number.isInteger(occurrence.durationMs) && occurrence.durationMs > 0) &&
    clip.occurrences.reduce((sum, occurrence) => sum + occurrence.durationMs, 0) <= 60000);
}
function validateMatchClip(snapshot: Snapshot, clipId: string) {
  if (clipId && !videoMatchClips(snapshot).some(clip => clip.clipId === clipId)) throw new Error('주기를 맞출 동작을 다시 선택해 주세요. 4~64프레임, 총 60초 이하의 반복 동작만 사용할 수 있습니다.');
}
export function videoGenerationRequest(snapshot: Snapshot, settings: VideoGenerationSettings, processing: VideoProcessingSettings) {
  if (!snapshot.assets.some(a => a.assetId === settings.assetId)) throw new Error('영상에 사용할 기준 이미지를 선택해 주세요.');
  if (settings.motionPrompt.length > 2000) throw new Error('추가 동작 지시는 2,000자 이하로 입력해 주세요.');
  validateMatchClip(snapshot, processing.matchClipId);
  const reference = approvedVideoReference(snapshot, settings.assetId);
  return {
    operation: 'generate_video', assetIds: [settings.assetId],
    params: {
      ...videoProcessingParams(processing),
      model: oneOf(settings.model, VIDEO_MODELS.map(m => m.id), '영상 모델'),
      durationSeconds: integer(settings.durationSeconds, 2, 6, '영상 길이'),
      resolution: oneOf(settings.resolution, ['480p', '720p'], '해상도'),
      direction: oneOf(settings.direction, VIDEO_DIRECTIONS.map(direction => direction.id), '보기 방향'),
      facing: oneOf(settings.facing, ['right', 'left'], '캐릭터 방향'),
      motionPrompt: settings.motionPrompt.trim(),
      ...(reference ? {referenceRevisionId: reference.referenceRevisionId} : {}),
    },
  };
}
export type VideoBatchItem = {assetId: string; params: ReturnType<typeof videoGenerationRequest>['params'] & Record<string, unknown>};
export function videoBatchItem(snapshot: Snapshot, settings: VideoGenerationSettings, processing: VideoProcessingSettings): VideoBatchItem {
  const request = videoGenerationRequest(snapshot, settings, processing);
  return {assetId: request.assetIds[0], params: {...request.params}};
}
export function videoBatchRequest(snapshot: Snapshot, items: readonly VideoBatchItem[], idempotencyKey: string) {
  if (!items.length || items.length > VIDEO_BATCH_LIMIT) throw new Error(`묶음에는 1~${VIDEO_BATCH_LIMIT}건을 담아 주세요.`);
  if (!idempotencyKey.trim()) throw new Error('묶음 요청 식별자가 없습니다.');
  for (const item of items) {
    if (!snapshot.assets.some(asset => asset.assetId === item.assetId)) throw new Error('묶음에 담은 기준 이미지가 없습니다. 해당 항목을 제거한 뒤 다시 추가해 주세요.');
    if (item.params.referenceRevisionId && !snapshot.references.some(reference => reference.referenceRevisionId === item.params.referenceRevisionId && reference.approval === 'approved' && reference.identityAssetId === item.assetId)) throw new Error('묶음에 담은 외형 기준의 승인이 달라졌습니다. 해당 항목을 다시 추가해 주세요.');
    if (typeof item.params.matchClipId === 'string') validateMatchClip(snapshot, item.params.matchClipId);
  }
  return {inputRevision: snapshot.revision, items: items.map(item => ({assetId: item.assetId, params: {...item.params}})), idempotencyKey};
}
export function videoProcessingRequest(snapshot: Snapshot, videoId: string, processing: VideoProcessingSettings) {
  const video = snapshot.videos?.find(v => v.videoId === videoId);
  if (!video) throw new Error('처리할 원본 영상을 선택해 주세요.');
  validateMatchClip(snapshot, processing.matchClipId);
  const spillReferenceAssetId = processing.spillReferenceAssetId;
  if (spillReferenceAssetId && !snapshot.assets.some(a => a.assetId === spillReferenceAssetId)) {
    throw new Error('색 번짐 판정 기준 이미지가 현재 프로젝트에 없습니다. 영상 제작에 쓴 원본 그림을 다시 선택해 주세요.');
  }
  return {operation: 'process_video', assetIds: [], params: {
    ...videoProcessingParams(processing, video), videoId,
    ...(spillReferenceAssetId ? {spillReferenceAssetId} : {}),
  }};
}
export function validateVideoUpload(file: Pick<File, 'name' | 'type' | 'size'>) {
  if (!/\.mp4$/i.test(file.name) || (file.type && file.type !== 'video/mp4')) throw new Error('MP4 영상만 가져올 수 있습니다.');
  if (!file.size || file.size > VIDEO_UPLOAD_LIMIT) throw new Error('비어 있지 않은 64MiB 이하 MP4를 선택해 주세요.');
}
export const isVideoJob = (job: Job) => ['generate_video', 'process_video'].includes(job.operation);
const videoSteps: Record<string, string> = {
  prepare: '기준 이미지와 설정 준비', submit: '영상 생성 요청 접수', poll: '접수한 영상 생성 결과 조회',
  download: '완료된 원본 영상 저장', extract: '프레임 추출·배경 제거', select_cycle: '동작 구간 선택',
  finish_frames: '편집·출력용 색상과 투명도 마무리',
  import_candidates: '새 후보와 동작 등록', complete: '완료 · 후보 검수 대기',
};
export function videoJobStep(job: Job) {
  if (job.status === 'needs_review') return '완료 · 후보 검수 대기';
  if (['succeeded', 'completed'].includes(job.status)) return '처리 완료';
  return videoSteps[job.step || ''] || (job.status === 'queued' ? '처리 대기' : '작업 상태 확인');
}
export function videoRetryLabel(job: Job): string | null {
  if (!isVideoJob(job) || job.resumable !== true || !['failed', 'interrupted', 'canceled'].includes(job.status)) return null;
  return job.result?.videoId || job.operation === 'process_video' ? '기존 영상 처리 재개' : '접수한 요청 조회 재개';
}
export function videoProvenanceLabel(video: Video) {
  const p = video.provenance;
  if (p && typeof p === 'object' && 'kind' in p) {
    if (['real-provider-video', 'real-provider'].includes(String(p.kind))) return 'AI 생성 원본 영상';
    if (['imported-video', 'imported', 'upload', 'uploaded'].includes(String(p.kind))) return '가져온 원본 영상';
  }
  return '원본 영상 · 출처 확인 필요';
}

/** Read the selected clip's stored assets, never the currently selected form options. */
export function videoClipColorLabel(snapshot: Snapshot, clip: Clip) {
  const frameAssets = new Map(snapshot.frames.map(frame => [frame.frameVersionId, frame.imageAssetId]));
  const assets = new Map(snapshot.assets.map(asset => [asset.assetId, asset]));
  const modes = new Set(clip.occurrences.map(occurrence => {
    const provenance = assets.get(frameAssets.get(occurrence.frameVersionId) ?? '')?.provenance;
    if (!provenance || typeof provenance !== 'object' || !('finish' in provenance)) return 'unknown';
    const finish = provenance.finish;
    return finish && typeof finish === 'object' && 'mode' in finish && ['gif', 'rgba'].includes(String(finish.mode)) ? String(finish.mode) : 'unknown';
  }));
  if (modes.size > 1) return '여러 색상 처리 결과가 섞인 동작';
  if (modes.has('gif')) return '검수 GIF와 같은 색상 · 프레임당 최대 255색 · 투명/불투명 PNG';
  if (modes.has('rgba')) return '반투명 원본 유지 · RGBA PNG';
  return '색상 마무리 기록 없음 · 기존 후보 그대로 표시';
}

/** Video controls use average FPS only to suggest an editable, zero-based range. */
export function videoRangeBoundary(video: Video, seconds: number, boundary: 'start' | 'end') {
  if (!Number.isFinite(seconds) || seconds < 0 || !Number.isFinite(video.fps) || video.fps <= 0 || video.frameCount < 1) return null;
  const frame = Math.min(video.frameCount - 1, Math.floor(seconds * video.fps));
  return String(boundary === 'end' ? frame + 1 : frame);
}

/** Read-only comparison keeps the exact same geometry, timing and user edits. */
export function videoBeforeFinishSnapshot(snapshot: Snapshot, clip: Clip): Snapshot | null {
  const frameIds = new Set(clip.occurrences.map(occurrence => occurrence.frameVersionId));
  if (!frameIds.size) return null;
  const assets = new Map(snapshot.assets.map(asset => [asset.assetId, asset]));
  const replacements = new Map<string, string>();
  for (const frame of snapshot.frames) {
    if (!frameIds.has(frame.frameVersionId)) continue;
    const asset = assets.get(frame.imageAssetId), provenance = asset?.provenance;
    if (!provenance || typeof provenance !== 'object' || !('processing' in provenance) || provenance.processing !== 'video-finish' || !('parentAssetId' in provenance) || typeof provenance.parentAssetId !== 'string') return null;
    const parent = assets.get(provenance.parentAssetId);
    if (!parent || parent.width !== asset?.width || parent.height !== asset?.height) return null;
    replacements.set(frame.frameVersionId, parent.assetId);
  }
  if (replacements.size !== frameIds.size) return null;
  return {...snapshot, frames: snapshot.frames.map(frame => replacements.has(frame.frameVersionId) ? {...frame, imageAssetId: replacements.get(frame.frameVersionId)!} : frame)};
}
