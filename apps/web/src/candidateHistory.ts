import type {Asset, Frame, Job, Snapshot} from './types';

type RecordValue = Record<string, unknown>;
const record = (value: unknown): RecordValue => value && typeof value === 'object' && !Array.isArray(value) ? value as RecordValue : {};
const records = (value: unknown) => Array.isArray(value) ? value.map(record) : [];
const string = (value: unknown) => typeof value === 'string' && value ? value : undefined;
const strings = (value: unknown) => Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [];

export interface CandidateUse {clipId: string; clipName: string; occurrenceId: string; slot: number}
export interface CandidateGeneration {
  id: string; jobId?: string; provider?: string; model?: string; createdAt?: string;
  sourceAssetIds: string[]; recorded: boolean;
}
export interface CandidateEntry {
  frame: Frame; number: number; lineage: Asset[]; issues: string[];
  generations: CandidateGeneration[]; extractionJobs: Job[]; uses: CandidateUse[];
}
export interface CandidateGroup {
  id: string; kind: 'extraction' | 'unlinked'; entries: CandidateEntry[];
  sourceAssetIds: string[]; generations: CandidateGeneration[]; jobs: Job[];
  nativeScaleGroupId?: string;
}
export interface CandidateRun {
  id: string; operation: string; job?: Job; revision?: number; createdAt?: string;
  candidateCount: number; reason?: string;
}

/** Only explicit identifiers establish lineage. Names, dates, array order and
 * alignment-group membership cannot establish an extraction execution. */
export function buildCandidateHistory(snapshot: Snapshot, jobs: Job[], includeHidden = false) {
  const assets = new Map(snapshot.assets.map(a => [a.assetId, a]));
  const generationRecords = [...snapshot.generations, ...jobs.flatMap(j => records(record(j.result).generations))];
  const generations = new Map<string, CandidateGeneration>();
  for (const value of generationRecords) {
    const g = record(value), id = string(g.generationVersionId);
    if (!id || generations.has(id)) continue;
    const request = record(g.requestSnapshot);
    generations.set(id, {id, jobId: string(g.jobId), provider: string(g.providerId), model: string(g.model),
      createdAt: string(request.createdAt), sourceAssetIds: strings(g.rawAssetIds), recorded: true});
  }
  const extractionByFrame = new Map<string, Job[]>();
  for (const job of jobs.filter(j => j.operation === 'extract')) {
    // Some portable/newer records retain result.frames; current public jobs may
    // contain only savedRevision. A partial result must match only its own IDs.
    const result = record(job.result);
    const ids = new Set([...strings(result.frameVersionIds), ...records(result.frames).flatMap(f => string(f.frameVersionId) || [])]);
    for (const id of ids) extractionByFrame.set(id, [...(extractionByFrame.get(id) || []), job]);
  }
  const uses = new Map<string, CandidateUse[]>();
  for (const clip of snapshot.clips) clip.occurrences.forEach((o, index) => {
    uses.set(o.frameVersionId, [...(uses.get(o.frameVersionId) || []), {clipId: clip.clipId, clipName: clip.name, occurrenceId: o.occurrenceId, slot: index + 1}]);
  });
  const entries: CandidateEntry[] = snapshot.frames.map((frame, index) => {
    const lineage: Asset[] = [], issues: string[] = [], visited = new Set<string>();
    function trace(startId: string) {
      let id: string | undefined = startId;
      const path = new Set<string>();
      while (id) {
        if (path.has(id)) {issues.push('원본 계보에 순환 참조가 있습니다.'); break;}
        if (visited.has(id)) break;
        path.add(id); visited.add(id);
        const asset = assets.get(id);
        if (!asset) {issues.push(`자료 ${id}의 기록이 없습니다.`); break;}
        lineage.push(asset);
        id = string(record(asset.provenance).parentAssetId);
      }
    }
    trace(frame.imageAssetId);
    // rawAssetId is an explicit source link even when crop provenance is absent.
    if (!visited.has(frame.rawAssetId)) trace(frame.rawAssetId);
    const generationIds = new Set<string>();
    const frameGeneration = string(record(frame).generationVersionId);
    if (frameGeneration) generationIds.add(frameGeneration);
    for (const asset of lineage) {
      const generationId = string(record(asset.provenance).generationVersionId);
      if (generationId) generationIds.add(generationId);
      for (const g of generations.values()) if (g.sourceAssetIds.includes(asset.assetId)) generationIds.add(g.id);
    }
    const linkedGenerations = [...generationIds].map(id => generations.get(id) || {id, sourceAssetIds: [], recorded: false});
    if (linkedGenerations.some(g => !g.recorded)) issues.push('생성 ID는 있으나 해당 생성 상세 기록이 없습니다.');
    const extractionJobs = extractionByFrame.get(frame.frameVersionId) || [];
    if (extractionJobs.length > 1) issues.push('여러 추출 작업이 같은 후보 ID를 참조합니다. 실행 연결을 확인하세요.');
    return {frame, number: index + 1, lineage, issues, generations: linkedGenerations, extractionJobs, uses: uses.get(frame.frameVersionId) || []};
  });
  const groups = new Map<string, CandidateGroup>();
  for (const entry of entries.filter(e => includeHidden || !e.frame.hidden)) {
    const linked = entry.extractionJobs.length === 1;
    const id = linked ? `job:${entry.extractionJobs[0].jobId}` : JSON.stringify(['unlinked', entry.frame.nativeScaleGroupId || null, entry.frame.rawAssetId, entry.generations.map(g => g.id).sort()]);
    let group = groups.get(id);
    if (!group) {
      group = {id, kind: linked ? 'extraction' : 'unlinked', entries: [], sourceAssetIds: [], generations: [], jobs: [], nativeScaleGroupId: entry.frame.nativeScaleGroupId};
      groups.set(id, group);
    }
    group.entries.push(entry);
    if (!group.sourceAssetIds.includes(entry.frame.rawAssetId)) group.sourceAssetIds.push(entry.frame.rawAssetId);
    for (const g of entry.generations) if (!group.generations.some(existing => existing.id === g.id)) group.generations.push(g);
    for (const j of entry.extractionJobs) if (!group.jobs.some(existing => existing.jobId === j.jobId)) group.jobs.push(j);
  }
  const runs: CandidateRun[] = jobs.filter(j => ['generate', 'extract', 'cutout'].includes(j.operation)).map(job => {
    const revision = record(job.result).savedRevision;
    return {id: `job:${job.jobId}`, operation: job.operation, job, revision: typeof revision === 'number' ? revision : undefined, createdAt: job.createdAt,
      candidateCount: entries.filter(e => job.operation === 'extract' ? e.extractionJobs.some(j => j.jobId === job.jobId) : job.operation === 'generate' && e.generations.some(g => g.jobId === job.jobId)).length};
  });
  for (const value of snapshot.journal) {
    const item = record(value), reason = string(item.reason), revision = item.revision;
    const operation = reason?.match(/^(generate|extract|cutout) 결과 등록$/)?.[1];
    if (!operation || typeof revision !== 'number' || runs.some(r => r.revision === revision && r.operation === operation)) continue;
    runs.push({id: `revision:${revision}`, operation, revision, createdAt: string(item.createdAt), candidateCount: 0, reason});
  }
  runs.sort((a, b) => (b.createdAt || '').localeCompare(a.createdAt || ''));
  return {groups: [...groups.values()], runs};
}

export const candidateApprovalLabel = (review: string) => review === 'approved' ? '수동 승인됨' : review === 'rejected' ? '거절됨' : '승인 대기';
