import {useEffect, useId, useRef, useState, type PointerEvent} from 'react';
import type {Clip, Job, Snapshot} from './types';
import type {Studio} from './useStudio';
import {drawOccurrence, loadImage} from './render';
import {Input, Select} from './ui';
import {
  artifactUrl, clipCell, currentJob, defaultFollow, defaultHanded, followParams, frameStartMs, handedParams, handedWarning,
  jobPending, jobSucceeded, previewMatches, readClipToolResult, regionFromDrag, sameSource, settingsKey, sourceOf,
  toolBlockReason, validateClipSource, type ClipToolResult, type FollowFields, type HandedFields, type ToolRequest,
} from './clipTools';
import './clip-tools.css';

interface Props {s: Studio; clipId: string; onClip: (id: string) => void; onSelectOccurrence: (id: string) => void}
type Session = {selection: string; mode: 'follow' | 'handed'; follow: FollowFields; handed: HandedFields; preview?: ToolRequest; check?: ToolRequest; apply?: ToolRequest; sending: boolean; error: string};
const freshSession = (selection: string): Session => ({selection, mode: 'follow', follow: defaultFollow(), handed: defaultHanded(), sending: false, error: ''});
const message = (error: unknown) => error instanceof Error ? error.message : '요청을 완료하지 못했습니다.';
function validationError(check: () => unknown) {try {check(); return '';} catch (error) {return message(error);}}

