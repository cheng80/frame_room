import {useCallback,useEffect,useState} from 'react';
import {createPortal} from 'react-dom';
import type {Studio} from './useStudio';
import type {Asset,Frame,Clip} from './types';
import {assetLabel} from './assetProvenance';
import {referenceLabel} from './referenceLabel';
import {Select,short} from './ui';
import {EditorDialog} from './EditorDialog';
import {useCanvasViewport,ZoomControls,type Zoom} from './SpriteViewport';
import './candidate-comparison.css';

function ComparisonImage({asset,alt,zoom,fitFactor,fitKey,onFitZoom}:{asset:Asset;alt:string;zoom:Zoom;fitFactor:number;fitKey:string;onFitZoom:(key:string,zoom:number)=>void}) {
  const viewport=useCanvasViewport(asset.width,asset.height);
  useEffect(()=>onFitZoom(fitKey,viewport.fitZoom),[viewport.fitZoom,fitKey,onFitZoom]);
  const scale=zoom==='fit'?viewport.fitZoom*fitFactor:zoom;
  return <div className="sprite-viewport comparison-sprite-viewport">
    <div ref={viewport.stage} className="sprite-stage checker" role="region" tabIndex={0} aria-label={`${alt} 이미지 영역`}>
      <div className="sprite-frame" style={{width:asset.width*scale,height:asset.height*scale}}><img src={asset.url} alt={alt}/></div>
    </div>
  </div>;
}

export interface ComparisonNavigation {label:string;previous?:()=>void;next?:()=>void}

