import type {Clip, Job, Snapshot} from './types';
import type {Studio} from './useStudio';

export type Region = [number, number, number, number];
export type FollowFields = {region: [string, string, string, string]; gain: string; freq: string; damping: string; onFold: 'lower' | 'refuse'};
export type HandedFields = {item: string; side: string; part: string; direction: string; facing: string; marker: string; referenceAssetId: string};
export type ClipToolSource = {projectId: string; projectRevision: number; clipId: string; clipRevisionId: string; occurrenceIds: string[]};
export type ClipToolPreview = {width: number; height: number; frameCount: number; durationsMs: number[]; before: string; beforeStrip: string; firstFrame: string; after?: string; afterStrip?: string; board?: string};
export type FollowReport = {gainRequested: number; gainApplied: number; foldLimited: boolean; unchanged?: boolean; reachPx?: number};
export type HandedReport = {verdict: 'clear' | 'suspect' | 'inconclusive'; framesShown: number; frameCount: number; suspectFrames: {index: number; occurrenceId: string; reasons: string[]}[]; unchecked: string[]};
export type ClipToolResult = {version: 'clip-tools-v1'; source: ClipToolSource; settings: Record<string, unknown>; preview: ClipToolPreview} & ({tool: 'follow'; report: FollowReport} | {tool: 'handed'; report: HandedReport});
export type ToolRequest = {job: Job; source: ClipToolSource; settingsKey: string};