export function ClipTools({s, clipId, onClip, onSelectOccurrence}: Props) {
  // Always resolve tool inputs from the saved snapshot, never the editable draft.
  const snapshot = s.base, savedId = s.resolveId(clipId), clip = snapshot?.clips.find(c => c.clipId === savedId);
  const selection = JSON.stringify([snapshot?.projectId, clipId, savedId]);
  const [session, setSession] = useState(() => freshSession(selection));
  const [open, setOpen] = useState(false);
  const inFlight = useRef(false);
  const epoch = useRef(0), mounted = useRef(true), opened = useRef('');
  const activeSelection = useRef(selection);
  if (activeSelection.current !== selection) {activeSelection.current = selection; epoch.current++; inFlight.current = false;}
  if (session.selection !== selection) setSession(freshSession(selection));
  const state = session.selection === selection ? session : freshSession(selection);
  useEffect(() => {mounted.current = true; return () => {mounted.current = false; epoch.current++;};}, []);
  const previewJob = currentJob(state.preview, s.jobs), checkJob = currentJob(state.check, s.jobs), applyJob = currentJob(state.apply, s.jobs);
  const pending = state.sending || [previewJob, checkJob, applyJob].some(jobPending);
  const source = snapshot && clip ? sourceOf(snapshot, clip) : undefined;
  const block = toolBlockReason(s), locked = !!block || pending;
  const followError = snapshot && clip ? validationError(() => followParams(snapshot, clip, state.follow)) : '저장된 동작을 먼저 선택하세요.';
  const checkError = snapshot && clip ? validationError(() => handedParams(snapshot, clip, state.handed)) : '저장된 동작을 먼저 선택하세요.';
  const followResult = readClipToolResult(previewJob), checkResult = readClipToolResult(checkJob);
  const validPreview = !!source && previewMatches(state.preview, previewJob, source, state.follow);
  const canSave = validPreview && !locked && !jobSucceeded(applyJob);
  const newClipId = jobSucceeded(applyJob) ? applyJob?.result?.clipId : undefined;
  // Polling may report job success before the refreshed project contains its new clip.
  useEffect(() => {
    if (!newClipId || !state.apply || state.selection !== selection || opened.current === newClipId || s.busy || s.commands.length || s.conflict || !clip || clip.clipRevisionId !== state.apply.source.clipRevisionId || !snapshot?.clips.some(c => c.clipId === newClipId)) return;
    opened.current = newClipId;
    onClip(newClipId);
  }, [newClipId, state.apply, state.selection, selection, s.busy, s.commands.length, s.conflict, clip, snapshot, onClip]);

  function updateFollow<K extends keyof FollowFields>(key: K, value: FollowFields[K]) {setSession(old => ({...old, follow: {...old.follow, [key]: value}, error: ''}));}
  function updateHanded(key: keyof HandedFields, value: string) {setSession(old => ({...old, handed: {...old.handed, [key]: value}, error: ''}));}
  async function submit(operation: 'preview_follow' | 'check_handed' | 'apply_follow') {
    if (toolBlockReason(s) || inFlight.current || pending || !snapshot || !clip || !source || activeSelection.current !== selection) return;
    let params: Record<string, unknown>;
    try {
      if (operation === 'apply_follow') {
        if (!canSave || !previewJob) return;
        params = {previewJobId: previewJob.jobId};
      } else params = operation === 'preview_follow' ? followParams(snapshot, clip, state.follow) : handedParams(snapshot, clip, state.handed);
    } catch (error) {setSession(old => ({...old, error: message(error)})); return;}
    inFlight.current = true;
    const requestEpoch = ++epoch.current;
    const key = operation === 'check_handed' ? settingsKey(state.handed) : settingsKey(state.follow);
    setSession(old => ({...old, sending: true, error: ''}));
    try {
      const response = await s.job(operation, [], params);
      if (!mounted.current || epoch.current !== requestEpoch || activeSelection.current !== selection) return;
      if (!response?.jobId) {setSession(old => ({...old, error: '작업 접수를 확인하지 못했습니다. 작업 센터의 오류를 확인하세요.'})); return;}
      const request: ToolRequest = {job: {status: 'queued', operation, inputRevision: snapshot.revision, ...response} as Job, source, settingsKey: key};
      setSession(old => operation === 'preview_follow' ? {...old, preview: request, apply: undefined} : operation === 'check_handed' ? {...old, check: request} : {...old, apply: request});
    } catch (error) {
      if (mounted.current && epoch.current === requestEpoch && activeSelection.current === selection) setSession(old => ({...old, error: message(error)}));
    } finally {
      if (mounted.current && epoch.current === requestEpoch && activeSelection.current === selection) {inFlight.current = false; setSession(old => ({...old, sending: false}));}
    }
  }
  function selectResultFrame(result: ClipToolResult, index: number) {
    if (!source || !sameSource(result.source, source) || s.commands.length || s.conflict || s.busy) return;
    const occurrenceId = result.source.occurrenceIds[index];
    if (occurrenceId && clip?.occurrences.some(o => o.occurrenceId === occurrenceId)) onSelectOccurrence(occurrenceId);
  }
  const shownJob = state.mode === 'follow' ? previewJob : checkJob;
  const shownResult = state.mode === 'follow' ? followResult : checkResult;
  const shownRequest = state.mode === 'follow' ? state.preview : state.check;
  const stale = !!shownResult && (!source || !sameSource(shownResult.source, source) || shownRequest?.settingsKey !== settingsKey(state.mode === 'follow' ? state.follow : state.handed));
  const canNavigate = !!source && !!shownResult && sameSource(shownResult.source, source) && !s.commands.length && !s.conflict && !s.busy;

  return <details className="clip-tools aw-property-group" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>동작 보완·검사</summary>
    <p className="caption">저장된 동작의 전체 슬롯을 처리합니다. 외부 이미지 생성이나 생성 과금은 없습니다.</p>
    {block ? <p className="warning" role="status">{block}</p> : null}
    <Select label="보완·검사 도구" value={state.mode} onChange={event => setSession(old => ({...old, mode: event.target.value as Session['mode'], error: ''}))}>
      <option value="follow">부위 흔들림</option><option value="handed">장비 좌우 검사</option>
    </Select>
    {snapshot && clip ? <>
      <p className="caption">입력: {clip.name} · 저장 버전 {snapshot.revision} · {clip.occurrences.length}슬롯 · {clip.occurrences.reduce((sum, o) => sum + o.durationMs, 0)}ms</p>
      {state.mode === 'follow' ? <form onSubmit={event => {event.preventDefault(); void submit('preview_follow');}}>
        <fieldset disabled={locked}>
          <legend>부위 흔들림 설정</legend>
          <p className="caption">첫 슬롯에서 흔들 부위를 드래그하거나 타원 좌표를 입력하세요. 모든 프레임에서 움직이는 타원이 셀 안에 있어야 합니다. 밖으로 나가면 영역을 줄이거나 옮기세요.</p>
          <RegionSelector key={selection} snapshot={snapshot} clip={clip} fields={state.follow} enabled={open} disabled={locked} onRegion={region => updateFollow('region', region)}/>
          <div className="clip-tools-grid">{(['중심 X', '중심 Y', '반지름 X', '반지름 Y'] as const).map((label, index) => <Input key={label} label={label} type="number" required step="any" min={index > 1 ? 0.01 : 0} value={state.follow.region[index]} onChange={event => {const region = [...state.follow.region] as FollowFields['region']; region[index] = event.target.value; updateFollow('region', region);}}/>)}</div>
          <div className="clip-tools-grid">
            <Input label="흔들림 강도" type="number" required min={0} max={8} step="any" value={state.follow.gain} onChange={event => updateFollow('gain', event.target.value)}/>
            <Input label="반응 주파수 (Hz)" type="number" required min={0.2} max={12} step="any" value={state.follow.freq} onChange={event => updateFollow('freq', event.target.value)}/>
            <Input label="감쇠" type="number" required min={0.05} max={4} step="any" value={state.follow.damping} onChange={event => updateFollow('damping', event.target.value)}/>
          </div>
          <Select label="과도한 접힘이 생길 때" value={state.follow.onFold} onChange={event => updateFollow('onFold', event.target.value as FollowFields['onFold'])}><option value="lower">강도를 낮추고 알림</option><option value="refuse">처리 중단</option></Select>
          {followError ? <p className="caption">{followError}</p> : null}
          <button type="submit" className="aw-wide" disabled={locked || !!followError}>흔들림 미리보기</button>
        </fieldset>
      </form> : <form onSubmit={event => {event.preventDefault(); void submit('check_handed');}}>
        <fieldset disabled={locked}>
          <legend>장비 좌우 검사 설정</legend>
          <p className="caption">장비를 의미로 자동 인식하지 않습니다. 장비에만 있는 채도 높은 색을 찾아 좌우를 비교합니다. 좌우는 캐릭터 자신의 기준입니다.</p>
          <Input label="장비 이름" required maxLength={160} value={state.handed.item} onChange={event => updateHanded('item', event.target.value)} placeholder="예: 손목 시계"/>
          <div className="clip-tools-grid">
            <Select label="착용 좌우" value={state.handed.side} onChange={event => updateHanded('side', event.target.value)}><option value="left">왼쪽</option><option value="right">오른쪽</option></Select>
            <Select label="착용 부위" value={state.handed.part} onChange={event => updateHanded('part', event.target.value)}><option value="wrist">손목</option><option value="hand">손</option><option value="head">머리</option><option value="ankle">발목</option><option value="body">몸통</option></Select>
            <Select label="보는 시점" value={state.handed.direction} onChange={event => updateHanded('direction', event.target.value)}><option value="side">측면</option><option value="front">정면</option><option value="back">후면</option><option value="front_diagonal">앞 대각선</option><option value="back_diagonal">뒤 대각선</option></Select>
            <Select label="바라보는 방향" value={state.handed.facing} onChange={event => updateHanded('facing', event.target.value)}><option value="left">왼쪽</option><option value="right">오른쪽</option></Select>
          </div>
          <Input label="장비 표식 색" type="color" value={state.handed.marker} onChange={event => updateHanded('marker', event.target.value)}/>
          <Input label="표식 색 코드" value={state.handed.marker} required pattern="#[0-9a-fA-F]{6}" onChange={event => updateHanded('marker', event.target.value)}/>
          <Select label="장비가 온전히 보이는 투명 기준 그림 (선택)" value={state.handed.referenceAssetId} onChange={event => updateHanded('referenceAssetId', event.target.value)}><option value="">사용하지 않음</option>{snapshot.assets.filter(asset => asset.alphaStats?.transparent > 0).map(asset => <option key={asset.assetId} value={asset.assetId}>{asset.originalFilename}</option>)}</Select>
          <p className="caption">투명 픽셀이 있는 이 프로젝트의 그림만 표시합니다. 장비 표식이 온전히 보이는 기준 그림을 선택하세요.</p>
          {checkError ? <p className="caption">{checkError}</p> : null}
          <button type="submit" className="aw-wide" disabled={locked || !!checkError}>장비 좌우 검사</button>
        </fieldset>
      </form>}
      {state.error ? <p className="error" role="alert">{state.error}</p> : null}
      {state.sending ? <p role="status">요청을 접수하고 있습니다.</p> : null}
      <ToolJobStatus job={shownJob}/>
      {shownResult && shownJob && jobSucceeded(shownJob) ? <>
        {stale ? <p className="warning" role="status">원본·프로젝트 버전 또는 설정이 달라졌습니다. 현재 설정으로 다시 실행하세요.</p> : null}
        {shownResult.tool === 'follow' ? <>
          {shownResult.report.foldLimited ? <p className="warning" role="alert">접힘을 막기 위해 강도를 낮췄습니다: 요청 {shownResult.report.gainRequested} → 적용 {shownResult.report.gainApplied}. 결과를 확인하세요.</p> : null}
          {shownResult.report.unchanged ? <p className="warning">움직임 변화가 없습니다. 선택 영역과 강도를 확인하세요.</p> : null}
        </> : <>
          <p className={shownResult.report.verdict === 'clear' && shownResult.report.framesShown > 0 ? 'caption' : 'warning'} role="status">{handedWarning(shownResult.report)}</p>
          <p className="caption">표식 확인 {shownResult.report.framesShown} / {shownResult.report.frameCount}프레임 · 자동 수정·승인 없음</p>
          {shownResult.report.unchecked.length ? <div className="warning"><strong>검사하지 못한 항목</strong><ul>{shownResult.report.unchecked.map((reason, i) => <li key={i}>{reason}</li>)}</ul></div> : null}
          <ul className="clip-tools-suspects" aria-label="의심 프레임">{shownResult.report.suspectFrames.map(frame => <li key={frame.occurrenceId}><button type="button" disabled={!canNavigate} onClick={() => selectResultFrame(shownResult, frame.index)}>슬롯 {frame.index + 1} 선택</button><span>{frame.reasons.join(' · ') || '표식 위치를 확인하세요.'}</span></li>)}</ul>
        </>}
        <ClipToolComparison key={shownJob.jobId} job={shownJob} result={shownResult} enabled={open} canNavigate={canNavigate} onSelectFrame={index => selectResultFrame(shownResult, index)}/>
      </> : null}
      {state.mode === 'follow' && previewJob ? <>
        <button type="button" className="primary aw-wide" disabled={!canSave} onClick={() => void submit('apply_follow')}>새 동작으로 저장</button>
        <p className="caption">확인한 미리보기를 새 동작으로 저장합니다. 새 프레임과 동작은 검수 대기 상태입니다.</p>
        <ToolJobStatus job={applyJob}/>
        {newClipId ? <p role="status">새 동작을 저장했습니다.{snapshot.clips.some(c => c.clipId === newClipId) ? <button type="button" disabled={!!block} onClick={() => onClip(newClipId)}>새 동작 열기</button> : ' 저장된 동작 목록을 확인하고 있습니다.'}</p> : null}
      </> : null}
    </> : <p className="caption">저장된 동작을 먼저 선택하세요.</p>}
  </details>;
}

