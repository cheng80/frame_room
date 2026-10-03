import {useMemo} from 'react';
import type {Asset, Job, Snapshot} from './types';
import {assetProvenanceLabel} from './assetProvenance';
import {buildCandidateHistory, candidateApprovalLabel, type CandidateGeneration} from './candidateHistory';
import './candidate-library.css';

export interface CandidateLibraryProps {
  snapshot: Snapshot; jobs: Job[]; includeHidden: boolean; selectedFrameId?: string;
  onSelect: (frameVersionId: string) => void;
  onUse: (clipId: string, occurrenceId: string) => void;
  onSource: (assetId: string) => void;
}
const shortId = (id: string) => id.slice(0, 8);
const operationName = (operation: string) => ({generate: '생성', extract: '추출', cutout: '배경 제거'}[operation] || operation);
const statusName = (status: string) => ({needs_review: '결과 등록 · 승인 별도', succeeded: '작업 완료', failed: '실패', queued: '대기', running: '진행 중', canceled: '취소', interrupted: '중단', provider_outcome_unknown: '생성 결과 확인 필요'}[status] || status);
const dateLabel = (date?: string) => date && Number.isFinite(Date.parse(date)) ? new Date(date).toLocaleString('ko-KR') : '실행 시각 미기록';
function JobLink({id}: {id: string}) {
  return <a href={`/v1/jobs/${encodeURIComponent(id)}`} target="_blank" rel="noreferrer" title={`작업 ${id} 원기록 JSON 열기`}>작업 {shortId(id)} ↗</a>;
}
function GenerationInfo({generation}: {generation: CandidateGeneration}) {
  return <p className="cl-meta">생성 <span title={generation.id}>{shortId(generation.id)}</span> · {generation.recorded ? [generation.provider, generation.model].filter(Boolean).join(' / ') || '제공자 미기록' : '상세 기록 없음'}{generation.jobId && <> · <JobLink id={generation.jobId}/></>}</p>;
}

