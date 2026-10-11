import {useState} from 'react';
import {createPortal} from 'react-dom';
import type {Studio} from './useStudio';
import type {Frame,Clip} from './types';
import {assetLabel} from './assetProvenance';
import {referenceLabel} from './referenceLabel';
import {Select,short} from './ui';
import {EditorDialog} from './EditorDialog';
import './candidate-comparison.css';

export interface ComparisonNavigation {label:string;previous?:()=>void;next?:()=>void}

export function CandidateComparison({s,frame,clip,navigation}:{s:Studio;frame:Frame;clip?:Clip;navigation?:ComparisonNavigation}) {
  const project=s.snapshot!;
  const [referenceId,setReferenceId]=useState((clip?clip.referenceRevisionId:project.activeReferenceRevisionId)||'');
  const [zoom,setZoom]=useState('fit');
  const [expanded,setExpanded]=useState(false);
  const reference=project.references.find(r=>r.referenceRevisionId===referenceId&&r.approval==='approved');
  const identity=project.assets.find(a=>a.assetId===reference?.identityAssetId);
  const candidate=project.assets.find(a=>a.assetId===frame.imageAssetId);
  const views=[{label:'승인된 외형 기준',asset:identity,id:reference?.referenceRevisionId},{label:'선택한 프레임 후보',asset:candidate,id:frame.frameVersionId}];
  const controls=<div className="row comparison-controls">
    <Select label="나란히 비교할 승인 기준" value={referenceId} onChange={e=>setReferenceId(e.target.value)}>
      <option value="">승인 기준 선택</option>
      {project.references.filter(r=>r.approval==='approved').map(r=><option key={r.referenceRevisionId} value={r.referenceRevisionId}>{referenceLabel(project,r.referenceRevisionId)}{r.referenceRevisionId===clip?.referenceRevisionId?' · 이 동작의 기준':''}</option>)}
    </Select>
    <Select label="비교 이미지 배율" value={zoom} onChange={e=>setZoom(e.target.value)}><option value="fit">패널에 맞춤</option><option value="1">1:1 픽셀</option><option value="2">200% 확대</option><option value="4">400% 확대</option></Select>
  </div>;
  const comparison=<div className="comparison-grid">{views.map(view=><figure key={view.label}>
    <figcaption><strong>{view.label}</strong><span>{view.label==='승인된 외형 기준'?referenceLabel(project,view.id):short(view.id)}</span></figcaption>
    <div className={`comparison-image checker ${zoom==='fit'?'fit':''}`}>{view.asset?<img src={view.asset.url} alt={view.label} style={zoom==='fit'?undefined:{width:view.asset.width*Number(zoom),height:view.asset.height*Number(zoom)}}/>:<p>{view.label==='승인된 외형 기준'?'승인한 외형 기준을 선택해 주세요.':'후보 원본 이미지를 찾을 수 없습니다.'}</p>}</div>
    <small>{view.asset?`${assetLabel(view.asset)} · ${view.asset.width} × ${view.asset.height}`:'자료 없음'}</small>
  </figure>)}</div>;
  const dialog=<EditorDialog open={expanded} title="승인 기준과 후보 크게 비교" className="candidate-comparison-dialog" onClose={()=>setExpanded(false)}>
    <div className="comparison-expanded-content">
      {navigation&&<div className="comparison-navigation" role="group" aria-label="비교 프레임 이동"><button type="button" disabled={!navigation.previous} onClick={navigation.previous}>이전 프레임</button><span role="status">{navigation.label}</span><button type="button" disabled={!navigation.next} onClick={navigation.next}>다음 프레임</button></div>}
      {controls}{comparison}
    </div>
  </EditorDialog>;
  return <>
    {controls}
    <button type="button" className="comparison-expand" onClick={()=>setExpanded(true)}>두 이미지 크게 비교</button>
    {comparison}
    {/* The inspector can be hidden at narrow widths; its modal stays outside. */}
    {typeof document==='undefined'?dialog:createPortal(dialog,document.body)}
    {reference&&<p className="caption">고정 특징: {reference.fixedTraits||'승인된 외형 이미지 기준'} · 비교 기준 선택은 동작의 사용 기준을 변경하지 않습니다.</p>}
  </>;
}
