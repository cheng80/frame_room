import {useId, useMemo, useRef, useState, type FormEvent} from 'react';
import {api} from './api';
import {EditorCanvas} from './Canvas';
import {VideoBatchPlan} from './VideoBatchPlan';
import {JobCard} from './FinishSteps';
import type {Studio} from './useStudio';
import type {Snapshot, Video} from './types';
import {Empty, Field, Input, Select} from './ui';
import {
  approvedVideoReference, defaultVideoAssetId, defaultVideoProcessing, isVideoJob,
  validateVideoUpload, VIDEO_DIRECTIONS, VIDEO_MODELS, VIDEO_STATES, videoGenerationRequest,
  videoProcessingRequest, videoProvenanceLabel, type VideoGenerationSettings, type VideoProcessingSettings,
  videoBeforeFinishSnapshot, videoClipColorLabel, videoRangeBoundary,
  videoMatchClips,
} from './videoWorkflow';
import './video-tools.css';

export function VideoStep({s, onSelectClip}: {s: Studio; onSelectClip?: (clipId: string) => void}) {
  const p = s.snapshot!;
  const id = useId();
  const fileInput = useRef<HTMLInputElement>(null);
  const originalPlayer = useRef<HTMLVideoElement>(null);
  const submitting = useRef(false);
  const [pane, setPane] = useState<'preview' | 'settings'>('settings');
  const [mode, setMode] = useState<'generate' | 'process'>('generate');
  const [generation, setGeneration] = useState<VideoGenerationSettings>(() => ({
    assetId: defaultVideoAssetId(p), model: VIDEO_MODELS[0].id, durationSeconds: '3', resolution: '480p',
    direction: 'side', facing: 'right', motionPrompt: '',
  }));
  const [processing, setProcessing] = useState(defaultVideoProcessing);
  const [videoId, setVideoId] = useState('');
  const [spillReference, setSpillReference] = useState({videoId: '', assetId: ''});
  const [clipId, setClipId] = useState('');
  const [occurrenceId, setOccurrenceId] = useState('');
  const [beforeFinishClipId, setBeforeFinishClipId] = useState('');
  const [allJobs, setAllJobs] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState('');
  const videos = p.videos ?? [];
  const video = videos.find(v => v.videoId === videoId) ?? videos.at(-1);
  // Snapshot refreshes can change the fallback video without a dropdown event.
  const spillReferenceAssetId = spillReference.videoId === video?.videoId ? spillReference.assetId : '';
  const videoProvenance = video?.provenance;
  const hasVideoReference = !!videoProvenance && typeof videoProvenance === 'object' &&
    'referenceAssetId' in videoProvenance && typeof videoProvenance.referenceAssetId === 'string' && !!videoProvenance.referenceAssetId;
  const missingSpillReference = !!spillReferenceAssetId && !p.assets.some(a => a.assetId === spillReferenceAssetId);
  const asset = p.assets.find(a => a.assetId === generation.assetId);
  const reference = approvedVideoReference(p, generation.assetId);
  const provider = s.providers.find(item => item.providerId === 'grok-video' && item.mediaKind === 'video');
  const rife = provider?.capabilities?.rife;
  const rifeAvailable = rife?.available === true;
  const rifeReason = typeof rife?.reason === 'string' ? rife.reason : '보정 도구의 준비 상태를 확인하지 못했습니다. Grok 연결을 다시 확인해 주세요.';
  const available = !!provider && provider.available !== false && provider.loginReady !== false;
  const active = s.jobs.some(job => isVideoJob(job) && ['queued', 'running', 'cancel_requested'].includes(job.status));
  const locked = s.busy || !!s.commands.length || !!s.conflict;
  const disabled = locked || active || s.service?.worker !== 'ready';
  const videoJobs = s.jobs.filter(isVideoJob);
  const resultClipIds = new Set(videoJobs.filter(job => mode === 'generate' || job.result?.videoId === video?.videoId).map(job => job.result?.clipId));
  const clips = p.clips.filter(clip => resultClipIds.has(clip.clipId) || !!clip.sourceVideoId && (mode === 'generate' || clip.sourceVideoId === video?.videoId));
  const selectedClip = clips.find(clip => clip.clipId === clipId) ?? clips.at(-1);
  const beforeFinish = useMemo(() => selectedClip ? videoBeforeFinishSnapshot(p, selectedClip) : null, [p, selectedClip]);
  const colorLabel = useMemo(() => selectedClip ? videoClipColorLabel(p, selectedClip) : '', [p, selectedClip]);
  const comparing = beforeFinishClipId === selectedClip?.clipId && !!beforeFinish;
  const resultVideo = videos.find(v => v.videoId === selectedClip?.sourceVideoId);
  const matchClips = videoMatchClips(p);
  const missingMatchClip = !!processing.matchClipId && !matchClips.some(clip => clip.clipId === processing.matchClipId);
  const setGenerationField = <K extends keyof VideoGenerationSettings>(key: K, value: VideoGenerationSettings[K]) => setGeneration(previous => ({...previous, [key]: value}));
  const setProcessingField = <K extends keyof VideoProcessingSettings>(key: K, value: VideoProcessingSettings[K]) => setProcessing(previous => ({...previous, [key]: value}));

  function changeMode(next: 'generate' | 'process') {
    setMode(next); setError('');
    if (next === 'generate' && processing.loopMode === 'manual') setProcessingField('loopMode', 'auto');
  }
  function chooseVideo(value: string) {
    setVideoId(value); setClipId(''); setOccurrenceId(''); setBeforeFinishClipId(''); setError('');
    setSpillReference({videoId: value, assetId: ''});
    setProcessing(previous => ({...previous, startFrame: '0', endFrame: ''}));
  }
  function markRange(boundary: 'start' | 'end') {
    if (!video || !originalPlayer.current) return;
    const frame = videoRangeBoundary(video, originalPlayer.current.currentTime, boundary);
    if (frame === null) return;
    setProcessing(previous => ({...previous, loopMode: 'manual', [boundary === 'start' ? 'startFrame' : 'endFrame']: frame}));
    setError('');
  }
  async function upload() {
    if (!file || locked || submitting.current) return;
    setError('');
    try { validateVideoUpload(file); } catch (e) { setError((e as Error).message); return; }
    submitting.current = true;
    try {
      const body = new FormData();
      body.append('file', file);
      body.append('expectedRevision', String(p.revision));
      const result = await s.run(async () => {
        const response = await api<{snapshot: Snapshot; video: Video}>(`/projects/${p.projectId}/videos`, 'POST', body);
        s.setBase(response.snapshot);
        // The acknowledged upload remains visible even if a follow-up details lookup fails.
        await s.refreshDetails(p.projectId);
        return response;
      });
      if (!result) return;
      chooseVideo(result.video.videoId); setMode('process'); setPane('preview'); setFile(null);
      if (fileInput.current) fileInput.current.value = '';
      s.setNotice('원본 MP4를 등록했습니다. 구간을 선택해 후보를 추출하세요.');
    } finally { submitting.current = false; }
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (disabled || submitting.current || (mode === 'generate' && !available)) return;
    setError('');
    try {
      if (processing.repairMode === 'on' && !rifeAvailable) throw new Error(`RIFE 필수 보정을 사용할 수 없습니다. ${rifeReason}`);
      if (processing.matchClipId && !rifeAvailable) throw new Error(`주기 맞춤에 필요한 RIFE 보간을 사용할 수 없습니다. ${rifeReason}`);
      const request = mode === 'generate'
        ? videoGenerationRequest(p, generation, processing)
        : videoProcessingRequest(p, video?.videoId ?? '', {...processing, spillReferenceAssetId});
      submitting.current = true;
      const result = await s.job(request.operation, request.assetIds, request.params);
      if (result) setPane('preview');
    } catch (e) { setError((e as Error).message); }
    finally { submitting.current = false; }
  }
  const numericField = (key: keyof VideoProcessingSettings, label: string, min: number, max: number) =>
    <Input label={label} type="number" required min={min} max={max} step={1} value={processing[key]} onChange={e => setProcessingField(key, e.target.value)}/>;

  return <div className="source-tool video-tool" data-mobile-pane={pane} aria-label="영상으로 동작 만들기">
    <div className="source-tool-toolbar video-toolbar">
      <div role="group" aria-label="영상 작업 선택" className="source-tool-segments">
        <button type="button" aria-pressed={mode === 'generate'} onClick={() => changeMode('generate')}>새 영상 생성</button>
        <button type="button" aria-pressed={mode === 'process'} onClick={() => changeMode('process')}>기존 영상 처리</button>
      </div>
      <div className="video-upload">
        <Field label="MP4 가져오기 · 최대 64MiB"><input ref={fileInput} type="file" accept="video/mp4,.mp4" disabled={locked} onChange={e => {setFile(e.target.files?.[0] ?? null); setError('');}}/></Field>
        <button type="button" disabled={locked || !file} onClick={upload}>원본 영상 등록</button>
      </div>
      {error ? <p className="error" role="alert">{error}</p> : null}
    </div>
    <div className="source-tool-switch" role="group" aria-label="영상 도구 보기 전환">
      <button type="button" aria-pressed={pane === 'preview'} aria-controls={`${id}-preview`} onClick={() => setPane('preview')}>원본·작업 결과</button>
      <button type="button" aria-pressed={pane === 'settings'} aria-controls={`${id}-settings`} onClick={() => setPane('settings')}>설정</button>
    </div>
    <div className="source-tool-columns">
      <section id={`${id}-preview`} className="source-tool-preview source-tool-pane" aria-label="원본과 작업 결과">
        <h2 className="source-tool-heading">{mode === 'generate' ? '영상에 사용할 기준 이미지' : '보관된 원본 영상'}</h2>
        <div className="source-tool-scroll">
          {mode === 'generate' ? <>
            {asset ? <div className="video-reference checker"><img src={asset.url} alt={`영상 기준 · ${asset.originalFilename}`}/></div> : <Empty title="기준 이미지를 선택해 주세요"/>}
            {asset ? <p className="caption">{asset.originalFilename} · {reference ? '승인된 외형 기준 사용' : '선택한 이미지 사용'}</p> : null}
            {reference?.fixedTraits ? <p className="video-traits">{reference.fixedTraits}</p> : null}
          </> : <>
            <Select label="처리할 원본 영상" value={video?.videoId ?? ''} onChange={e => chooseVideo(e.target.value)}>
              {!videos.length ? <option value="">등록된 영상 없음</option> : null}
              {videos.map(v => <option key={v.videoId} value={v.videoId}>{v.originalFilename} · {(v.durationMs / 1000).toFixed(2)}초</option>)}
            </Select>
            {video ? <>
              <video ref={originalPlayer} key={video.videoId} className="video-original" src={video.url} controls playsInline preload="metadata" aria-label={`원본 영상 · ${video.originalFilename}`}/>
              <p className="caption">{videoProvenanceLabel(video)} · {video.width} × {video.height} · {video.fps.toFixed(2)}fps · {video.frameCount}프레임</p>
              <a className="button" href={video.url} download={video.originalFilename}>원본 MP4 다운로드</a>
              <div className="video-range-actions" role="group" aria-label="영상 위치로 추출 구간 지정">
                <button type="button" onClick={() => markRange('start')}>현재 위치를 시작으로</button>
                <button type="button" onClick={() => markRange('end')}>현재 위치 다음까지</button>
              </div>
              {processing.loopMode === 'manual' ? <p className="caption" role="status">선택 구간 [{processing.startFrame}, {processing.endFrame || video.frameCount}) · 설정에서 프레임 번호를 조정할 수 있습니다.</p> : null}
              <p className="caption">영상 위치는 평균 fps로 환산합니다. 추출 범위는 프레임 번호로 확인하세요.</p>
            </> : <Empty title="등록된 영상이 없습니다"><p>MP4를 가져오거나 기준 이미지로 영상을 생성하세요.</p></Empty>}
          </>}
          {selectedClip ? <section className="video-result" aria-label="등록된 동작 결과">
            <h3>편집에 사용하는 동작 결과</h3>
            <Select label="편집할 동작" value={selectedClip.clipId} onChange={e => {setClipId(e.target.value); setOccurrenceId(''); setBeforeFinishClipId('');}}>
              {clips.map(c => <option key={c.clipId} value={c.clipId}>{c.name} · {c.occurrences.length}프레임</option>)}
            </Select>
            {mode === 'generate' && resultVideo ? <details className="video-result-source"><summary>이 동작의 원본 영상과 비교</summary>
              <video key={resultVideo.videoId} className="video-original" src={resultVideo.url} controls playsInline preload="metadata" aria-label={`결과의 원본 영상 · ${resultVideo.originalFilename}`}/>
              <p className="caption">{videoProvenanceLabel(resultVideo)} · {resultVideo.originalFilename}</p>
            </details> : null}
            <p className="video-color-info">{colorLabel}</p>
            {beforeFinish ? <div className="source-tool-segments video-comparison" role="group" aria-label="색상 마무리 전후 비교">
              <button type="button" aria-pressed={!comparing} onClick={() => setBeforeFinishClipId('')}>마무리 후 · 편집 결과</button>
              <button type="button" aria-pressed={comparing} onClick={() => setBeforeFinishClipId(selectedClip.clipId)}>마무리 전 · 비교용</button>
            </div> : null}
            <div className="video-result-player" aria-label={comparing ? '색상 마무리 전 비교 재생' : '실제 PNG 후보 재생'}>
              <EditorCanvas key={selectedClip.clipId} snapshot={comparing ? beforeFinish! : p} clip={selectedClip} selected={occurrenceId} onSelect={setOccurrenceId}/>
            </div>
            <p className="caption">{comparing ? '마무리 전 PNG에 같은 정렬·편집값을 적용한 비교 화면입니다. 저장된 후보는 바뀌지 않습니다.' : '현재 PNG 후보를 편집 캔버스로 재생합니다. 저장된 색상과 현재 정렬·픽셀 편집·재생 시간이 반영됩니다.'}</p>
            <p className="caption">{selectedClip.occurrences.reduce((sum, o) => sum + o.durationMs, 0)}ms · 원본의 표시 시간 유지 · 후보·앵커·반복 검수 필요</p>
            <Select label="결과 동작의 재생 종료" value={selectedClip.loop ? 'loop' : 'once'} disabled={s.busy || !!s.conflict || active} onChange={e => s.edit({type: 'updateClip', clipId: selectedClip.clipId, changes: {loop: e.target.value === 'loop', endBehavior: 'hold-last'}})}>
              <option value="loop">끝에서 처음으로 반복</option><option value="once">한 번 재생 · 마지막 프레임 유지</option>
            </Select>
            <p className="caption">종료 방식 변경은 편집 초안에 적용됩니다. 저장하면 출력에도 반영됩니다.</p>
            {onSelectClip ? <button type="button" onClick={() => onSelectClip(selectedClip.clipId)}>이 동작 편집하기</button> : <p className="caption">편집기의 동작 목록에서 “{selectedClip.name}”을 선택하세요.</p>}
          </section> : null}
          <section className="video-jobs" aria-label="영상 작업 진행">
            {videoJobs.slice(0, allJobs ? undefined : 4).map(job => <div key={job.jobId}>
              {job.batchId && job.batchIndex !== undefined && job.batchSize ? <p className="caption">묶음 작업 · {job.batchIndex + 1} / {job.batchSize}</p> : null}
              <JobCard job={job} s={s} onSelectClip={onSelectClip}/>
              {job.result?.videoId && videos.some(v => v.videoId === job.result?.videoId) ? <button type="button" onClick={() => {chooseVideo(job.result!.videoId!); changeMode('process');}}>이 영상 확인·재처리</button> : null}
            </div>)}
            {videoJobs.length > 4 ? <button type="button" onClick={() => setAllJobs(previous => !previous)}>{allJobs ? '최근 영상 작업만 보기' : `영상 작업 모두 보기 (${videoJobs.length}건)`}</button> : null}
          </section>
        </div>
      </section>
      <div id={`${id}-settings`} className="source-tool-settings">
        <form className="source-tool-pane" aria-label={mode === 'generate' ? '영상 생성 설정' : '기존 영상 처리 설정'} onSubmit={submit}>
          <h2 className="source-tool-heading">{mode === 'generate' ? '생성 설정 · 1회 요청' : '후보 추출 · 추가 생성 없음'}</h2>
          <div className="source-tool-scroll">
            {mode === 'generate' ? <>
              <Select label="기준 이미지" value={generation.assetId} required onChange={e => setGenerationField('assetId', e.target.value)}>
                <option value="">이미지 선택</option>
                {p.assets.map(a => <option key={a.assetId} value={a.assetId}>{a.originalFilename}{approvedVideoReference(p, a.assetId) ? ' · 승인 기준' : ''}</option>)}
              </Select>
              <Select label="영상 모델" value={generation.model} onChange={e => setGenerationField('model', e.target.value)}>
                {VIDEO_MODELS.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
              </Select>
              {generation.model === 'grok-imagine-video-1.5-lite' ? <p className="warning">Lite는 걷기가 빨라지거나 머리 흔들림이 커질 수 있습니다. 480p로 먼저 확인하고 원본·프레임 결과를 비교하세요.</p> : null}
              <div className="source-tool-numbers">
                <Select label="길이" value={generation.durationSeconds} onChange={e => setGenerationField('durationSeconds', e.target.value)}>{[2, 3, 4, 5, 6].map(n => <option key={n} value={n}>{n}초</option>)}</Select>
                <Select label="해상도" value={generation.resolution} onChange={e => setGenerationField('resolution', e.target.value)}><option value="480p">480p</option><option value="720p">720p</option></Select>
              </div>
              <div className="source-tool-numbers">
                <Select label="보기 방향" value={generation.direction} onChange={e => setGenerationField('direction', e.target.value)}>{VIDEO_DIRECTIONS.map(direction => <option key={direction.id} value={direction.id}>{direction.label}</option>)}</Select>
                <Select label="캐릭터 방향" value={generation.facing} onChange={e => setGenerationField('facing', e.target.value)}><option value="right">오른쪽</option><option value="left">왼쪽</option></Select>
              </div>
            </> : null}
            <Select label="동작 상태" value={processing.state} onChange={e => setProcessingField('state', e.target.value)}>{VIDEO_STATES.map(state => <option key={state.id} value={state.id}>{state.label}</option>)}</Select>
            {mode === 'generate' ? <>
              <Field label="추가 동작 지시 · 선택"><textarea maxLength={2000} value={generation.motionPrompt} onChange={e => setGenerationField('motionPrompt', e.target.value)} placeholder="예: 제자리에서 걷기. 검과 의상 유지."/></Field>
              {!available ? <p className="warning">{provider?.reason || provider?.disabledReason || 'Grok 영상 연결을 확인해 주세요. 기존 영상 처리는 계속 사용할 수 있습니다.'}</p> : null}
              <button type="button" disabled={s.busy} onClick={s.connect}>Grok 연결 다시 확인</button>
            </> : null}
            <h3>프레임 추출 설정</h3>
            <Select label="색상 마무리" value={processing.finishMode} onChange={e => setProcessingField('finishMode', e.target.value as VideoProcessingSettings['finishMode'])}>
              <option value="gif">검수 GIF와 같은 색상</option><option value="rgba">반투명 원본 유지</option>
            </Select>
            <p className="caption">{processing.finishMode === 'gif' ? '프레임마다 최대 255색으로 줄이고 반투명 경계를 정리해 실제 PNG 후보에 저장합니다. 편집과 출력에 같은 색상이 적용됩니다.' : '축소한 RGBA의 색상과 반투명을 그대로 저장합니다. 작은 색 점과 경계의 색 번짐이 남을 수 있습니다.'} 기존 동작은 새로 추출하기 전까지 바뀌지 않습니다.</p>
            <Select label="동작 흔들림 보정" value={processing.repairMode} onChange={e => setProcessingField('repairMode', e.target.value as VideoProcessingSettings['repairMode'])}>
              <option value="off">끄기 · 촬영된 프레임 유지</option>
              <option value="auto">자동 · 필요한 경우 RIFE 보간</option>
              <option value="on" disabled={!rifeAvailable}>필수 · 보간할 수 없으면 중단</option>
            </Select>
            <p className="caption">걷기·달리기 반복 구간의 급격한 움직임만 보정합니다. 자동 모드는 RIFE를 사용할 수 없으면 원본 프레임을 유지하고 사유를 기록합니다. 보간 프레임은 출처에 표시됩니다.</p>
            {!rifeAvailable ? <p className="warning">RIFE 필수 보정을 사용할 수 없습니다. {rifeReason}</p> : <p className="caption">로컬 RIFE 준비됨 · 보정에 새 영상 생성은 필요하지 않습니다.</p>}
            <Select label="추출 구간" value={processing.loopMode} onChange={e => setProcessing(previous => ({...previous, loopMode: e.target.value, matchClipId: e.target.value === 'full' ? '' : previous.matchClipId}))}>
              <option value="auto">자동 · 반복 구간 찾기</option><option value="full">전체 영상</option>
              {mode === 'process' ? <option value="manual">수동 · 프레임 범위</option> : null}
            </Select>
            {processing.loopMode === 'manual' && mode === 'process' ? <>
              <div className="source-tool-numbers">
                {numericField('startFrame', '시작 프레임 · 포함', 0, Math.max(0, (video?.frameCount ?? 1) - 1))}
                <Input label="끝 프레임 · 미포함" type="number" required min={1} max={video?.frameCount ?? 1} step={1} value={processing.endFrame || video?.frameCount || ''} onChange={e => setProcessingField('endFrame', e.target.value)}/>
              </div>
              <p className="caption">프레임은 0부터 셉니다. [0, {video?.frameCount ?? 0})은 전체 영상입니다.</p>
            </> : null}
            <Select label="주기를 맞출 동작" value={processing.matchClipId} disabled={processing.loopMode === 'full'} onChange={e => setProcessingField('matchClipId', e.target.value)}>
              <option value="">맞추지 않음 · 원래 주기 유지</option>
              {missingMatchClip ? <option value={processing.matchClipId} disabled>맞출 동작 없음 · 다시 선택</option> : null}
              {matchClips.map(clip => <option key={clip.clipId} value={clip.clipId} disabled={!rifeAvailable}>{clip.name} · {clip.occurrences.length}프레임 · {clip.occurrences.reduce((sum, occurrence) => sum + occurrence.durationMs, 0)}ms</option>)}
            </Select>
            <p className="caption">선택한 동작과 프레임 수·재생 시간을 맞춥니다. 중간 프레임은 로컬 보간할 수 있습니다. 추가 영상 생성은 없습니다.</p>
            {processing.loopMode === 'full' ? <p className="caption">전체 영상에서는 주기 맞춤을 사용하지 않습니다.</p> : null}
            <Select label="제거할 배경색" value={processing.key} onChange={e => setProcessingField('key', e.target.value)}><option value="auto">자동 감지</option><option value="green">녹색</option><option value="magenta">마젠타</option><option value="cyan">시안</option><option value="white">흰색</option></Select>
            {mode === 'process' ? <>
              <Select label="색 번짐 판정 기준" value={spillReferenceAssetId} onChange={e => {setSpillReference({videoId: video?.videoId ?? '', assetId: e.target.value}); setError('');}}>
                <option value="">{hasVideoReference ? '영상 생성 기준 사용' : '기준 없음 · 약한 보정'}</option>
                {missingSpillReference ? <option value={spillReferenceAssetId} disabled>기준 이미지 없음 · 다시 선택</option> : null}
                {p.assets.map(a => <option key={a.assetId} value={a.assetId}>{a.originalFilename}</option>)}
              </Select>
              {missingSpillReference ? <p className="warning">선택한 기준 이미지가 없습니다. 영상 제작에 쓴 원본 그림을 다시 선택해 주세요.</p>
                : !spillReferenceAssetId && !hasVideoReference ? <p className="caption">기준이 없으면 칼·손 안쪽에 배경색이 남을 수 있습니다. 영상 제작에 쓴 원본 그림을 선택해 주세요.</p> : null}
            </> : null}
            <div className="source-tool-numbers">
              {numericField('maxFrames', '최대 후보 수', 4, 64)}
              {numericField('bodyHeight', '공통 몸 높이 (px)', 16, 512)}
              {numericField('cellWidth', '셀 너비 (px)', 32, 1024)}
              {numericField('cellHeight', '셀 높이 (px)', 32, 1024)}
            </div>
            <p className="caption">선택 구간에서 순서대로 추출하며 표시 시간을 유지합니다. 새 후보와 동작은 검수 대기로 추가됩니다.</p>
            {mode === 'process' ? <p className="caption">보관된 원본을 다시 사용합니다. 모델 호출 없이 구간·배경·크기를 조정할 수 있습니다.</p> : null}
            <VideoBatchPlan key={p.projectId} s={s} generation={generation} processing={processing} available={available} active={active} visible={mode === 'generate'} onSubmitted={() => {setPane('preview'); setAllJobs(true);}}/>
          </div>
          <div className="source-tool-footer">
            {mode === 'generate' ? <div className="video-request-summary" aria-live="polite">
              <strong>Grok {VIDEO_MODELS.find(m => m.id === generation.model)?.label} · {generation.durationSeconds}초 · {generation.resolution} · 생성 1회</strong>
              <p>Grok 로그인 사용량을 사용합니다. 정확한 비용·잔여량은 여기서 확인할 수 없습니다.</p>
              <p>후처리 실패 시 자동 재생성하지 않습니다.</p>
            </div> : <strong>기존 영상 처리 · 생성 요청 0회</strong>}
            {s.commands.length ? <p className="warning">편집 초안을 먼저 저장해 주세요.</p> : null}
            {s.conflict ? <p className="warning">다른 저장 버전과 충돌을 해결해 주세요.</p> : null}
            {active ? <p className="caption">영상 작업을 처리하고 있습니다. 원본·작업 결과에서 확인하세요.</p> : null}
            {s.service?.worker !== 'ready' ? <p className="warning">처리 엔진 연결을 확인해 주세요.</p> : null}
            <button className="primary full" type="submit" disabled={disabled || (mode === 'generate' ? !asset || !available : !video)}>{mode === 'generate' ? '영상 1회 생성하고 후보 추출' : '이 영상에서 새 후보 추출'}</button>
          </div>
        </form>
      </div>
    </div>
  </div>;
}