export function CandidateComparison({s,frame,clip,navigation}:{s:Studio;frame:Frame;clip?:Clip;navigation?:ComparisonNavigation}) {
  const project=s.snapshot!;
  const [referenceId,setReferenceId]=useState(clip?.referenceRevisionId||project.activeReferenceRevisionId||project.references.at(-1)?.referenceRevisionId||'');
  const [zoom,setZoom]=useState<Zoom>('fit');
  const [fitFactor,setFitFactor]=useState(1);
  const [fitZooms,setFitZooms]=useState<Record<string,number>>({});
  const [expanded,setExpanded]=useState(false);
  const reference=project.references.find(r=>r.referenceRevisionId===referenceId);
  const identity=project.assets.find(a=>a.assetId===reference?.identityAssetId);
  const candidate=project.assets.find(a=>a.assetId===frame.imageAssetId);
  const views=[{label:'저장된 외형 기준',asset:identity,id:reference?.referenceRevisionId},{label:'선택한 프레임 후보',asset:candidate,id:frame.frameVersionId}];
  const updateFitZoom=useCallback((key:string,value:number)=>setFitZooms(current=>current[key]===value?current:{...current,[key]:value}),[]);
  const setComparisonZoom=(value:Zoom)=>{if(value==='fit')setFitFactor(1);setZoom(value);};
  const controls=(expandedView=false)=>{
  const bucket=expandedView?'expanded':'embedded';
  const fitZoom=Math.max(0,...views.map(view=>fitZooms[`${bucket}:${view.label}`]||0));
  const zoomOptions:[Zoom,string][]=[['fit','패널에 맞춤'],[0.25,'25%'],[0.5,'50%'],[0.75,'75%'],[1,'1:1 픽셀'],[1.5,'150%'],[2,'200% 확대'],[3,'300%'],[4,'400% 확대'],[6,'600%'],[8,'800%']];
  const fitLabel=fitFactor===1?'패널에 맞춤':`맞춤 기준 ${Math.round(fitFactor*100)}%`;
  const currentZoomLabel=zoom==='fit'?fitLabel:`${Math.round(zoom*100)}%`;
  const stepZoom=(direction:-1|1)=>{
    if(zoom==='fit'){
      const minimum=fitZoom>0?Math.min(1/64,fitZoom/4)/fitZoom:0.25;
      const maximum=fitZoom>0?Math.max(64,fitZoom*4)/fitZoom:4;
      setFitFactor(current=>Math.max(minimum,Math.min(maximum,current*2**direction)));
    } else setZoom(current=>typeof current==='number'?Math.max(Math.min(1/64,(fitZoom||1)/4),Math.min(Math.max(64,fitZoom*4),current*2**direction)):current);
  };
  const controlMode=zoom==='fit'&&fitFactor!==1?fitFactor:zoom;
  const displayZoom=zoom==='fit'?fitZoom*fitFactor:zoom;
  return <div className="row comparison-controls">
    <Select label="나란히 비교할 저장 기준" value={referenceId} onChange={e=>setReferenceId(e.target.value)}>
      <option value="">기준 선택</option>
      {project.references.map(r=><option key={r.referenceRevisionId} value={r.referenceRevisionId}>{referenceLabel(project,r.referenceRevisionId)}{r.referenceRevisionId===clip?.referenceRevisionId?' · 이 동작의 기준':''}</option>)}
    </Select>
    <Select label="비교 이미지 배율" value={String(zoom)} onChange={e=>setComparisonZoom(e.target.value==='fit'?'fit':Number(e.target.value))}>{zoom!=='fit'&&!zoomOptions.some(([value])=>value===zoom)&&<option value={String(zoom)}>{currentZoomLabel}</option>}{zoomOptions.map(([value,label])=><option key={String(value)} value={String(value)}>{value==='fit'?fitLabel:label}</option>)}</Select>
    <div className="comparison-zoom-controls" role="group" aria-label="비교 이미지 배율 조절"><ZoomControls width={1} mode={controlMode} zoom={displayZoom} fitZoom={fitZoom} setZoom={setComparisonZoom} onStep={stepZoom}/><span className="comparison-zoom-label">{zoom==='fit'?fitLabel:`${Math.round(zoom*100)}%`}</span></div>
  </div>;
  };
  const comparison=(expandedView=false)=><div className="comparison-grid">{views.map(view=><figure key={view.label}>
    <figcaption><strong>{view.label}</strong><span>{view.label==='저장된 외형 기준'?referenceLabel(project,view.id):short(view.id)}</span></figcaption>
    <div className="comparison-image">{view.asset?<ComparisonImage asset={view.asset} alt={view.label} zoom={zoom} fitFactor={fitFactor} fitKey={`${expandedView?'expanded':'embedded'}:${view.label}`} onFitZoom={updateFitZoom}/>:<p>{view.label==='저장된 외형 기준'?'비교할 저장 기준을 선택해 주세요.':'후보 원본 이미지를 찾을 수 없습니다.'}</p>}</div>
    <small>{view.asset?`${assetLabel(view.asset)} · ${view.asset.width} × ${view.asset.height}`:'자료 없음'}</small>
  </figure>)}</div>;
  const dialog=<EditorDialog open={expanded} title="저장 기준과 후보 크게 비교" className="candidate-comparison-dialog" onClose={()=>setExpanded(false)}>
    <div className="comparison-expanded-content">
      {navigation&&<div className="comparison-navigation" role="group" aria-label="비교 프레임 이동"><button type="button" disabled={!navigation.previous} onClick={navigation.previous}>이전 프레임</button><span role="status">{navigation.label}</span><button type="button" disabled={!navigation.next} onClick={navigation.next}>다음 프레임</button></div>}
      {controls(true)}{comparison(true)}
    </div>
  </EditorDialog>;
  return <>
    {controls()}
    <p className="caption">외형 기준과 후보의 시각 비교입니다. 최종 셀의 원본 복원·측정 비교는 동작 보완·검사에서 실행합니다.</p>
    {clip?.comparisonEvidence && <p className="caption">복원 source {short(clip.comparisonEvidence.source?.id)} · 최초 origin {short(clip.comparisonEvidence.origin?.id)}</p>}
    <button type="button" className="comparison-expand" onClick={()=>setExpanded(true)}>두 이미지 크게 비교</button>
    {comparison()}
    {/* The inspector can be hidden at narrow widths; its modal stays outside. */}
    {typeof document==='undefined'?dialog:createPortal(dialog,document.body)}
    {reference&&<p className="caption">고정 특징: {reference.fixedTraits||'등록한 외형 이미지 기준'} · 비교 기준 선택은 동작의 사용 기준을 변경하지 않습니다.</p>}
  </>;
}