export const defaultFollow = (): FollowFields => ({region: ['', '', '', ''], gain: '2.5', freq: '2.4', damping: '0.6', onFold: 'lower'});
export const defaultHanded = (): HandedFields => ({item: '', side: 'right', part: 'hand', direction: 'side', facing: 'right', marker: '#ff00ff', referenceAssetId: ''});
export const jobSucceeded = (job?: Job) => !!job && (job.status === 'succeeded' || job.operation === 'apply_follow' && ['completed', 'needs_review'].includes(job.status));
export const jobPending = (job?: Job) => !!job && ['queued', 'running', 'cancel_requested', 'pending'].includes(job.status);
export const currentJob = (request: ToolRequest | undefined, jobs: Job[]) => request ? jobs.find(job => job.jobId === request.job.jobId) || request.job : undefined;
export const settingsKey = (value: FollowFields | HandedFields) => JSON.stringify(value);
export const sourceOf = (snapshot: Snapshot, clip: Clip): ClipToolSource => ({projectId: snapshot.projectId, projectRevision: snapshot.revision, clipId: clip.clipId, clipRevisionId: clip.clipRevisionId, occurrenceIds: clip.occurrences.map(o => o.occurrenceId)});
export const sameSource = (a: ClipToolSource, b: ClipToolSource) => a.projectId === b.projectId && a.projectRevision === b.projectRevision && a.clipId === b.clipId && a.clipRevisionId === b.clipRevisionId && a.occurrenceIds.length === b.occurrenceIds.length && a.occurrenceIds.every((id, i) => id === b.occurrenceIds[i]);
export function clipCell(snapshot: Snapshot, clip: Clip) {
  const frame = snapshot.frames.find(f => f.frameVersionId === clip.occurrences[0]?.frameVersionId);
  const group = snapshot.alignmentGroups.find(g => g.alignmentGroupId === frame?.nativeScaleGroupId);
  return {width: group?.cell.width || 512, height: group?.cell.height || 512};
}
export function toolBlockReason(s: Pick<Studio, 'base' | 'commands' | 'conflict' | 'busy' | 'service'>): string | undefined {
  if (!s.base) return '저장된 프로젝트를 먼저 여세요.';
  if (s.conflict) return '저장 충돌을 먼저 해결하세요.';
  if (s.commands.length) return '편집 초안을 먼저 저장하세요. 도구는 저장된 동작을 사용합니다.';
  if (s.busy) return '현재 요청이 끝난 뒤 실행하세요.';
  if (s.service?.worker !== 'ready') return '처리 서비스가 연결되어야 실행할 수 있습니다.';
}
export function validateClipSource(snapshot: Snapshot, clip: Clip | undefined, follow: boolean): string | undefined {
  if (!clip || !clip.clipRevisionId) return '저장된 동작을 먼저 선택하세요.';
  if (follow && !clip.loop) return '부위 흔들림은 반복 동작에서만 사용할 수 있습니다.';
  if (clip.occurrences.length < (follow ? 4 : 1) || clip.occurrences.length > 64) return follow ? '반복 동작의 슬롯이 4~64개여야 합니다.' : '검사할 슬롯이 1~64개여야 합니다.';
  if (clip.occurrences.some(o => !Number.isInteger(o.durationMs) || o.durationMs <= 0) || clip.occurrences.reduce((sum, o) => sum + o.durationMs, 0) > 60000) return '슬롯 표시 시간은 양의 정수이며 전체 재생 시간은 60초 이하여야 합니다.';
  const cell = clipCell(snapshot, clip);
  if (![cell.width, cell.height].every(n => Number.isInteger(n) && n >= 2 && n <= 1024) || cell.width * cell.height * clip.occurrences.length > 16777216) return '셀은 최대 1024 × 1024, 전체 셀은 16,777,216픽셀 이하여야 합니다.';
  for (const occurrence of clip.occurrences) {
    const frame = snapshot.frames.find(f => f.frameVersionId === occurrence.frameVersionId);
    if (!frame || !snapshot.assets.some(a => a.assetId === frame.imageAssetId)) return '슬롯의 원본 이미지가 없습니다.';
    const groups = snapshot.alignmentGroups.filter(g => g.frameVersionIds.includes(frame.frameVersionId));
    if (groups.length !== 1 || groups[0].alignmentGroupId !== frame.nativeScaleGroupId) return '후보의 크기·발 정렬 그룹을 확인하세요.';
    const other = groups[0].cell;
    if ( (other.width !== cell.width || other.height !== cell.height)) return '모든 슬롯의 출력 셀 크기를 같게 맞추세요.';
  }
}
function numeric(text: string) {return text.trim() ? Number(text) : NaN;}
export function followParams(snapshot: Snapshot, clip: Clip, fields: FollowFields): Record<string, unknown> {
  const sourceError = validateClipSource(snapshot, clip, true); if (sourceError) throw new Error(sourceError);
  const region = fields.region.map(numeric) as Region, [cx, cy, rx, ry] = region, {width, height} = clipCell(snapshot, clip);
  if (!region.every(Number.isFinite) || rx <= 0 || ry <= 0 || cx - rx < 0 || cy - ry < 0 || cx + rx > width || cy + ry > height) throw new Error('영역의 중심 X·Y와 반지름 X·Y를 모두 입력하세요. 타원은 출력 셀 안에 있어야 합니다.');
  const gain = numeric(fields.gain), freq = numeric(fields.freq), damping = numeric(fields.damping);
  if (!Number.isFinite(gain) || gain < 0 || gain > 8) throw new Error('흔들림 강도는 0~8이어야 합니다.');
  if (!Number.isFinite(freq) || freq < 0.2 || freq > 12) throw new Error('반응 주파수는 0.2~12 Hz여야 합니다.');
  if (!Number.isFinite(damping) || damping < 0.05 || damping > 4) throw new Error('감쇠는 0.05~4여야 합니다.');
  if (!['lower', 'refuse'].includes(fields.onFold)) throw new Error('접힘 처리 방법을 선택하세요.');
  return {clipId: clip.clipId, clipRevisionId: clip.clipRevisionId, region, gain, freq, damping, onFold: fields.onFold};
}
export function handedParams(snapshot: Snapshot, clip: Clip, fields: HandedFields): Record<string, unknown> {
  const sourceError = validateClipSource(snapshot, clip, false); if (sourceError) throw new Error(sourceError);
  if (!fields.item.trim() || fields.item.trim().length > 160) throw new Error('검사할 장비 이름을 1~160자로 입력하세요.');
  if (!['left', 'right'].includes(fields.side) || !['wrist', 'hand', 'head', 'ankle', 'body'].includes(fields.part) || !['side', 'front', 'back', 'front_diagonal', 'back_diagonal'].includes(fields.direction) || !['left', 'right'].includes(fields.facing)) throw new Error('장비의 좌우·부위·시점·방향을 선택하세요.');
  if (!/^#[0-9a-f]{6}$/i.test(fields.marker)) throw new Error('표식 색은 #RRGGBB 형식으로 입력하세요.');
  const rgb = [1, 3, 5].map(i => parseInt(fields.marker.slice(i, i + 2), 16)), max = Math.max(...rgb);
  if (!max || (max - Math.min(...rgb)) / max < 0.2) throw new Error('회색·흰색·검정 대신 장비에만 있는 채도 높은 표식 색을 고르세요.');
  if (fields.referenceAssetId && !snapshot.assets.some(a => a.assetId === fields.referenceAssetId && a.alphaStats?.transparent > 0 && a.width * a.height <= 16777216)) throw new Error('이 프로젝트의 투명 기준 그림을 선택하세요.');
  return {clipId: clip.clipId, clipRevisionId: clip.clipRevisionId, item: fields.item.trim(), side: fields.side, part: fields.part, direction: fields.direction, facing: fields.facing, marker: fields.marker, ...(fields.referenceAssetId ? {referenceAssetId: fields.referenceAssetId} : {})};
}
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(v => typeof v === 'string');
/** Result names are not URLs. Only artifact entries returned by the job may supply media URLs. */
export function readClipToolResult(job?: Job): ClipToolResult | undefined {
  const result: unknown = job?.result;
  if (!object(result) || result.version !== 'clip-tools-v1' || !['follow', 'handed'].includes(String(result.tool)) || !object(result.source) || !object(result.preview) || !object(result.report) || !object(result.settings)) return;
  const source = result.source, preview = result.preview, report = result.report;
  if (!['projectId', 'clipId', 'clipRevisionId'].every(k => typeof source[k] === 'string') || !Number.isInteger(source.projectRevision) || !strings(source.occurrenceIds)) return;
  const occurrenceIds = source.occurrenceIds;
  if (![preview.width, preview.height, preview.frameCount].every(n => typeof n === 'number' && Number.isInteger(n) && n > 0) || Number(preview.frameCount) > 64 || Number(preview.width) > 1024 || Number(preview.height) > 1024 || !Array.isArray(preview.durationsMs) || preview.durationsMs.length !== preview.frameCount || preview.frameCount !== source.occurrenceIds.length || !preview.durationsMs.every(n => Number.isInteger(n) && n > 0) || !['before', 'beforeStrip', 'firstFrame'].every(k => typeof preview[k] === 'string')) return;
  if (result.tool === 'follow' && (!Number.isFinite(report.gainRequested) || !Number.isFinite(report.gainApplied) || typeof report.foldLimited !== 'boolean' || typeof preview.after !== 'string' || typeof preview.afterStrip !== 'string')) return;
  if (result.tool === 'handed' && (!['clear', 'suspect', 'inconclusive'].includes(String(report.verdict)) || !Number.isInteger(report.framesShown) || report.frameCount !== preview.frameCount || !Array.isArray(report.suspectFrames) || !report.suspectFrames.every(f => object(f) && Number.isInteger(f.index) && Number(f.index) >= 0 && Number(f.index) < Number(preview.frameCount) && typeof f.occurrenceId === 'string' && occurrenceIds[Number(f.index)] === f.occurrenceId && strings(f.reasons)) || !strings(report.unchecked))) return;
  return result as ClipToolResult;
}
export const artifactUrl = (job: Job, name: string | undefined) => name ? job.artifacts?.find(a => a.name === name)?.url : undefined;
export function previewMatches(request: ToolRequest | undefined, job: Job | undefined, source: ClipToolSource, fields: FollowFields): boolean {
  const result = readClipToolResult(job);
  if (!request || !job || job.operation !== 'preview_follow' || job.inputRevision !== source.projectRevision || !jobSucceeded(job) || !result || result.tool !== 'follow' || !sameSource(request.source, source) || !sameSource(result.source, source) || request.settingsKey !== settingsKey(fields)) return false;
  const settings = result.settings;
  return settings.clipId === source.clipId && settings.clipRevisionId === source.clipRevisionId && Array.isArray(settings.region) && settings.region.length === 4 && settings.region.every((v, i) => v === numeric(fields.region[i])) && settings.gain === numeric(fields.gain) && settings.freq === numeric(fields.freq) && settings.damping === numeric(fields.damping) && settings.onFold === fields.onFold && [result.preview.before, result.preview.beforeStrip, result.preview.firstFrame, result.preview.after, result.preview.afterStrip].every(name => !!artifactUrl(job, name));
}
export function regionFromDrag(start: [number, number], end: [number, number], width: number, height: number): Region {
  const x1 = Math.max(0, Math.min(width, start[0])), y1 = Math.max(0, Math.min(height, start[1]));
  const x2 = Math.max(0, Math.min(width, end[0])), y2 = Math.max(0, Math.min(height, end[1]));
  return [(x1 + x2) / 2, (y1 + y2) / 2, Math.abs(x1 - x2) / 2, Math.abs(y1 - y2) / 2];
}
export const frameStartMs = (durations: number[], index: number) => durations.slice(0, index).reduce((sum, duration) => sum + duration, 0);
export const handedWarning = (report: HandedReport) => report.framesShown === 0 || report.verdict === 'inconclusive' ? '표식을 충분히 찾지 못해 판단할 수 없습니다. 표식 색과 기준 그림을 확인하세요.' : report.verdict === 'suspect' ? '장비 위치가 의심되는 프레임을 직접 확인하세요.' : '표식 색 기준으로 의심 항목이 없습니다. 수동 승인은 별도로 진행하세요.';
