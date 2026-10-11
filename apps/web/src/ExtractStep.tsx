import {useState,useEffect} from 'react';
import type {Studio} from './useStudio';
import type {Rect} from './types';
import {assetLabel} from './assetProvenance';
import {Select,Num,Check,Empty} from './ui';
import {SourceTool,SourcePane} from './SourceToolLayout';

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
    <Select label="처리할 이미지" value={assetId} onChange={e => { setAsset(e.target.value); setRegions([]); setRegionHistory([]); setSelected([]); }}><option value="">이미지 선택</option>{p.assets.map(a => <option key={a.assetId} value={a.assetId}>{assetLabel(a)} · {a.width}×{a.height}</option>)}</Select>
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