export function CandidateLibrary({snapshot, jobs, includeHidden, selectedFrameId, onSelect, onUse, onSource}: CandidateLibraryProps) {
  const history = useMemo(() => buildCandidateHistory(snapshot, jobs, includeHidden), [snapshot, jobs, includeHidden]);
  const assets = useMemo(() => new Map(snapshot.assets.map(a => [a.assetId, a])), [snapshot.assets]);
  function sourceLink(id: string, prefix = '원본') {
    const asset: Asset | undefined = assets.get(id);
    return asset ? <button type="button" className="cl-link" title={`${asset.originalFilename} · ${id}`} onClick={() => onSource(id)}>{prefix} · {asset.originalFilename} <span>{shortId(id)}</span></button> : <span className="cl-note">{prefix} {shortId(id)} · 기록 없음</span>;
  }
  return <div className="aw-scroll aw-candidate-list cl-library" aria-label="제작 이력과 후보 묶음">
    <p className="cl-note">후보는 추천 순위가 아닙니다. 수동 승인은 자동 검사 결과와 별개입니다.</p>
    {history.groups.map((group, index) => <details className="cl-group" key={group.id} open>
      <summary><strong>{group.kind === 'extraction' ? '추출 실행' : '원본·정렬 묶음'} {index + 1}</strong><span>{group.entries.length}개 후보</span></summary>
      <div className="cl-group-info">
        {group.kind === 'unlinked' && <p className="cl-note">추출 실행 연결 미기록{group.nativeScaleGroupId && <> · 묶음 <span title={group.nativeScaleGroupId}>{shortId(group.nativeScaleGroupId)}</span></>}</p>}
        {group.sourceAssetIds.map(id => <div key={id}>{sourceLink(id)}</div>)}
        {group.generations.map(g => <GenerationInfo key={g.id} generation={g}/>)}
        {group.jobs.map(job => <p className="cl-meta" key={job.jobId}><JobLink id={job.jobId}/> · {dateLabel(job.createdAt)} · 입력 v{job.inputRevision} · {statusName(job.status)}</p>)}
      </div>
      {group.entries.map(entry => {
        const {frame, number} = entry, asset = assets.get(frame.imageAssetId);
        return <article className="cl-entry" key={frame.frameVersionId}>
          <button type="button" className={`aw-candidate ${selectedFrameId === frame.frameVersionId ? 'is-selected' : ''}`} aria-pressed={selectedFrameId === frame.frameVersionId} onClick={() => onSelect(frame.frameVersionId)}>
            <span className="aw-candidate-thumb checker">{asset && <img src={asset.url} alt="" loading="lazy"/>}</span>
            <span className="aw-candidate-info"><strong>후보 {number}</strong><small>{frame.hidden ? '숨김 · ' : ''}{candidateApprovalLabel(frame.review)}</small><small>{asset ? assetProvenanceLabel(asset, assets).originLabel || assetProvenanceLabel(asset, assets).label : '자료 기록 없음'}</small><small>{entry.uses.length}회 사용 · {shortId(frame.frameVersionId)}</small>{(frame.extractionReview?.warnings?.length||frame.extractionReview?.belowMinArea)?<small>추출 검사 경고 · 직접 확인</small>:null}</span>
          </button>
          <details className="cl-entry-detail">
            <summary>출처·사용처{entry.uses.length ? ` (${entry.uses.length})` : ''}</summary>
            <p className="cl-meta">추출 방식 버전: {frame.extractionVersion || '미기록'}<br/>원본 영역: {frame.sourceRect.x}, {frame.sourceRect.y} · {frame.sourceRect.width} × {frame.sourceRect.height}</p>
            {entry.lineage.slice().reverse().map(a => <div className="cl-lineage" key={a.assetId}><small>{assetProvenanceLabel(a, assets).label}</small>{sourceLink(a.assetId, a.assetId === frame.imageAssetId ? '후보 이미지' : '자료')}</div>)}
            {!entry.generations.length && <p className="cl-note">연결된 생성 기록 없음</p>}
            {entry.issues.map(issue => <p className="cl-note" key={issue}>{issue}</p>)}
            {frame.parentFrameVersionId && <p className="cl-meta">이전 후보 버전 {shortId(frame.parentFrameVersionId)}</p>}
            {frame.reviewReason && <p className="cl-note">승인 메모: {frame.reviewReason}</p>}
            <div className="cl-uses" aria-label={`후보 ${number} 사용처`}>
              {entry.uses.length ? entry.uses.map(use => <button type="button" key={`${use.clipId}:${use.occurrenceId}`} onClick={() => onUse(use.clipId, use.occurrenceId)}>{use.clipName} · 슬롯 {use.slot}로 이동</button>) : <p className="cl-note">사용 중인 클립 없음</p>}
            </div>
          </details>
        </article>;
      })}
    </details>)}
    {!history.groups.length && <p className="aw-empty">{snapshot.frames.length ? '표시할 후보가 없습니다. 숨긴 후보 포함을 확인하세요.' : '프레임 후보가 없습니다. 원본에서 프레임을 추출하세요.'}</p>}
    {!!history.runs.length && <details className="cl-history"><summary>생성·추출 실행 기록 ({history.runs.length})</summary>
      <p className="cl-note">후보 ID가 없는 실행은 후보 묶음과 연결하지 않습니다. 연결 수에는 숨긴 후보도 포함됩니다.</p>
      {history.runs.map(run => <article key={run.id}><strong>{operationName(run.operation)}{run.revision !== undefined ? ` · 저장 v${run.revision}` : ''}</strong><p className="cl-meta">{dateLabel(run.createdAt)}</p>{run.job ? <><JobLink id={run.job.jobId}/><p className="cl-meta">입력 v{run.job.inputRevision} · {statusName(run.job.status)}</p></> : <p className="cl-note">저장 이력만 있음 · 작업 연결 미기록</p>}<p className="cl-note">{run.candidateCount ? `${run.candidateCount}개 후보 연결 확인` : '연결 확인된 후보 없음'}</p></article>)}
    </details>}
  </div>;
}
