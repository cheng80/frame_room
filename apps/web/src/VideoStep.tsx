import {assetLabel} from './assetProvenance';
import {useEffect, useId, useMemo, useRef, useState, type FormEvent} from 'react';
import {api} from './api';
import {EditorCanvas} from './Canvas';
import {VideoBatchPlan} from './VideoBatchPlan';
import {JobCard} from './FinishSteps';
import type {Studio} from './useStudio';
import type {Snapshot, Video} from './types';
import {Empty, Field, Input, Select} from './ui';
import {
  videoReference, defaultVideoAssetId, defaultVideoProcessing, isVideoJob,
  validateVideoUpload, VIDEO_DIRECTIONS, VIDEO_MODELS, VIDEO_STATES, videoGenerationRequest,
  videoProcessingRequest, videoProvenanceLabel, type VideoGenerationSettings, type VideoProcessingSettings,
  videoBeforeFinishSnapshot, videoClipColorLabel, videoRangeBoundary, videoRangeSource, videoHasExactTimes,
  videoMatchClips, videoAssetSettings,
} from './videoWorkflow';
import {stripViewInstructions} from './viewDirection';
import {BodyPlanField} from './BodyPlanField';
import {SpriteImage,SpriteViewport} from './SpriteViewport';
import './video-tools.css';

