import {useState,useEffect} from 'react';
import type {Studio} from './useStudio';
import {referenceLabel} from './referenceLabel';
import {Field,Input,Select,Num,Check,Empty,short} from './ui';
import {VideoStep} from './VideoStep';
import {VideoBasePreset} from './VideoBasePreset';
import {buildVideoBasePrompt,DEFAULT_VIDEO_BASE_SETTINGS,type VideoBaseSettings} from './videoBasePrompt';
import {imageProviders} from './videoWorkflow';
import {stripViewInstructions} from './viewDirection';
import {SourceTool,SourcePane} from './SourceToolLayout';

export function GenerationStep({ s, onSelectClip }: { s: Studio; onSelectClip?: (clipId: string) => void }) {
    const [mode, setMode] = useState<'image' | 'video'>('image');
    return <div className="generation-tool">
      <div className="generation-mode" role="group" aria-label="동작 생성 방식">
        <button type="button" aria-pressed={mode === 'image'} onClick={() => setMode('image')}>이미지로 만들기</button>
        <button type="button" aria-pressed={mode === 'video'} onClick={() => setMode('video')}>영상으로 만들기</button>
      </div>
      {mode === 'video' ? <VideoStep key={s.snapshot!.projectId} s={s} onSelectClip={onSelectClip}/> : <ImageGenerationStep key={s.snapshot!.projectId} s={s}/>}
    </div>;
}
export function ImageGenerationStep({ s, assetMode = false, onBack }: {
    s: Studio;
    assetMode?: boolean;
    onBack?: () => void;
}) {
    const p = s.snapshot!;
    const settings: Record<string, unknown> = assetMode ? {} : p.generationSettings;
    const providers = imageProviders(s.providers).filter(provider => !assetMode || provider.providerId === 'codex');
    const [providerId, setProvider] = useState(String(providers.find(item => item.providerId === settings.providerId)?.providerId || providers[0]?.providerId || ''));
    const [model, setModel] = useState(String(settings.model || ''));
    const [prompt, setPrompt] = useState(String(settings.prompt || ''));
    const [frameCount, setCount] = useState(assetMode ? 1 : Number(settings.frameCount || 4));
    const [resolution, setResolution] = useState(String(settings.resolution || '1024x1024'));
    const [quality, setQuality] = useState(String(settings.quality || 'medium'));
    const [background, setBackground] = useState(String(settings.background || (assetMode ? 'transparent' : 'green')));
    const [layoutGuide, setLayoutGuide] = useState(settings.layoutGuide === true);
    const [scope, setScope] = useState(settings.scope === 'sheet' || settings.scope === 'frame' ? settings.scope : 'states');
    const [frameVersionId, setFrame] = useState(typeof settings.frameVersionId === 'string' ? settings.frameVersionId : '');
    const [imageUse, setImageUse] = useState(settings.imageUse === 'grok-video' ? 'grok-video' : 'frames');
    const [videoBase, setVideoBase] = useState<VideoBaseSettings>(() => {
        const saved = settings.videoBase && typeof settings.videoBase === 'object' ? settings.videoBase as Record<string, unknown> : {};
        return {
            direction: typeof saved.direction === 'string' && ['front', 'back', 'side', 'front_diagonal', 'back_diagonal'].includes(saved.direction) ? saved.direction : DEFAULT_VIDEO_BASE_SETTINGS.direction,
            facing: saved.facing === 'left' || saved.facing === 'right' ? saved.facing : DEFAULT_VIDEO_BASE_SETTINGS.facing,
            pose: saved.pose === 'walk' || saved.pose === 'idle' ? saved.pose : DEFAULT_VIDEO_BASE_SETTINGS.pose,
            bodyPlan: typeof saved.bodyPlan === 'string' ? saved.bodyPlan : DEFAULT_VIDEO_BASE_SETTINGS.bodyPlan,
            equipment: typeof saved.equipment === 'string' ? saved.equipment : DEFAULT_VIDEO_BASE_SETTINGS.equipment,
        };
    });
    const grokVideo = imageUse === 'grok-video';
    const requestScope = assetMode ? 'asset' : grokVideo ? 'states' : scope;
    const provider = providers.find(p => p.providerId === providerId);
    const models = provider?.models || [];
    const approved = p.references.some(r => r.referenceRevisionId === p.activeReferenceRevisionId && r.approval === 'approved');
    const available = provider?.available !== false && provider?.loginReady !== false && !!provider;
    const singleFrame = assetMode || grokVideo || scope === 'frame' || frameCount === 1;
    useEffect(() => {
        if (!model && models.length) {
            setModel(typeof models[0] === 'string' ? models[0] : models[0].id);
        }
    }, [providerId, models.length]);
    const params = {
        providerId,
        model: model || provider?.defaultModel || provider?.model || '',
        prompt: grokVideo ? [stripViewInstructions(prompt), buildVideoBasePrompt(videoBase)].filter(Boolean).join('\n\n') : prompt,
        ...(grokVideo ? {viewDirection: videoBase.direction, viewFacing: videoBase.facing, bodyPlan: videoBase.bodyPlan, equipment: videoBase.equipment} : {}),
        background,
        frameCount: grokVideo || scope === 'frame' ? 1 : frameCount,
        layoutGuide: !!provider?.capabilities?.layoutGuide && singleFrame && layoutGuide,
        ...(!assetMode && provider?.capabilities?.resolution ? {resolution} : {}),
        ...(!assetMode && provider?.capabilities?.quality ? {quality} : {}),
        scope: requestScope,
        ...(requestScope === 'frame' ? {frameVersionId} : {}),
    };
    const activeReference = p.references.find(r => r.referenceRevisionId === p.activeReferenceRevisionId && r.approval === 'approved');
    const identityAsset = p.assets.find(a => a.assetId === activeReference?.identityAssetId);
    const {viewDirection: _direction, viewFacing: _facing, bodyPlan: _body, equipment: _equipment, ...savedParams} = params;
    return (<SourceTool name={assetMode ? '자료 이미지 생성' : '동작 생성'} previewLabel={assetMode ? '생성 안내' : '승인 기준'} toolbar={assetMode && onBack ? <div className="source-tool-filebar"><button type="button" onClick={onBack}>자료 가져오기로 돌아가기</button></div> : undefined} preview={assetMode ? <SourcePane title="새 자료 이미지">
      <Empty title="설명으로 새 이미지를 만듭니다"><p>기준 그림 없이 GPT ImageGen으로 한 장 생성합니다. 결과 원본은 라이브러리의 자료에 보관됩니다.</p><p>그림을 확인한 뒤 외형 기준으로 선택하고 승인할 수 있습니다.</p></Empty>
    </SourcePane> : <SourcePane title={referenceLabel(p,activeReference?.referenceRevisionId)} className="source-tool-identity-pane">
    <div className="source-tool-canvas checker">{identityAsset ? <img src={identityAsset.url} alt="승인된 외형 기준"/> : <Empty title="승인한 외형 기준이 없습니다"><p>기준 도구에서 외형을 승인해 주세요.</p></Empty>}</div>
    <section className="source-tool-traits" tabIndex={0} aria-label="승인된 고정 특징">
      <h3>{grokVideo ? '이번 생성에 유지할 특징' : '고정 특징'}</h3><p>{activeReference?.fixedTraits ? (grokVideo ? stripViewInstructions(activeReference.fixedTraits) : activeReference.fixedTraits) : '등록한 외형 이미지 기준'}</p>
      {activeReference?.allowedChanges && <><h3>변경 가능</h3><p>{grokVideo ? stripViewInstructions(activeReference.allowedChanges) : activeReference.allowedChanges}</p></>}
      {activeReference?.forbiddenTransfers && <><h3>가져오면 안 되는 특징</h3><p>{activeReference.forbiddenTransfers}</p></>}
    </section>
  </SourcePane>} settings={<SourcePane title={assetMode ? '자료 이미지 생성 설정' : '동작과 생성 설정'} footer={<>
    {!assetMode && !approved && <p className="warning">외형 기준을 먼저 승인해 주세요.</p>}
    {!!s.commands.length && <p className="warning">{assetMode ? '현재 편집 초안을 저장한 뒤 생성해 주세요.' : '설정을 저장한 뒤 생성해 주세요.'}</p>}
    {!assetMode && <button className="full" onClick={() => s.edit({ type: 'setGenerationSettings', settings: { ...savedParams, prompt, frameCount, scope, frameVersionId, layoutGuide, imageUse, videoBase } })}>설정을 초안에 적용</button>}
    <button className="primary full" disabled={(!assetMode && !approved) || !available || !prompt.trim() || s.busy || !!s.commands.length || s.service?.worker !== 'ready' || requestScope === 'frame' && !frameVersionId} onClick={() => s.job('generate', [], params)}>{assetMode ? '자료 이미지 1장 생성' : '새 후보 생성'}</button>
  </>}>
    {!assetMode && <>
    <Select label="Grok 영상 사용" value={imageUse} onChange={e => setImageUse(e.target.value)}>
      <option value="frames">사용 안 함 · 이미지 프레임 생성</option>
      <option value="grok-video">사용함 · 영상용 기준 그림 1장</option>
    </Select>
    </>}
    <Field label={assetMode ? '만들 이미지 설명' : '동작과 포즈 설명'}><textarea className="source-tool-prompt" value={prompt} maxLength={assetMode ? 20000 : undefined} onChange={e => setPrompt(e.target.value)} placeholder={assetMode ? '예: SD 3등신 여성 힐러. 효과 없는 황금색 스태프를 든 정면 모습, 선명한 2D 픽셀 아트.' : '제자리에서 걷는 캐릭터. 승인 기준의 의상과 장비를 유지해 주세요.'}/></Field>
    {!assetMode && (grokVideo ? <>
      <p className="caption">선택한 이미지 제공자로 영상용 기준 그림 1장을 새 동작 후보로 생성합니다. Grok 영상은 자동 생성하지 않습니다.</p>
      <VideoBasePreset value={videoBase} onChange={setVideoBase}/>
      <details className="source-tool-details">
        <summary>방향이 반영된 생성 설명 보기</summary>
        <p className="caption">원래 설명과 승인 기준은 보존합니다. 이번 요청에서는 기존 보기 방향 표현을 정리하고 아래 방향을 적용합니다.</p>
        <Field label="방향이 반영된 생성 설명"><textarea className="source-tool-prompt" readOnly value={params.prompt}/></Field>
      </details>
    </> : <>
    <Select label="생성 범위" value={scope} onChange={e => setScope(e.target.value)}><option value="states">새 동작 후보</option><option value="sheet">스프라이트 시트</option><option value="frame">한 프레임 재생성</option></Select>
    {scope === 'frame' ? <Select label="재생성할 프레임" value={frameVersionId} onChange={e => setFrame(e.target.value)}><option value="">후보 선택</option>{p.frames.map((f, i) => <option key={f.frameVersionId} value={f.frameVersionId}>후보 {i + 1} · {short(f.frameVersionId)}</option>)}</Select> : <Num label="요청 프레임 수" value={frameCount} onChange={setCount} min={1} max={provider?.capabilities?.frameCount?.max || 24}/>}
    </>)}
    {!assetMode && provider?.capabilities?.layoutGuide && <>
      <fieldset disabled={!singleFrame} style={{border: 0, padding: 0, margin: 0}}>
        <Check label="구도 가이드 사용" checked={singleFrame && layoutGuide} onChange={setLayoutGuide}/>
      </fieldset>
      <p className="caption">{singleFrame ? '머리 높이·발 위치·여백을 안내하는 보조 이미지를 함께 보냅니다. 로컬에서 만든 가이드이며 추가 생성 비용은 없습니다.' : '구도 가이드는 요청 프레임 수가 1장일 때 사용할 수 있습니다.'}</p>
    </>}
    <Select label="생성 배경" value={background} onChange={e => setBackground(e.target.value)}><option value="green">녹색 · 배경 제거용</option><option value="white">흰색</option><option value="magenta">마젠타</option><option value="transparent" disabled={!provider?.capabilities?.nativeAlphaRequest}>투명 배경 요청</option></Select>
    <p className="caption">{background === 'transparent' ? '투명 배경 요청 후에도 응답 알파를 검수합니다. 투명도를 보장하지 않습니다.' : '단색 배경은 배경 정리 도구에서 제거할 수 있습니다.'}</p>
    <details className="source-tool-details" open={!available}>
      <summary>생성 연결 · {available ? (provider?.label || provider?.name || providerId) : '연결 확인 필요'}</summary>
      <Select label="제공자" value={providerId} onChange={e => { setProvider(e.target.value); setModel(''); }}><option value="">연결 선택</option>{providers.map(item => <option key={item.providerId} value={item.providerId}>{item.label || item.name || item.providerId}</option>)}</Select>
      {models.length ? <Select label="모델" value={model} onChange={e => setModel(e.target.value)}>{models.map(m => <option key={typeof m === 'string' ? m : m.id} value={typeof m === 'string' ? m : m.id}>{typeof m === 'string' ? m : m.name || m.id}</option>)}</Select> : <Input label="모델" value={model} onChange={e => setModel(e.target.value)}/>}
      <Select label="해상도" disabled={!provider?.capabilities?.resolution} value={resolution} onChange={e => setResolution(e.target.value)}>{(provider?.capabilities?.resolutions || ['1024x1024', '1536x1024', '1024x1536']).map((r: string) => <option key={r}>{r}</option>)}</Select>
      <Select label="품질" disabled={!provider?.capabilities?.quality} value={quality} onChange={e => setQuality(e.target.value)}>{(provider?.capabilities?.qualities || ['low', 'medium', 'high']).map((q: string) => <option key={q} value={q}>{({ low: '낮음', medium: '표준', high: '높음' } as Record<string, string>)[q] || q}</option>)}</Select>
      <p className="caption">{!provider?.capabilities?.quality && '이 연결은 품질 지정을 지원하지 않습니다. '}{!provider?.capabilities?.resolution && '해상도는 제공자가 결정합니다. '}{!provider?.capabilities?.nativeAlphaRequest && 'native alpha 요청은 지원하지 않습니다.'}</p>
      <p className="caption">{provider?.reason || provider?.disabledReason || (!available ? '설치·로그인 상태를 확인하세요. PNG 가져오기는 계속 사용할 수 있습니다.' : '연결 준비와 실제 생성 성공은 별개입니다.')}</p>
      <dl className="facts"><dt>최근 실제 생성</dt><dd>{provider?.lastSuccess ? '성공 이력 있음' : '확인된 이력 없음'}</dd><dt>남은 사용량</dt><dd>확인 불가</dd><dt>결제 경로</dt><dd>{provider?.billingRoute || '제공자 설정 기준'}</dd></dl>
      <button onClick={s.connect}>연결 다시 확인</button>
    </details>
    <details className="source-tool-details"><summary>생성 결과와 취소 안내</summary><p className="caption">결과는 새 후보로 보존하며 기존 순서를 자동 교체하지 않습니다. 외부 요청의 즉시 취소·결과 재조회는 지원하지 않습니다. 취소가 외부 과금 중단을 보장하지 않으며 접수 불명 시 자동 재전송하거나 다른 유료 제공자로 전환하지 않습니다.</p></details>
  </SourcePane>}/>);
}
