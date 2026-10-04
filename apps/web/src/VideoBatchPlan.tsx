import {useRef, useState} from 'react';
import {api, ApiError} from './api';
import {uid, type Job, type Snapshot} from './types';
import type {Studio} from './useStudio';
import {
  VIDEO_BATCH_LIMIT, VIDEO_DIRECTIONS, VIDEO_MODELS, VIDEO_STATES,
  videoBatchItem, videoBatchRequest, type VideoBatchItem, type VideoGenerationSettings, type VideoProcessingSettings,
} from './videoWorkflow';

type BatchRequest = ReturnType<typeof videoBatchRequest>;

/** The attempted body remains immutable so an uncertain acknowledgement can be retried safely. */
export function VideoBatchPlan({s, generation, processing, available, active, visible, onSubmitted}: {
  s: Studio; generation: VideoGenerationSettings; processing: VideoProcessingSettings;
  available: boolean; active: boolean; visible: boolean; onSubmitted: () => void;
}) {
  const [items, setItems] = useState<VideoBatchItem[]>([]);
  const [key, setKey] = useState('');
  const [attempted, setAttempted] = useState<BatchRequest | null>(null);
  const [error, setError] = useState('');
  const pending = useRef<BatchRequest | null>(null);
  const submitting = useRef(false);
  const snapshot = s.snapshot!;
  const locked = s.busy || !!s.commands.length || !!s.conflict;
  const requestBlocked = locked || !attempted && (active || !available || s.service?.worker !== 'ready');
  function add() {
    if (locked || attempted || submitting.current || items.length >= VIDEO_BATCH_LIMIT) return;
    try {
      const item = videoBatchItem(snapshot, generation, processing);
      setItems(previous => [...previous, item]); setKey(uid()); setError('');
    } catch (e) { setError((e as Error).message); }
  }
  function remove(index: number) {
    if (locked || attempted || submitting.current) return;
    setItems(previous => previous.filter((_, i) => i !== index)); setKey(uid()); setError('');
  }
  async function submit() {
    if (requestBlocked || submitting.current || !items.length) return;
    setError('');
    try {
      if (!pending.current && items.some(item => item.params.repairMode === 'on' || item.params.matchClipId) && s.providers.find(provider => provider.providerId === 'grok-video')?.capabilities?.rife?.available !== true) throw new Error('RIFE 보정·주기 맞춤을 사용할 수 없습니다. 해당 항목의 보정 설정을 확인해 다시 담아 주세요.');
      // Preserve the first inputRevision too: later project refreshes must not alter a retry.
      const body = pending.current ?? videoBatchRequest(snapshot, items, key);
      pending.current = body; setAttempted(body); submitting.current = true;
      const outcome = await s.run(async () => {
        const refresh = async () => {
          const results = await Promise.allSettled([
            api<Snapshot>(`/projects/${snapshot.projectId}`).then(s.setBase),
            s.refreshDetails(snapshot.projectId), s.refreshProjects(),
          ]);
          return results.some(result => result.status === 'rejected');
        };
        let result: {batchId: string; jobs: Job[]};
        try { result = await api(`/projects/${snapshot.projectId}/video-batches`, 'POST', body); }
        catch (e) {
          // Classify only the submission response. A refresh failure after an ACK
          // must never turn an accepted request into a new editable submission.
          if (e instanceof ApiError && e.status >= 400 && e.status < 500 && e.status !== 408) {
            return {kind: 'rejected' as const, message: e.message, refreshFailed: await refresh()};
          }
          return {kind: 'unknown' as const};
        }
        if (!result?.batchId || !Array.isArray(result.jobs)) return {kind: 'unknown' as const};
        return {kind: 'accepted' as const, refreshFailed: await refresh()};
      });
      if (outcome?.kind === 'rejected') {
        pending.current = null; setAttempted(null); setKey(uid());
        setError(`${outcome.message} 묶음은 접수되지 않았습니다. 항목을 수정한 뒤 다시 제출해 주세요.${outcome.refreshFailed ? ' 최신 프로젝트를 불러오지 못했으니 연결도 확인해 주세요.' : ''}`);
        return;
      }
      if (outcome?.kind !== 'accepted') {
        setError('접수 결과를 확인하지 못했습니다. 같은 요청으로 다시 확인해 주세요. 담은 설정과 요청 식별자는 유지됩니다.');
        return;
      }
      setItems([]); setKey(''); setAttempted(null); pending.current = null;
      s.setNotice(`영상 ${body.items.length}건을 묶음으로 접수했습니다. 각 작업에서 진행 상태를 확인하세요.`);
      if (outcome.refreshFailed) setError('묶음은 접수됐지만 화면을 갱신하지 못했습니다. 연결을 확인한 뒤 작업 목록을 새로고침해 주세요.');
      onSubmitted();
    } catch (e) { setError((e as Error).message); }
    finally { submitting.current = false; }
  }
  return <section className="video-batch" aria-label="영상 묶음 제작" hidden={!visible}>
    <h3>여러 동작 함께 만들기</h3>
    <p className="caption">현재 기준 그림·동작·방향을 한 건씩 담습니다. 방향마다 사용할 그림을 직접 선택하세요.</p>
    <button type="button" disabled={locked || !!attempted || items.length >= VIDEO_BATCH_LIMIT} onClick={add}>현재 설정을 묶음에 추가</button>
    <p className="caption">최대 {VIDEO_BATCH_LIMIT}건 · 추가만으로 생성하지 않습니다. 기준 그림은 그대로 사용합니다.</p>
    {items.length ? <>
      <ol className="video-batch-items">
        {items.map((item, index) => <li key={`${key}-${index}`}>
          <div><strong>{index + 1}. {snapshot.assets.find(asset => asset.assetId === item.assetId)?.originalFilename || '기준 이미지 없음'}</strong>
            <span>{VIDEO_STATES.find(state => state.id === item.params.state)?.label} · {VIDEO_DIRECTIONS.find(direction => direction.id === item.params.direction)?.label} · {item.params.facing === 'left' ? '왼쪽' : '오른쪽'}</span>
            <span>{VIDEO_MODELS.find(model => model.id === item.params.model)?.label} · {item.params.durationSeconds}초 · {item.params.resolution} · {item.params.finishMode === 'gif' ? 'GIF 색상' : 'RGBA 유지'}</span>
            {item.params.repairMode !== 'off' ? <span>RIFE 보정 {item.params.repairMode === 'on' ? '필수' : '자동'}</span> : null}
            {typeof item.params.matchClipId === 'string' ? <span>주기 맞춤 · {snapshot.clips.find(clip => clip.clipId === item.params.matchClipId)?.name || '대상 동작 없음'}</span> : null}
          </div>
          <button type="button" aria-label={`묶음 ${index + 1}번 제거`} disabled={locked || !!attempted} onClick={() => remove(index)}>제거</button>
        </li>)}
      </ol>
      <p className="video-batch-summary"><strong>영상 {items.length}건 · 총 {items.reduce((sum, item) => sum + item.params.durationSeconds, 0)}초</strong><br/>각 영상마다 Grok 로그인 사용량이 차감됩니다.</p>
      {attempted ? <p className="caption">이미 보낸 설정으로 접수 결과를 확인합니다. 확인 전에는 항목을 변경하지 않습니다.</p> : null}
      <button type="button" className="primary full" disabled={requestBlocked} onClick={submit}>{attempted ? '같은 묶음의 접수 결과 다시 확인' : `영상 ${items.length}건 생성`}</button>
    </> : null}
    {error ? <p role="alert" className="error">{error}</p> : null}
  </section>;
}