export function VideoStep({s, onSelectClip, initialReferenceRevisionId}: {s: Studio; onSelectClip?: (clipId: string) => void; initialReferenceRevisionId?: string}) {
  const p = s.snapshot!;
  const id = useId();
  const fileInput = useRef<HTMLInputElement>(null);
  const originalPlayer = useRef<HTMLVideoElement>(null);
  const submitting = useRef(false);
  const [pane, setPane] = useState<'preview' | 'settings'>('settings');
  const [mode, setMode] = useState<'generate' | 'process'>('generate');
  const initialReference = p.references.find(r => r.referenceRevisionId === initialReferenceRevisionId);
  const initialAssetId = initialReference?.identityAssetId ?? defaultVideoAssetId(p);
  const [generation, setGeneration] = useState<VideoGenerationSettings>(() => ({
    assetId: initialAssetId, model: VIDEO_MODELS[0].id, durationSeconds: '3', resolution: '480p',
    ...videoAssetSettings(p, initialAssetId), motionPrompt: '',
  }));
  const [selectedReferenceRevisionId, setSelectedReferenceRevisionId] = useState(initialReference?.referenceRevisionId ?? videoReference(p, initialAssetId)?.referenceRevisionId ?? '');
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
  const reference = videoReference(p, generation.assetId);
  const provider = s.providers.find(item => item.providerId === 'grok-video' && item.mediaKind === 'video');
  const rife = provider?.capabilities?.rife;
  const rifeAvailable = rife?.available === true;
  const rifeReason = typeof rife?.reason === 'string' ? rife.reason : '보정 도구의 준비 상태를 확인하지 못했습니다. Grok 연결을 다시 확인해 주세요.';
  const available = !!provider && provider.available !== false && provider.loginReady !== false;
  const selectionCapability = provider?.capabilities?.frameSelection as {observer?: {model?: string | null; effort?: string | null; available?: boolean; reason?: string | null}} | undefined;
  const observer = selectionCapability?.observer;
  const frameSelection = processing.matchClipId ? 'uniform' : processing.frameSelection ?? 'uniform';
  const active = s.jobs.some(job => isVideoJob(job) && ['queued', 'running', 'cancel_requested'].includes(job.status));
  const locked = s.busy || !!s.commands.length || !!s.conflict;
  const disabled = locked || active || s.service?.worker !== 'ready';
  const videoJobs = s.jobs.filter(isVideoJob);
  const rangeVideo = video ? videoRangeSource(video, videoJobs) : undefined;
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

  useEffect(() => {
    const reference = p.references.find(r => r.referenceRevisionId === initialReferenceRevisionId);
    if (!reference) return;
    setSelectedReferenceRevisionId(reference.referenceRevisionId);
    setGeneration(previous => ({...previous, assetId: reference.identityAssetId}));
  }, [initialReferenceRevisionId]);

  function chooseGenerationAsset(assetId: string) {
    setGeneration(previous => ({...previous, assetId, ...videoAssetSettings(p, assetId)}));
    setSelectedReferenceRevisionId(videoReference(p, assetId)?.referenceRevisionId ?? '');
  }

  function changeMode(next: 'generate' | 'process') {
    setMode(next); setError('');
    if (next === 'generate') setProcessing(previous => ({...previous, loopMode: previous.loopMode === 'manual' ? 'auto' : previous.loopMode, startIndex: ''}));
  }
  function chooseVideo(value: string) {
    setVideoId(value); setClipId(''); setOccurrenceId(''); setBeforeFinishClipId(''); setError('');
    setSpillReference({videoId: value, assetId: ''});
    setProcessing(previous => ({...previous, startFrame: '0', endFrame: '', direction: '', facing: ''}));
  }
  function markRange(boundary: 'start' | 'end') {
    if (!rangeVideo || !originalPlayer.current) return;
    const frame = videoRangeBoundary(rangeVideo, originalPlayer.current.currentTime, boundary);
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
      if (processing.matchClipId && processing.between !== 'off' && !rifeAvailable) throw new Error(`주기 맞춤에 필요한 RIFE 보간을 사용할 수 없습니다. 주기 보간을 끄면 가까운 원본을 사용할 수 있습니다. ${rifeReason}`);
      const request = mode === 'generate'
        ? videoGenerationRequest(p, generation, processing)
        : videoProcessingRequest(p, video?.videoId ?? '', {...processing, spillReferenceAssetId});
      if (mode === 'generate' && selectedReferenceRevisionId && p.references.some(reference => reference.referenceRevisionId === selectedReferenceRevisionId && reference.identityAssetId === generation.assetId)) {
        (request.params as Record<string, unknown>).referenceRevisionId = selectedReferenceRevisionId;
      }
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
            {asset ? <SpriteImage src={asset.url} alt={`영상 기준 · ${assetLabel(asset)}`} width={asset.width} height={asset.height} className="video-reference checker"/> : <Empty title="기준 이미지를 선택해 주세요"/>}
            {asset ? <p className="caption">{assetLabel(asset)} · {reference ? '저장된 외형 기준 사용' : '선택한 이미지 사용'}</p> : null}
            {reference?.fixedTraits ? <p className="video-traits">{stripViewInstructions(reference.fixedTraits)}</p> : null}
          </> : <>
            <Select label="처리할 원본 영상" value={video?.videoId ?? ''} onChange={e => chooseVideo(e.target.value)}>
              {!videos.length ? <option value="">등록된 영상 없음</option> : null}
              {videos.map(v => <option key={v.videoId} value={v.videoId}>{v.originalFilename} · {(v.durationMs / 1000).toFixed(2)}초</option>)}
            </Select>
            {video ? <>
              <SpriteViewport width={video.width} height={video.height} label={`원본 영상 · ${video.originalFilename}`} className="video-original-viewport"><video ref={originalPlayer} key={video.videoId} className="video-original" src={video.url} controls playsInline preload="metadata" aria-label={`원본 영상 · ${video.originalFilename}`}/></SpriteViewport>
              <p className="caption">{videoProvenanceLabel(video)} · {video.width} × {video.height} · {video.fps.toFixed(2)}fps · {video.frameCount}프레임</p>
              <a className="button" href={video.url} download={video.originalFilename}>원본 MP4 다운로드</a>
              <div className="video-range-actions" role="group" aria-label="영상 위치로 추출 구간 지정">
                <button type="button" onClick={() => markRange('start')}>현재 위치를 시작으로</button>
                <button type="button" onClick={() => markRange('end')}>현재 위치 다음까지</button>
              </div>
              {processing.loopMode === 'manual' ? <p className="caption" role="status">선택 구간 [{processing.startFrame}, {processing.endFrame || video.frameCount}) · 설정에서 프레임 번호를 조정할 수 있습니다.</p> : null}
              <p className="caption">{rangeVideo && videoHasExactTimes(rangeVideo) ? '저장된 원본 프레임 시각으로 구간을 지정합니다.' : '영상 위치는 평균 fps로 환산한 예상값입니다. 가변 프레임 영상은 차이가 날 수 있으니 추출 범위를 확인하세요.'}</p>
            </> : <Empty title="등록된 영상이 없습니다"><p>MP4를 가져오거나 기준 이미지로 영상을 생성하세요.</p></Empty>}
          </>}
          {selectedClip ? <section className="video-result" aria-label="등록된 동작 결과">
            <h3>편집에 사용하는 동작 결과</h3>
            <Select label="편집할 동작" value={selectedClip.clipId} onChange={e => {setClipId(e.target.value); setOccurrenceId(''); setBeforeFinishClipId('');}}>
              {clips.map(c => <option key={c.clipId} value={c.clipId}>{c.name} · {c.occurrences.length}프레임</option>)}
            </Select>
            {mode === 'generate' && resultVideo ? <details className="video-result-source"><summary>이 동작의 원본 영상과 비교</summary>
              <SpriteViewport width={resultVideo.width} height={resultVideo.height} label={`결과의 원본 영상 · ${resultVideo.originalFilename}`} className="video-original-viewport"><video key={resultVideo.videoId} className="video-original" src={resultVideo.url} controls playsInline preload="metadata" aria-label={`결과의 원본 영상 · ${resultVideo.originalFilename}`}/></SpriteViewport>
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
            <p className="caption">{selectedClip.occurrences.reduce((sum, o) => sum + o.durationMs, 0)}ms · 원본의 표시 시간 유지 · 후보·앵커·반복 상태 확인</p>
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
              <Select label="기준 이미지" value={generation.assetId} required onChange={e => chooseGenerationAsset(e.target.value)}>
                <option value="">이미지 선택</option>
                {p.assets.map(a => <option key={a.assetId} value={a.assetId}>{assetLabel(a)}{videoReference(p, a.assetId) ? ' · 저장 기준' : ''}</option>)}
              </Select>
              <p className="caption">프로젝트의 active 기준 그림을 기본으로 선택합니다. 다른 이미지를 고르면 해당 이미지에 연결된 저장 기준을 사용합니다.</p>
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
                <Select label="캐릭터 방향" disabled={generation.direction === 'front' || generation.direction === 'back'} value={generation.facing} onChange={e => setGenerationField('facing', e.target.value)}><option value="right">오른쪽</option><option value="left">왼쪽</option></Select>
              </div>
              <p className="caption">선택한 그림의 생성 기록에서 방향·신체 구조·장비를 불러옵니다. 기록이 없는 그림은 방향을 확인해 주세요. 보기 방향을 바꿔도 기존 그림 자체가 회전하지는 않으므로, 그 방향의 기준 그림을 먼저 만들어 선택하세요.</p>
            </> : null}
            {mode === 'process' ? <div className="source-tool-numbers">
              <Select label="원본 보기 방향" value={processing.direction ?? ''} onChange={e => setProcessingField('direction', e.target.value)}>
                <option value="">저장된 설정 사용 · 없으면 측면</option>
                {VIDEO_DIRECTIONS.map(direction => <option key={direction.id} value={direction.id}>{direction.label}</option>)}
              </Select>
              <Select label="원본 캐릭터 방향" value={processing.facing ?? ''} onChange={e => setProcessingField('facing', e.target.value)}>
                <option value="">저장된 설정 사용 · 없으면 오른쪽</option><option value="right">오른쪽</option><option value="left">왼쪽</option>
              </Select>
            </div> : null}
            <Select label="동작 상태" value={processing.state} onChange={e => setProcessingField('state', e.target.value)}>{VIDEO_STATES.map(state => <option key={state.id} value={state.id}>{state.label}</option>)}</Select>
            {mode === 'generate' ? <>
              <details className="source-tool-details">
                <summary>신체 구조·장비 지정 · 선택</summary>
                <BodyPlanField label="신체 구조" value={generation.bodyPlan} onChange={bodyPlan => setGenerationField('bodyPlan', bodyPlan)}/>
                <Input label="장비와 손" value={generation.equipment} onChange={e => setGenerationField('equipment', e.target.value)} placeholder="예: sword:right; shield:left"/>
                <p className="caption">캐릭터 자신의 오른손은 right, 왼손은 left입니다. 장비 이름과 손을 콜론으로, 여러 장비는 세미콜론으로 구분하세요.</p>
              </details>
              <Field label="추가 동작 지시 · 선택"><textarea maxLength={2000} value={generation.motionPrompt} onChange={e => setGenerationField('motionPrompt', e.target.value)} placeholder="예: 제자리에서 걷기. 검과 의상 유지."/></Field>
              {stripViewInstructions(generation.motionPrompt) !== generation.motionPrompt.trim() ? <p className="caption">기존 보기 방향 지시를 정리한 추가 지시: {stripViewInstructions(generation.motionPrompt) || '선택한 동작 상태 사용'}</p> : null}
              {!available ? <p className="warning">{provider?.reason || provider?.disabledReason || 'Grok 영상 연결을 확인해 주세요. 기존 영상 처리는 계속 사용할 수 있습니다.'}</p> : null}
              <button type="button" disabled={s.busy} onClick={s.connect}>Grok 연결 다시 확인</button>
            </> : null}
            <h3>프레임 추출 설정</h3>
            <p className="video-frame-default"><strong>게임용 걷기 · 한 주기 기본 8장</strong><br/>왼발·오른발이 한 번씩 돌아오는 구간을 추출하고 원래 주기 시간을 유지합니다.</p>
            <div className="source-tool-segments video-frame-presets" role="group" aria-label="게임용 프레임 수">
              <button type="button" aria-pressed={processing.maxFrames === '8'} onClick={() => setProcessingField('maxFrames', '8')}>8장 · 기본</button>
              <button type="button" aria-pressed={processing.maxFrames === '12'} onClick={() => setProcessingField('maxFrames', '12')}>12장</button>
            </div>
            {numericField('maxFrames', '최대 후보 수', 4, 64)}
            <p className="caption">4~64장 직접 입력도 가능합니다. 주기 맞춤을 선택하면 대상 동작의 프레임 수와 시간을 따릅니다.</p>
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
            <Select label="영상 프레임 선별" value={frameSelection} disabled={!!processing.matchClipId} onChange={e => setProcessingField('frameSelection', e.target.value as NonNullable<VideoProcessingSettings['frameSelection']>)}>
              <option value="vision" disabled={!selectionCapability}>Luna 관찰 + 규칙 판정 · 기본</option>
              <option value="uniform">균등 간격 · 기존 방식</option>
            </Select>
            {processing.matchClipId ? <p className="caption">주기 맞춤은 균등 간격으로 추출합니다.</p> : frameSelection === 'vision' ? <>
              <p className="caption">각 출력 슬롯의 균등 위치와 이웃 후보를 {observer?.model ? `${observer.model} · ${observer.effort}` : 'Luna'}가 한 번 관찰하고 규칙으로 판정합니다(ChatGPT 구독 호출 1회, 같은 후보는 캐시 재사용). 프레임 수·순서·총 재생 시간은 유지하며 확실한 대체 후보가 없으면 균등 프레임을 둡니다. 추천은 프레임 편집에서 바꿀 수 있고 검토·숨김 기록은 바꾸지 않습니다.</p>
              {observer && observer.available !== true ? <p className="warning">이 컴퓨터의 Codex 모델 목록에서 이미지·medium을 지원하는 Luna를 찾지 못했습니다({observer.reason ?? '확인 불가'}). 관찰 호출 없이 균등 프레임을 유지하고 확인 필요로 표시합니다.</p> : null}
            </> : null}
            <Select label="추출 구간" value={processing.loopMode} onChange={e => setProcessing(previous => ({...previous, loopMode: e.target.value, ...(e.target.value === 'full' ? {matchClipId: '', startIndex: '', startFoot: 'auto'} : {})}))}>
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
              {matchClips.map(clip => <option key={clip.clipId} value={clip.clipId} disabled={!rifeAvailable && processing.between !== 'off'}>{clip.name} · {clip.occurrences.length}프레임 · {clip.occurrences.reduce((sum, occurrence) => sum + occurrence.durationMs, 0)}ms</option>)}
            </Select>
            <p className="caption">선택한 동작과 프레임 수·재생 시간을 맞춥니다. 중간 프레임은 로컬 보간할 수 있습니다. 추가 영상 생성은 없습니다.</p>
            {processing.loopMode === 'full' ? <p className="caption">전체 영상에서는 주기 맞춤을 사용하지 않습니다.</p> : null}
            <details className="source-tool-details">
              <summary>주기 보간·시작 자세</summary>
              <Select label="RIFE TTA · 추가 연산" value={processing.rifeTta ?? 'off'} onChange={e => setProcessingField('rifeTta', e.target.value as 'off' | 'on')}>
                <option value="off">끄기 · 기본</option><option value="on">공간·시간 TTA · 느릴 수 있음</option>
              </Select>
              <Select label="루프 겹침 보정" value={processing.overlapWrap ?? 'off'} onChange={e => setProcessingField('overlapWrap', e.target.value as 'off' | 'auto')}>
                <option value="off">끄기 · 기본</option><option value="auto">자동 · 확인된 두 걸음·로컬 예산 내</option>
              </Select>
              <p className="caption">로컬 보간은 작업당 60초 예산을 사용합니다. 겹침 보정은 조건이나 예산을 통과한 경우만 적용합니다.</p>
              <Select label="주기 보간" value={processing.between} onChange={e => setProcessingField('between', e.target.value as VideoProcessingSettings['between'])}>
                <option value="auto">자동 · 손상된 보간 대신 원본 사용</option>
                <option value="on">켜기 · 보간 결과 유지</option>
                <option value="off">끄기 · 가까운 원본 사용</option>
              </Select>
              <p className="caption">주기 길이를 맞출 때 필요한 중간 프레임에 적용합니다. 자동은 번짐·윤곽 손상이 감지된 보간을 원본으로 대체합니다. 동작 흔들림 보정과 별도 설정입니다.</p>
              {processing.between === 'on' ? <p className="warning">손상이 감지된 보간도 유지합니다. 처리 후 진단과 프레임을 확인하세요.</p> : null}
              <Select label="시작 발" value={processing.startFoot} disabled={processing.loopMode === 'full' || !!processing.startIndex.trim()} onChange={e => setProcessingField('startFoot', e.target.value as VideoProcessingSettings['startFoot'])}>
                <option value="auto">자동 · 기본 추출은 시작 유지</option><option value="left">캐릭터의 왼발</option><option value="right">캐릭터의 오른발</option>
              </Select>
              {mode === 'process' ? <>
                <Input label="수동 시작 위치 · 선택" type="number" min={0} max={63} step={1} value={processing.startIndex} disabled={processing.loopMode === 'full'} onChange={e => setProcessingField('startIndex', e.target.value)} placeholder="자동"/>
                <p className="caption">추출 결과의 프레임 번호를 0부터 지정합니다. 8장 결과라면 0~7입니다. 수동 위치가 시작 발보다 우선합니다.</p>
              </> : <p className="caption">수동 시작 위치는 영상 생성 후 기존 영상 처리에서 지정할 수 있습니다.</p>}
              <p className="caption">자동은 기본 추출의 시작을 유지하고, 주기 맞춤에서는 발 디딤을 판정합니다.</p>
            </details>
            <Select label="제거할 배경색" value={processing.key} onChange={e => setProcessingField('key', e.target.value)}><option value="auto">자동 감지</option><option value="green">녹색</option><option value="magenta">마젠타</option><option value="cyan">시안</option><option value="white">흰색</option></Select>
            {mode === 'process' ? <>
              <Select label="색 번짐 판정 기준" value={spillReferenceAssetId} onChange={e => {setSpillReference({videoId: video?.videoId ?? '', assetId: e.target.value}); setError('');}}>
                <option value="">{hasVideoReference ? '영상 생성 기준 사용' : '기준 없음 · 약한 보정'}</option>
                {missingSpillReference ? <option value={spillReferenceAssetId} disabled>기준 이미지 없음 · 다시 선택</option> : null}
                {p.assets.map(a => <option key={a.assetId} value={a.assetId}>{assetLabel(a)}</option>)}
              </Select>
              {missingSpillReference ? <p className="warning">선택한 기준 이미지가 없습니다. 영상 제작에 쓴 원본 그림을 다시 선택해 주세요.</p>
                : !spillReferenceAssetId && !hasVideoReference ? <p className="caption">기준이 없으면 칼·손 안쪽에 배경색이 남을 수 있습니다. 영상 제작에 쓴 원본 그림을 선택해 주세요.</p> : null}
            </> : null}
            <div className="source-tool-numbers">
              {numericField('bodyHeight', '공통 몸 높이 (px)', 16, 512)}
              {numericField('cellWidth', '셀 너비 (px)', 32, 1024)}
              {numericField('cellHeight', '셀 높이 (px)', 32, 1024)}
            </div>
            <p className="caption">선택 구간에서 순서대로 추출하며 표시 시간을 유지합니다. 새 후보와 동작을 프로젝트에 추가합니다.</p>
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