function ToolJobStatus({job}: {job?: Job}) {
  if (!job) return null;
  if (jobPending(job)) return <p role="status">{job.operation === 'apply_follow' ? '새 동작을 저장하고 있습니다.' : '저장된 슬롯을 처리하고 있습니다.'}</p>;
  if (jobSucceeded(job)) return job.operation !== 'apply_follow' && !readClipToolResult(job) ? <p className="warning" role="alert">미리보기 결과 형식을 확인하지 못했습니다. 작업 센터의 결과를 확인하세요.</p> : null;
  return <div className="error" role="alert"><p>작업이 완료되지 않았습니다.</p>{(job.errors || (job.error ? [job.error] : [])).map((error, i) => <p key={i}>{error.message || '작업 센터에서 오류를 확인하세요.'}</p>)}</div>;
}

export function RegionSelector({snapshot, clip, fields, enabled, disabled, onRegion}: {snapshot: Snapshot; clip: Clip; fields: FollowFields; enabled: boolean; disabled: boolean; onRegion: (region: FollowFields['region']) => void}) {
  const canvas = useRef<HTMLCanvasElement>(null), drag = useRef<{id: number; start: [number, number]} | null>(null);
  const [error, setError] = useState(''), [ready, setReady] = useState(false);
  const {width, height} = clipCell(snapshot, clip), first = clip.occurrences[0];
  const sourceError = validateClipSource(snapshot, clip, true);
  useEffect(() => {
    let active = true; setReady(false); setError('');
    if (!enabled || !first || sourceError) return;
    void drawOccurrence(snapshot, first, false).then(image => {
      if (!active) return;
      const context = canvas.current?.getContext('2d');
      if (!context) throw new Error('첫 슬롯 미리보기를 표시할 수 없습니다. 좌표로 영역을 입력하세요.');
      context.clearRect(0, 0, width, height); context.drawImage(image, 0, 0); setReady(true);
    }).catch(error => {if (active) setError(message(error));});
    return () => {active = false;};
  }, [snapshot, first, enabled, sourceError, width, height]);
  const values = fields.region.map(value => value.trim() ? Number(value) : NaN);
  const valid = values.every(Number.isFinite) && values[2] > 0 && values[3] > 0;
  function point(event: PointerEvent<SVGSVGElement>): [number, number] {
    const bounds = event.currentTarget.getBoundingClientRect();
    return [(event.clientX - bounds.left) * width / bounds.width, (event.clientY - bounds.top) * height / bounds.height];
  }
  function update(event: PointerEvent<SVGSVGElement>) {
    if (disabled || drag.current?.id !== event.pointerId) return;
    onRegion(regionFromDrag(drag.current.start, point(event), width, height).map(String) as FollowFields['region']);
  }
  return <div className="clip-tools-region">
    <div className="clip-tools-cell checker" style={{aspectRatio: `${width} / ${height}`}}>
      <canvas ref={canvas} width={width} height={height} aria-label="저장된 첫 슬롯, 팀 테두리 제외"/>
      <svg viewBox={`0 0 ${width} ${height}`} aria-label="흔들림 영역 드래그 선택" aria-disabled={disabled || !ready} onPointerDown={event => {
        if (disabled || !ready || event.button !== 0) return;
        event.preventDefault(); drag.current = {id: event.pointerId, start: point(event)}; event.currentTarget.setPointerCapture(event.pointerId);
      }} onPointerMove={update} onPointerUp={event => {update(event); if (drag.current?.id === event.pointerId) {drag.current = null; event.currentTarget.releasePointerCapture(event.pointerId);}}} onPointerCancel={() => {drag.current = null;}} onLostPointerCapture={() => {drag.current = null;}}>
        {valid ? <ellipse cx={values[0]} cy={values[1]} rx={values[2]} ry={values[3]}/> : null}
      </svg>
    </div>
    <p className="caption">저장된 첫 슬롯 · {width} × {height}px · 변형·정렬·픽셀 편집 반영, 팀 테두리 제외</p>
    {error ? <p className="warning" role="status">{error}</p> : null}
  </div>;
}

