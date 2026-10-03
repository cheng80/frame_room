import { useState, useEffect, useId, type ReactNode } from 'react';
import type { Studio } from './useStudio';
import { assetProvenanceLabel } from './assetProvenance';
import { Field, Input, Select, Num, Check, Empty, short } from './ui';
import type { Rect } from './types';
import './source-tools.css';
/** The dialog owns its header; this grid fills only its remaining tool-content. */
function SourceTool({ name, previewLabel = '미리보기', preview, settings, toolbar }: {
    name: string;
    previewLabel?: string;
    preview: ReactNode;
    settings: ReactNode;
    toolbar?: ReactNode;
}) {
    const [pane, setPane] = useState<'preview' | 'settings'>('preview');
    const id = useId();
    return (<div className="source-tool" data-mobile-pane={pane} aria-label={name}>
      {toolbar && <div className="source-tool-toolbar">{toolbar}</div>}
      <div className="source-tool-switch" role="group" aria-label={`${name} 보기 전환`}>
        <button type="button" aria-pressed={pane === 'preview'} aria-controls={`${id}-preview`} onClick={() => setPane('preview')}>{previewLabel}</button>
        <button type="button" aria-pressed={pane === 'settings'} aria-controls={`${id}-settings`} onClick={() => setPane('settings')}>설정</button>
      </div>
      <div className="source-tool-columns">
        <div id={`${id}-preview`} className="source-tool-preview">{preview}</div>
        <div id={`${id}-settings`} className="source-tool-settings">{settings}</div>
      </div>
    </div>);
}
function SourcePane({ title, children, footer, className = '' }: {
    title: string;
    children: ReactNode;
    footer?: ReactNode;
    className?: string;
}) {
    const id = useId();
    return (<section className={`source-tool-pane ${className}`} aria-labelledby={id}>
      <h2 className="source-tool-heading" id={id}>{title}</h2>
      <div className="source-tool-scroll" tabIndex={0} role="region" aria-label={`${title} 내용`}>{children}</div>
      {footer && <div className="source-tool-footer">{footer}</div>}
    </section>);
}
export function AssetsStep({ s, onNext }: {
    s: Studio;
    onNext: () => void;
}) {
    const p = s.snapshot!;
    const [role, setRole] = useState('source');
    const [mode, setMode] = useState('whole');
    const [files, setFiles] = useState<File[]>([]);
    const limit = s.service?.limits?.maxUploadBytes || 32 * 1024 * 1024;
    const assetById = new Map(p.assets.map(a => [a.assetId, a]));
    async function upload() {
        if (!files.length) {
            s.setError('가져올 PNG 또는 WebP를 선택해 주세요.');
            return;
        }
        if (files.some(f => !['image/png', 'image/webp'].includes(f.type))) {
            s.setError('PNG와 WebP만 가져올 수 있습니다. 파일을 다시 선택해 주세요.');
            return;
        }
        if (files.some(f => f.size > limit)) {
            s.setError('파일 크기가 서버 업로드 한도를 초과했습니다.');
            return;
        }
        const body = new FormData();
        files.forEach(f => body.append('files', f));
        body.append('role', role);
        body.append('importMode', mode);
        const result = await s.mutation(`/projects/${p.projectId}/assets`, body);
        if (result) setFiles([]);
    }
    return (<SourceTool name="이미지 가져오기" previewLabel="등록된 자료" toolbar={<div className="source-tool-filebar" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); setFiles(Array.from(e.dataTransfer.files)); }}>
      <label className="file-button">파일 선택<input type="file" multiple accept="image/png,image/webp" onChange={e => setFiles(Array.from(e.target.files || []))}/></label>
      <span>PNG · WebP · 파일당 {Math.floor(limit / 1024 / 1024)}MB · 여기에 놓기</span>
      <span className="badge" aria-live="polite">{files.length}개 선택</span>
      <button type="button" onClick={onNext}>기준 정하기 →</button>
    </div>} preview={<SourcePane title={`등록된 자료 ${p.assets.length}개`}>
      <div className="source-tool-asset-grid">
        {p.assets.map(a => {
                const source = assetProvenanceLabel(a, assetById);
                return <article className="source-tool-asset" key={a.assetId}>
            <div className="source-tool-thumb checker"><img src={a.url} alt={a.originalFilename} loading="lazy"/></div>
            <strong>{a.originalFilename}</strong>
            <span>{a.width} × {a.height} · {source.roleLabel}</span>
            <span className="badge">{source.label}</span>
            {source.originLabel && <span className="badge">{source.originLabel}</span>}
            <small>투명 {a.alphaStats?.transparent ?? 0} / 반투명 {a.alphaStats?.partial ?? 0} / 불투명 {a.alphaStats?.opaque ?? 0}</small>
            <span className={`badge ${a.alphaStats?.transparent ? 'success' : 'warn'}`}>{a.alphaStats?.transparent ? '실제 알파 포함' : '불투명 · 배경 검수 필요'}</span>
          </article>;
            })}
      </div>
      {!p.assets.length && <Empty title="등록한 이미지가 없습니다"><p>파일을 선택해 가져오세요. 완성 PNG는 생성 없이 편집할 수 있습니다.</p></Empty>}
    </SourcePane>} settings={<SourcePane title="가져오기 설정" footer={<>
      {!!s.commands.length && <p className="warning">현재 초안을 저장한 뒤 파일을 가져와 주세요.</p>}
      <button className="primary full" disabled={s.busy || !files.length || !!s.commands.length} onClick={upload}>선택한 {files.length}개 가져오기</button>
    </>}>
      <Select label="자료 역할" value={role} onChange={e => setRole(e.target.value)}>
        <option value="source">편집할 원본</option><option value="identity">외형 기준</option><option value="style">스타일 참조</option><option value="pose">자세 참고</option>
      </Select>
      <Select label="가져오기 형태" value={mode} onChange={e => setMode(e.target.value)}>
        <option value="whole">개별 이미지</option><option value="grid">규칙 격자 시트</option><option value="regions">아틀라스 · 수동 영역</option>
      </Select>
      <h3>선택한 파일</h3>
      {files.length ? <ul className="source-tool-files">{files.map((f, i) => <li key={i}><span>{f.name}</span><small>{(f.size / 1024).toFixed(1)} KB</small></li>)}</ul> : <p className="caption">상단 파일바에서 파일을 선택하세요.</p>}
      <p className="caption">원본은 그대로 보관합니다.</p>
    </SourcePane>}/>);
}
export function ReferenceStep({ s }: {
    s: Studio;
}) {
    const p = s.snapshot!;
    const active = p.references.find(r => r.referenceRevisionId === p.activeReferenceRevisionId);
    const [identity, setIdentity] = useState(active?.identityAssetId || p.assets[0]?.assetId || '');
    const [styles, setStyles] = useState<string[]>(active?.styleAssetIds || []);
    const [poses, setPoses] = useState<string[]>(active?.poseAssetIds || []);
    const [fixed, setFixed] = useState(active?.fixedTraits || '');
    const [allowed, setAllowed] = useState(active?.allowedChanges || '');
    const [forbidden, setForbidden] = useState(active?.forbiddenTransfers || '');
    const [facing, setFacing] = useState(active?.facing || 'right');
    const [confirmed, setConfirmed] = useState(false);
    const toggle = (ids: string[], id: string) => ids.includes(id) ? ids.filter(x => x !== id) : [...ids, id];
    async function saveReference() {
        const reference = {
            identityAssetId: identity,
            styleAssetIds: styles,
            poseAssetIds: poses,
            fixedTraits: fixed,
            allowedChanges: allowed,
            forbiddenTransfers: forbidden,
            facing,
            bodyMeasurement: null,
        };
        await s.mutation(`/projects/${p.projectId}/reference-revisions`, {
            expectedRevision: p.revision,
            reference,
        });
        setConfirmed(false);
    }
    const [tab, setTab] = useState<'identity' | 'roles' | 'approval'>('identity');
    const identityAsset = p.assets.find(a => a.assetId === identity);
    return (<SourceTool name="캐릭터 기준" preview={<SourcePane title="외형 기준 이미지" className="source-tool-visual-pane" footer={<span>{identityAsset ? `${identityAsset.originalFilename} · ${identityAsset.width} × ${identityAsset.height}` : '외형 기준을 선택해 주세요'}</span>}>
    <div className="source-tool-canvas checker">{identityAsset ? <img src={identityAsset.url} alt="선택한 외형 기준"/> : <Empty title="외형 기준 이미지가 없습니다"/>}</div>
  </SourcePane>} settings={<SourcePane title="기준 편집" footer={tab !== 'approval' ? <button className="primary full" disabled={!identity || s.busy || !!s.commands.length} onClick={saveReference}>새 기준 초안 저장</button> : <p className="caption">승인한 기준은 고정됩니다. 변경은 새 초안으로 저장하세요.</p>}>
    <div className="source-tool-segments" role="group" aria-label="기준 설정 분류">
      <button aria-pressed={tab === 'identity'} onClick={() => setTab('identity')}>외형</button>
      <button aria-pressed={tab === 'roles'} onClick={() => setTab('roles')}>참조</button>
      <button aria-pressed={tab === 'approval'} onClick={() => setTab('approval')}>승인</button>
    </div>
    {tab === 'identity' && <>
      <Select label="외형 기준 이미지" value={identity} onChange={e => setIdentity(e.target.value)}>
        <option value="">이미지 선택</option>{p.assets.map(a => <option key={a.assetId} value={a.assetId}>{a.originalFilename}</option>)}
      </Select>
      <Field label="고정 특징 · 얼굴 / 의상 / 장비 / 팔레트"><textarea value={fixed} onChange={e => setFixed(e.target.value)} placeholder="예: 짧은 은색 머리, 오른팔의 청색 장갑, 붉은 목도리"/></Field>
      <Field label="변경해도 되는 특징"><textarea value={allowed} onChange={e => setAllowed(e.target.value)} placeholder="예: 자세와 표정, 무기의 각도"/></Field>
      <Field label="스타일에서 가져오면 안 되는 특징"><textarea value={forbidden} onChange={e => setForbidden(e.target.value)} placeholder="예: 다른 캐릭터의 의상이나 장비"/></Field>
      <Select label="기준 방향" value={facing} onChange={e => setFacing(e.target.value)}><option value="right">오른쪽</option><option value="left">왼쪽</option><option value="front">정면</option><option value="back">뒷면</option></Select>
    </>}
    {tab === 'roles' && <>
      <p className="caption">스타일과 자세는 보조 참조입니다. 외형 기준은 유지됩니다.</p>
      {p.assets.map(a => <article className="source-tool-reference" key={a.assetId}>
        <img className="checker" src={a.url} alt="" loading="lazy"/><strong>{a.originalFilename}</strong>
        <div><Check label="스타일" checked={styles.includes(a.assetId)} onChange={() => setStyles(toggle(styles, a.assetId))}/><Check label="자세" checked={poses.includes(a.assetId)} onChange={() => setPoses(toggle(poses, a.assetId))}/></div>
      </article>)}
      {!p.assets.length && <p className="caption">먼저 참조 이미지를 가져오세요.</p>}
    </>}
    {tab === 'approval' && <>
      {p.references.map(r => <article className="source-tool-version" key={r.referenceRevisionId}>
        <div className="row"><strong>기준 {short(r.referenceRevisionId)}</strong><span className={`badge ${r.approval === 'approved' ? 'success' : 'warn'}`}>{r.approval === 'approved' ? '승인됨' : '초안'}</span></div>
        <p>{r.fixedTraits || '등록한 외형 이미지 기준'}</p>
        {r.approval !== 'approved' && <><Check label="외형·역할·방향을 확인했습니다" checked={confirmed} onChange={setConfirmed}/><button disabled={!confirmed || s.busy || !!s.commands.length} onClick={() => s.mutation(`/reference-revisions/${r.referenceRevisionId}/approve`, { expectedRevision: p.revision, reviewChecks: { identity: true } })}>이 기준 승인</button></>}
      </article>)}
      {!p.references.length && <p className="caption">외형 탭에서 첫 기준 초안을 저장하세요.</p>}
    </>}
  </SourcePane>}/>);
}
export function GenerationStep({ s }: {
    s: Studio;
}) {
    const p = s.snapshot!;
    const settings = p.generationSettings;
    const [providerId, setProvider] = useState(String(settings.providerId || s.providers[0]?.providerId || ''));
    const [model, setModel] = useState(String(settings.model || ''));
    const [prompt, setPrompt] = useState(String(settings.prompt || ''));
    const [frameCount, setCount] = useState(Number(settings.frameCount || 4));
    const [resolution, setResolution] = useState(String(settings.resolution || '1024x1024'));
    const [quality, setQuality] = useState(String(settings.quality || 'medium'));
    const [background, setBackground] = useState(String(settings.background || 'green'));
    const [scope, setScope] = useState('states');
    const [frameVersionId, setFrame] = useState('');
    const provider = s.providers.find(p => p.providerId === providerId);
    const models = provider?.models || [];
    const approved = p.references.some(r => r.referenceRevisionId === p.activeReferenceRevisionId && r.approval === 'approved');
    const available = provider?.available !== false && provider?.loginReady !== false && !!provider;
    useEffect(() => {
        if (!model && models.length) {
            setModel(typeof models[0] === 'string' ? models[0] : models[0].id);
        }
    }, [providerId, models.length]);
    const params = {
        providerId,
        model: model || provider?.defaultModel || provider?.model || '',
        prompt,
        background,
        frameCount: scope === 'frame' ? 1 : frameCount,
        ...(provider?.capabilities?.resolution ? {resolution} : {}),
        ...(provider?.capabilities?.quality ? {quality} : {}),
        scope,
        ...(scope === 'frame' ? {frameVersionId} : {}),
    };
    const activeReference = p.references.find(r => r.referenceRevisionId === p.activeReferenceRevisionId && r.approval === 'approved');
    const identityAsset = p.assets.find(a => a.assetId === activeReference?.identityAssetId);
    return (<SourceTool name="동작 생성" previewLabel="승인 기준" preview={<SourcePane title={`승인 외형 기준 · ${short(activeReference?.referenceRevisionId)}`} className="source-tool-identity-pane">
    <div className="source-tool-canvas checker">{identityAsset ? <img src={identityAsset.url} alt="승인된 외형 기준"/> : <Empty title="승인한 외형 기준이 없습니다"><p>기준 도구에서 외형을 승인해 주세요.</p></Empty>}</div>
    <section className="source-tool-traits" tabIndex={0} aria-label="승인된 고정 특징">
      <h3>고정 특징</h3><p>{activeReference?.fixedTraits || '등록한 외형 이미지 기준'}</p>
      {activeReference?.allowedChanges && <><h3>변경 가능</h3><p>{activeReference.allowedChanges}</p></>}
      {activeReference?.forbiddenTransfers && <><h3>가져오면 안 되는 특징</h3><p>{activeReference.forbiddenTransfers}</p></>}
    </section>
  </SourcePane>} settings={<SourcePane title="동작과 생성 설정" footer={<>
    {!approved && <p className="warning">외형 기준을 먼저 승인해 주세요.</p>}
    {!!s.commands.length && <p className="warning">설정을 저장한 뒤 생성해 주세요.</p>}
    <button className="full" onClick={() => s.edit({ type: 'setGenerationSettings', settings: params })}>설정을 초안에 적용</button>
    <button className="primary full" disabled={!approved || !available || !prompt.trim() || s.busy || !!s.commands.length || s.service?.worker !== 'ready' || scope === 'frame' && !frameVersionId} onClick={() => s.job('generate', [], params)}>새 후보 생성</button>
  </>}>
    <Field label="동작과 포즈 설명"><textarea className="source-tool-prompt" value={prompt} onChange={e => setPrompt(e.target.value)} placeholder="오른쪽을 바라보며 달리는 캐릭터. 승인 기준의 의상과 장비를 유지해 주세요."/></Field>
    <Select label="생성 범위" value={scope} onChange={e => setScope(e.target.value)}><option value="states">새 동작 후보</option><option value="sheet">스프라이트 시트</option><option value="frame">한 프레임 재생성</option></Select>
    {scope === 'frame' ? <Select label="재생성할 프레임" value={frameVersionId} onChange={e => setFrame(e.target.value)}><option value="">후보 선택</option>{p.frames.map((f, i) => <option key={f.frameVersionId} value={f.frameVersionId}>후보 {i + 1} · {short(f.frameVersionId)}</option>)}</Select> : <Num label="요청 프레임 수" value={frameCount} onChange={setCount} min={1} max={provider?.capabilities?.frameCount?.max || 24}/>}
    <Select label="생성 배경" value={background} onChange={e => setBackground(e.target.value)}><option value="green">녹색 · 배경 제거용</option><option value="white">흰색</option><option value="magenta">마젠타</option><option value="transparent" disabled={!provider?.capabilities?.nativeAlphaRequest}>투명 배경 요청</option></Select>
    <p className="caption">{background === 'transparent' ? '투명 배경 요청 후에도 응답 알파를 검수합니다. 투명도를 보장하지 않습니다.' : '단색 배경은 배경 정리 도구에서 제거할 수 있습니다.'}</p>
    <details className="source-tool-details" open={!available}>
      <summary>생성 연결 · {available ? (provider?.label || provider?.name || providerId) : '연결 확인 필요'}</summary>
      <Select label="제공자" value={providerId} onChange={e => { setProvider(e.target.value); setModel(''); }}><option value="">연결 선택</option>{s.providers.map(item => <option key={item.providerId} value={item.providerId}>{item.label || item.name || item.providerId}</option>)}</Select>
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
export function ExtractStep({ s, initialAssetId }: {
    s: Studio;
    initialAssetId?: string;
}) {
    const p = s.snapshot!;
    const [assetId, setAsset] = useState(initialAssetId ?? p.assets.at(-1)?.assetId ?? '');
    const [mode, setMode] = useState('whole');
    const [rows, setRows] = useState(1);
    const [columns, setColumns] = useState(1);
    const [minArea, setArea] = useState(4);
    const [regions, setRegions] = useState<Rect[]>([]);
    const [regionHistory, setRegionHistory] = useState<Rect[][]>([]);
    const [selected, setSelected] = useState<number[]>([]);
    const [rect, setRect] = useState<Rect>({ x: 0, y: 0, width: 64, height: 64 });
    const [key, setKey] = useState('white');
    const [tolerance, setTolerance] = useState(24);
    const [groupId, setGroup] = useState('');
    useEffect(() => {
        if (initialAssetId === undefined) return;
        setAsset(initialAssetId);
        setRegions([]);
        setRegionHistory([]);
        setSelected([]);
        // Only a new parent selection replaces the tool's local selection.
    }, [initialAssetId]);
    const asset = p.assets.find(a => a.assetId === assetId);
    const disabled = s.busy || !!s.commands.length || s.service?.worker !== 'ready';
    const updateRegions = (next: Rect[]) => {
        setRegionHistory(h => [...h, regions]);
        setRegions(next);
    };

    async function importMetadata(file: File) {
        try {
            const data = JSON.parse(await file.text());
            let values: Rect[];
            if (data.schemaVersion === 1 && Array.isArray(data.frames) && data.atlas && Array.isArray(data.clips)) {
                values = data.frames.map((f: any) => f.rect);
            } else if (data.meta && data.frames && (Array.isArray(data.frames) || typeof data.frames === 'object')) {
                values = Object.values(data.frames).map((f: any) => ({
                    x: f.frame?.x, y: f.frame?.y, width: f.frame?.w, height: f.frame?.h,
                }));
            } else {
                throw new Error('지원하지 않는 메타데이터입니다. runtime.json 또는 Aseprite JSON을 선택하세요.');
            }
            const invalid = !asset || !values.length || values.some(r =>
                !r || ![r.x, r.y, r.width, r.height].every(Number.isInteger) ||
                r.x < 0 || r.y < 0 || r.width <= 0 || r.height <= 0 ||
                r.x + r.width > asset.width || r.y + r.height > asset.height,
            );
            if (invalid) throw new Error('메타데이터 영역이 선택 이미지의 경계와 일치하지 않습니다.');
            updateRegions(values);
            setSelected([]);
            s.setNotice(`${values.length}개 영역을 가져왔습니다. 순서와 영역을 확인하세요.`);
        } catch (e) {
            s.report(e);
        }
    }

    const addRegion = () => {
        if (!asset || rect.x < 0 || rect.y < 0 || rect.x + rect.width > asset.width || rect.y + rect.height > asset.height) {
            s.setError('선택 영역이 원본 이미지 경계를 벗어납니다.');
            return;
        }
        updateRegions([...regions, rect]);
    };

    const merge = () => {
        const chosen = regions.filter((_, i) => selected.includes(i));
        if (chosen.length < 2) return;
        const x = Math.min(...chosen.map(r => r.x));
        const y = Math.min(...chosen.map(r => r.y));
        updateRegions([
            ...regions.filter((_, i) => !selected.includes(i)),
            {
                x, y,
                width: Math.max(...chosen.map(r => r.x + r.width)) - x,
                height: Math.max(...chosen.map(r => r.y + r.height)) - y,
            },
        ]);
        setSelected([]);
    };
    return (<SourceTool name="프레임 추출" preview={<SourcePane title="원본과 추출 영역" className="source-tool-visual-pane" footer={<p className="caption">{asset?.alphaStats?.transparent ? '실제 투명 픽셀 포함' : '배경과 장비 경계를 확인하세요.'} · 원시 crop과 추출 좌표 보존</p>}>
    {asset ? <div className="source-tool-canvas checker"><div className="source-tool-overlay" style={{ aspectRatio: `${asset.width} / ${asset.height}` }}>
      <img src={asset.url} alt="프레임을 추출할 원본"/>
      <svg viewBox={`0 0 ${asset.width} ${asset.height}`} aria-label="추출 영역 미리보기" role="img">
        {mode === 'grid' && Array.from({ length: Math.min(rows * columns, 1024) }, (_, i) => <rect key={i} x={i % columns * asset.width / columns} y={Math.floor(i / columns) * asset.height / rows} width={asset.width / columns} height={asset.height / rows}/>)}
        {mode === 'regions' && regions.map((r, i) => <g key={i}><rect {...r} className={selected.includes(i) ? 'is-selected' : ''}/><text x={r.x + 3} y={r.y + 16}>{i + 1}</text></g>)}
      </svg>
    </div></div> : <Empty title="먼저 이미지를 가져와 주세요"/>}
  </SourcePane>} settings={<SourcePane title="추출 설정" footer={<>
    <button className="primary full" disabled={disabled || !asset || mode === 'regions' && !regions.length} onClick={() => s.job('extract', [assetId], { mode, rows, columns, regions, minArea, ...(groupId ? { groupId } : {}) })}>프레임 후보 추출</button>
    {disabled && <p className="caption">저장 완료·작업 처리기 연결 후 실행할 수 있습니다.</p>}
  </>}>
    <Select label="처리할 이미지" value={assetId} onChange={e => { setAsset(e.target.value); setRegions([]); setRegionHistory([]); setSelected([]); }}><option value="">이미지 선택</option>{p.assets.map(a => <option key={a.assetId} value={a.assetId}>{a.originalFilename} · {a.width}×{a.height}</option>)}</Select>
    <Select label="추출 방식" value={mode} onChange={e => setMode(e.target.value)}><option value="whole">전체 이미지 · 한 프레임</option><option value="grid">규칙 격자</option><option value="components">연결 성분 자동 추출</option><option value="regions">수동 영역</option></Select>
    {mode === 'grid' && <div className="source-tool-numbers"><Num label="행" value={rows} onChange={setRows} min={1} max={64}/><Num label="열" value={columns} onChange={setColumns} min={1} max={64}/></div>}
    {mode === 'components' && <><Num label="최소 연결 영역 (px²)" value={minArea} onChange={setArea} min={1}/><p className="caption">분리된 장비는 수동 영역에서 합쳐 다시 추출하세요.</p></>}
    {mode === 'regions' && <>
      <label className="file-button">아틀라스 메타데이터 가져오기<input type="file" accept=".json,application/json" disabled={!asset} onChange={e => { const file = e.target.files?.[0]; if (file)
                void importMetadata(file); e.target.value = ''; }}/></label>
      <p className="caption">Aseprite JSON / runtime.json 영역을 읽습니다. 지원하지 않는 형식은 오류로 표시합니다.</p>
      <div className="source-tool-numbers">{(['x', 'y', 'width', 'height'] as const).map(k => <Num key={k} label={{ x: '왼쪽 X', y: '위쪽 Y', width: '너비', height: '높이' }[k]} value={rect[k]} onChange={v => setRect({ ...rect, [k]: v })} min={k === 'width' || k === 'height' ? 1 : 0}/>)}</div>
      <button onClick={addRegion} disabled={!asset}>영역 추가</button>
      <div className="source-tool-regions" role="region" aria-label="수동 영역 목록" tabIndex={0}>{regions.map((r, i) => <div key={i}><Check label={`${i + 1}. (${r.x}, ${r.y}) ${r.width}×${r.height}`} checked={selected.includes(i)} onChange={v => setSelected(v ? [...selected, i] : selected.filter(n => n !== i))}/><button aria-label={`영역 ${i + 1} 제외`} onClick={() => { updateRegions(regions.filter((_, n) => n !== i)); setSelected([]); }}>제외</button></div>)}</div>
      <div className="source-tool-actions"><button disabled={selected.length < 2} onClick={merge}>선택 영역 병합</button><button disabled={!regionHistory.length} onClick={() => { setRegions(regionHistory.at(-1)!); setRegionHistory(h => h.slice(0, -1)); setSelected([]); }}>영역 편집 되돌리기</button></div>
      <p className="caption">영역 {regions.length}개 · 되돌릴 편집 {regionHistory.length}개</p>
    </>}
    <Select label="공통 배율 그룹" value={groupId} onChange={e => setGroup(e.target.value)}><option value="">새 그룹으로 만들기</option>{p.alignmentGroups.map((g, i) => <option key={g.alignmentGroupId} value={g.alignmentGroupId}>그룹 {i + 1} · {g.sharedScale}×</option>)}</Select>
    <details className="source-tool-details"><summary>배경 정리</summary>
      <p className="caption">균일한 단색 배경용입니다. 체크무늬·복잡한 배경은 픽셀 보정 또는 재생성이 필요합니다.</p>
      <Select label="제거할 배경" value={key} onChange={e => setKey(e.target.value)}><option value="white">흰색</option><option value="magenta">마젠타</option><option value="green">녹색</option><option value="auto">모서리에서 자동 추정</option></Select>
      <Num label="색 허용 오차" value={tolerance} onChange={setTolerance} min={0} max={255}/>
      <button disabled={disabled || !asset} onClick={() => s.job('cutout', [assetId], { key, tolerance })}>배경 제거 결과 만들기</button>
      <p className="caption">원본은 유지됩니다. 완료 후 이미지 목록에서 새 결과를 선택하세요.</p>
    </details>
    <p className="caption">자세별 크기를 유지합니다. 추출 시 셀에 맞춰 확대하지 않으며 공통 배율은 정렬 도구에서 정합니다.</p>
  </SourcePane>}/>);
}
