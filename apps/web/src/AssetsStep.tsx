import {useState} from 'react';
import type {Studio} from './useStudio';
import type {Asset} from './types';
import {assetLabel,assetProvenanceLabel,isVideoProcessingAsset} from './assetProvenance';
import {AssetNameInput} from './AssetNameInput';
import {EditorDialog} from './EditorDialog';
import {Select,Empty} from './ui';
import {SourceTool,SourcePane} from './SourceToolLayout';
import {SpriteImage} from './SpriteViewport';

export function AssetsStep({ s, onNext, onGenerate }: {
    s: Studio;
    onNext: () => void;
    onGenerate: () => void;
}) {
    const p = s.snapshot!;
    const [role, setRole] = useState('source');
    const [mode, setMode] = useState('whole');
    const [files, setFiles] = useState<File[]>([]);
    const [previewAssetId,setPreviewAssetId] = useState('');
    const limit = s.service?.limits?.maxUploadBytes || 32 * 1024 * 1024;
    const assetById = new Map(p.assets.map(a => [a.assetId, a]));
    const videoById = new Map((p.videos ?? []).map(v => [v.videoId, v]));
    const previewAsset = assetById.get(previewAssetId);
    const primaryAssets = p.assets.filter(a => !isVideoProcessingAsset(a));
    const videoAssets = p.assets.filter(isVideoProcessingAsset);
    const renderAsset = (a:Asset) => {
        const source = assetProvenanceLabel(a, assetById, videoById);
        return <article className="source-tool-asset" key={a.assetId} data-asset-id={a.assetId}>
          <button type="button" className="source-tool-thumb source-tool-asset-preview checker" aria-label={`자료 이미지 크게 보기 · ${assetLabel(a)}`} onClick={()=>setPreviewAssetId(a.assetId)}><img src={a.url} alt={assetLabel(a)} loading="lazy"/><span>크게 보기</span></button>
          <strong>{assetLabel(a)}</strong>
          <AssetNameInput s={s} asset={a}/>
          <span>{a.width} × {a.height} · {source.roleLabel}</span>
          <span className="badge">{source.label}</span>
          {source.originLabel && <span className="badge">{source.originLabel}</span>}
          <small>투명 {a.alphaStats?.transparent ?? 0} / 반투명 {a.alphaStats?.partial ?? 0} / 불투명 {a.alphaStats?.opaque ?? 0}</small>
          <span className={`badge ${a.alphaStats?.transparent ? 'success' : 'warn'}`}>{a.alphaStats?.transparent ? '실제 알파 포함' : '불투명 · 배경 검수 필요'}</span>
        </article>;
    };
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
      <button type="button" onClick={onGenerate}>AI로 이미지 생성</button>
      <span>PNG · WebP · 파일당 {Math.floor(limit / 1024 / 1024)}MB · 여기에 놓기</span>
      <span className="badge" aria-live="polite">{files.length}개 선택</span>
      <button type="button" onClick={onNext}>기준 정하기 →</button>
    </div>} preview={<SourcePane title={`등록된 자료 ${p.assets.length}개`}>
      {!!p.assets.length && <p className="caption">그림을 누르면 크게 볼 수 있습니다. 자료 이름은 Enter 또는 다른 곳을 눌러 초안에 적용하고 상단 저장으로 확정합니다. 비우면 원본 파일명을 표시합니다.</p>}
      {!!p.assets.length && <h3>자료 이미지 {primaryAssets.length}개</h3>}
      <div className="source-tool-asset-grid source-tool-primary-assets">{primaryAssets.map(renderAsset)}</div>
      {!primaryAssets.length && !!videoAssets.length && <p className="caption">직접 가져오거나 생성한 자료 이미지가 없습니다. 영상 처리 결과를 펼쳐 보세요.</p>}
      {!!videoAssets.length && <details className="source-tool-details source-tool-video-results">
        <summary>영상 처리 결과 {videoAssets.length}개</summary>
        <p className="caption">영상 기준 캔버스, 원본 프레임과 배경 제거·크기·색상 처리 결과입니다.</p>
        <div className="source-tool-asset-grid">{videoAssets.map(renderAsset)}</div>
      </details>}
      {!p.assets.length && <Empty title="등록한 이미지가 없습니다"><p>파일을 선택해 가져오세요. 완성 PNG는 생성 없이 편집할 수 있습니다.</p></Empty>}
      <EditorDialog open={!!previewAsset} title="자료 이미지 크게 보기" onClose={()=>setPreviewAssetId('')} className="asset-image-dialog" actions={<button type="button" disabled={s.busy||!s.commands.length||!!s.conflict} onClick={()=>s.save()}>저장</button>}>
        {previewAsset&&<figure className="asset-image-full"><SpriteImage src={previewAsset.url} alt={assetLabel(previewAsset)} width={previewAsset.width} height={previewAsset.height} className="asset-image-viewport"/><figcaption><AssetNameInput s={s} asset={previewAsset}/><strong>{assetLabel(previewAsset)}</strong><p>원본 파일: {previewAsset.originalFilename} · {previewAsset.width} × {previewAsset.height}</p><p>{assetProvenanceLabel(previewAsset,assetById,videoById).label}</p><p>이름을 바꾼 뒤 상단 저장으로 확정합니다. 원본 파일명과 이미지는 유지됩니다.</p></figcaption></figure>}
      </EditorDialog>
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