/** Both strips use the same source slot and its original duration, including variable timing. */
export function ClipToolComparison({job, result, enabled, canNavigate, onSelectFrame}: {job: Job; result: ClipToolResult; enabled: boolean; canNavigate: boolean; onSelectFrame: (index: number) => void}) {
  const [index, setIndex] = useState(0), [error, setError] = useState('');
  const canvas = useRef<HTMLCanvasElement>(null), id = useId();
  const preview = result.preview, after = result.tool === 'follow';
  const beforeUrl = artifactUrl(job, preview.before), afterUrl = artifactUrl(job, preview.after);
  const beforeStrip = artifactUrl(job, preview.beforeStrip), afterStrip = artifactUrl(job, preview.afterStrip), board = artifactUrl(job, preview.board);
  useEffect(() => {
    let active = true; setError('');
    const context = canvas.current?.getContext('2d');
    context?.clearRect(0, 0, preview.width * (after ? 2 : 1), preview.height);
    if (!enabled || !beforeStrip || after && !afterStrip) return;
    void Promise.all([loadImage(beforeStrip), ...(after && afterStrip ? [loadImage(afterStrip)] : [])]).then(images => {
      if (!active || !context) return;
      if (images.some(image => image.width !== preview.width * preview.frameCount || image.height !== preview.height)) throw new Error('프레임 시트 크기가 결과와 다릅니다. 작업 센터의 산출물을 확인하세요.');
      context.imageSmoothingEnabled = false;
      images.forEach((image, column) => context.drawImage(image, index * preview.width, 0, preview.width, preview.height, column * preview.width, 0, preview.width, preview.height));
    }).catch(error => {if (active) setError(message(error));});
    return () => {active = false;};
  }, [beforeStrip, afterStrip, enabled, after, index, preview.width, preview.height, preview.frameCount]);
  const missing = !beforeUrl || !beforeStrip || after && (!afterUrl || !afterStrip);
  return <section className="clip-tools-comparison" aria-label="처리 전후 비교">
    <div className="clip-tools-previews">
      {beforeUrl ? <figure><figcaption>저장된 원본 동작</figcaption><img className="checker" src={beforeUrl} alt="처리 전 원본 동작 WebP"/></figure> : null}
      {after && afterUrl ? <figure><figcaption>흔들림 미리보기</figcaption><img className="checker" src={afterUrl} alt="흔들림 적용 후 동작 WebP"/></figure> : null}
    </div>
    {missing ? <p className="warning" role="alert">비교 산출물을 찾지 못했습니다. 미리보기를 다시 실행하세요.</p> : null}
    <p className="caption">아래 프레임 비교는 원본 표시 시간을 기준으로 맞춥니다.{after ? ' 왼쪽: 이전 · 오른쪽: 이후' : ''}</p>
    <canvas className="clip-tools-strip checker" ref={canvas} width={preview.width * (after ? 2 : 1)} height={preview.height} aria-label={`슬롯 ${index + 1} ${after ? '이전·이후 동시 비교' : '원본 프레임'}`}/>
    {error ? <p className="warning" role="status">{error}</p> : null}
    <label htmlFor={id}>비교 프레임 {index + 1} / {preview.frameCount}</label>
    <input id={id} type="range" min={0} max={preview.frameCount - 1} step={1} value={index} aria-label="비교 프레임" onChange={event => {const next = Number(event.target.value); if (Number.isInteger(next) && next >= 0 && next < preview.frameCount) setIndex(next);}}/>
    <p className="caption">원본 시점 {frameStartMs(preview.durationsMs, index)}ms · 이 슬롯 {preview.durationsMs[index]}ms · 전체 {preview.durationsMs.reduce((sum, duration) => sum + duration, 0)}ms</p>
    <button type="button" disabled={!canNavigate} onClick={() => onSelectFrame(index)}>이 프레임을 재생 순서에서 선택</button>
    <details><summary>원본 슬롯별 표시 시간</summary><ol>{preview.durationsMs.map((duration, i) => <li key={i}>슬롯 {i + 1}: {duration}ms</li>)}</ol></details>
    {board ? <figure><figcaption>장비 좌우 검사 보드</figcaption><a href={board} target="_blank" rel="noreferrer"><img src={board} alt="장비 표식 위치와 의심 프레임 검사 보드"/></a><a href={board} download>검사 보드 PNG 다운로드</a></figure> : null}
  </section>;
}
