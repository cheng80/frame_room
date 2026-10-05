import {useEffect,useId,useRef,useState,type KeyboardEvent} from 'react';
import {ArrowLeft,ArrowLeftRight,ArrowRight,CheckCircle2,Copy,ImagePlus,Layers,PanelLeft,PanelRight,Plus,Scissors,SlidersHorizontal,Sparkles,Trash2,X} from 'lucide-react';
import type {Studio} from './useStudio';
import {EditorCanvas} from './Canvas';
import {CandidateReview} from './CandidateReview';
import {ClipTools} from './ClipToolsPanel';
import {CandidateLibrary} from './CandidateLibrary';
import {NextWorkPanel} from './WorkflowPanel';
import {nextWork,approvalLabel,type WorkTarget} from './workflow';
import {ReviewStep} from './FinishSteps';
import {Check,Input,Num,Select,short} from './ui';
import {assetProvenanceLabel} from './assetProvenance';
import {defaultTransform,type Point,type RGBA,type Transform} from './types';
import './animation-workspace.css';

type ActionId='assets'|'reference'|'generate'|'extract'|'align'|'export';
type WorkspaceView='canvas'|'library'|'inspector';
type InspectorTab='slot'|'pixel'|'review'|'next';
type ActionSelection={frameVersionId?:string;assetId?:string};
interface Props {s:Studio;clipId:string;onClip:(id:string)=>void;onAction?:(id:string,selection?:ActionSelection)=>void;onSelectionChange?:(selection:ActionSelection)=>void}

/** Keyboard tab navigation follows the visible buttons without global listeners. */
function tabKeys(event:KeyboardEvent<HTMLDivElement>){
  const buttons=Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
  const current=buttons.indexOf(event.target as HTMLButtonElement);
  if(current<0)return;
  const delta=event.key==='ArrowRight'?1:event.key==='ArrowLeft'?-1:0;
  const index=event.key==='Home'?0:event.key==='End'?buttons.length-1:delta?(current+delta+buttons.length)%buttons.length:-1;
  if(index>=0){event.preventDefault();buttons[index].focus();buttons[index].click();}
}

export function EditStep({s,clipId,onClip,onAction,onSelectionChange}:Props){
  const p=s.snapshot!;
  const id=useId();
  const [name,setName]=useState('대기');
  const [newClipOpen,setNewClipOpen]=useState(false);
  const [selected,setSelected]=useState('');
  const [candidate,setCandidate]=useState('');
  const [includeHidden,setIncludeHidden]=useState(false);
  const [libraryTab,setLibraryTab]=useState<'clips'|'candidates'>('clips');
  const [inspectorTab,setInspectorTab]=useState<InspectorTab>('slot');
  const [view,setView]=useState<WorkspaceView>('canvas');
  const [compare,setCompare]=useState(false);
  const [canvasTarget,setCanvasTarget]=useState<'timeline'|'candidate'>('timeline');
  const [tool,setTool]=useState('select');
  const [color,setColor]=useState('#9cf4c0');
  const [alpha,setAlpha]=useState(255);
  const [pixelX,setPixelX]=useState(0);
  const [pixelY,setPixelY]=useState(0);
  const [onion,setOnion]=useState(false);
  const libraryToggle=useRef<HTMLButtonElement>(null);
  const inspectorToggle=useRef<HTMLButtonElement>(null);
  const clip=p.clips.find(c=>c.clipId===s.resolveId(clipId))||p.clips[0];
  const occurrence=clip?.occurrences.find(o=>o.occurrenceId===s.resolveId(selected))||clip?.occurrences[0];
  const index=clip&&occurrence?clip.occurrences.indexOf(occurrence):-1;
  const occurrenceFrame=p.frames.find(f=>f.frameVersionId===occurrence?.frameVersionId);
  const candidateFrame=p.frames.find(f=>f.frameVersionId===s.resolveId(candidate));
  const selectedFrame=(canvasTarget==='timeline'?occurrenceFrame||candidateFrame:candidateFrame||occurrenceFrame)||p.frames.find(f=>!f.hidden);
  const activeFrameVersionId=selectedFrame?.frameVersionId;
  const activeAssetId=selectedFrame?.rawAssetId;
  const reportedSelection=useRef<ActionSelection|null>(null);
  useEffect(()=>{
    if(!onSelectionChange)return;
    const previous=reportedSelection.current;
    if(previous&&previous.frameVersionId===activeFrameVersionId&&previous.assetId===activeAssetId)return;
    const selection={frameVersionId:activeFrameVersionId,assetId:activeAssetId};
    reportedSelection.current=selection;
    onSelectionChange(selection);
  },[activeFrameVersionId,activeAssetId,onSelectionChange]);
  const assetById=new Map(p.assets.map(a=>[a.assetId,a]));
  const frameById=new Map(p.frames.map(f=>[f.frameVersionId,f]));
  const frameNumberById=new Map(p.frames.map((f,i)=>[f.frameVersionId,i+1]));
  const candidateAsset=selectedFrame?assetById.get(selectedFrame.imageAssetId):undefined;
  const candidateRawAsset=selectedFrame?assetById.get(selectedFrame.rawAssetId):undefined;
  const candidateSource=candidateAsset?assetProvenanceLabel(candidateAsset,assetById):undefined;
  const group=p.alignmentGroups.find(g=>g.frameVersionIds.includes(occurrence?.frameVersionId||''));
  const defaultPivot={x:(group?.cell.width||512)/2,y:(group?.cell.height||512)/2};
  const transform={...defaultTransform(defaultPivot),...occurrence?.transform,pivot:occurrence?.transform.pivot||defaultPivot};
  const reference=p.references.find(r=>r.referenceRevisionId===(clip?.referenceRevisionId||p.activeReferenceRevisionId)&&r.approval==='approved');
  const referenceAsset=reference?assetById.get(reference.identityAssetId):undefined;
  const duration=clip?.occurrences.reduce((n,o)=>n+o.durationMs,0)||0;
  const blocked=s.busy;
  const work=nextWork(p,clip,!!s.commands.length,s.jobs,!!s.conflict);

  function clipEdit(type:string,extra:Record<string,unknown>){if(clip)s.edit({type,clipId:clip.clipId,...extra});}
  function selectClip(next:string){onClip(next);setSelected('');setCanvasTarget('timeline');setView('canvas');}
  function selectOccurrence(next:string){setSelected(next);setCanvasTarget('timeline');}
  function createClip(){
    if(!name.trim()||blocked)return;
    const next=s.edit({type:'createClip',clip:{name:name.trim(),referenceRevisionId:p.activeReferenceRevisionId}});
    if(next){selectClip(next);setNewClipOpen(false);}
  }
  function addCandidate(){
    if(!clip||!selectedFrame)return;
    const next=s.edit({type:'addOccurrence',clipId:clip.clipId,frameVersionId:selectedFrame.frameVersionId});
    if(next){selectOccurrence(next);setView('canvas');}
  }
  function duplicate(){
    if(!clip||!occurrence)return;
    const next=s.edit({type:'duplicateOccurrence',clipId:clip.clipId,occurrenceId:occurrence.occurrenceId});
    if(next)selectOccurrence(next);
  }
  function move(delta:number){
    if(!clip||!occurrence)return;
    const ids=clip.occurrences.map(o=>o.occurrenceId),i=ids.indexOf(occurrence.occurrenceId),j=i+delta;
    if(j<0||j>=ids.length)return;
    [ids[i],ids[j]]=[ids[j],ids[i]];
    clipEdit('reorderOccurrences',{occurrenceIds:ids});
    s.setNotice(`선택 슬롯을 ${j+1}번째로 이동했습니다.`);
  }
  function reverse(){
    if(blocked||!clip||clip.occurrences.length<2)return;
    if(occurrence)setSelected(occurrence.occurrenceId);
    clipEdit('reorderOccurrences',{occurrenceIds:clip.occurrences.map(o=>o.occurrenceId).reverse()});
    s.setNotice('재생 순서를 뒤집었습니다.');
  }
  function setTransform(changes:Partial<Transform>){if(occurrence)clipEdit('setTransform',{occurrenceId:occurrence.occurrenceId,transform:{...transform,...changes}});}
  function pixel(point:Point){
    if(!occurrence||tool==='select'||point.x<0||point.y<0||point.x>=(group?.cell.width||512)||point.y>=(group?.cell.height||512))return;
    const rgba:RGBA=tool==='eraser'?[0,0,0,0]:[parseInt(color.slice(1,3),16),parseInt(color.slice(3,5),16),parseInt(color.slice(5,7),16),alpha];
    clipEdit('setPixelEdits',{occurrenceId:occurrence.occurrenceId,pixelEdits:[...(occurrence.pixelEdits||[]).filter(e=>e.x!==point.x||e.y!==point.y),{...point,color:rgba}]});
  }
  function action(next:ActionId,selection?:ActionSelection){onAction?.(next,selection);}
  function navigateWork(target:WorkTarget){
    if(target.clipId)onClip(target.clipId);
    if(target.frameVersionId){setCandidate(target.frameVersionId);setCanvasTarget('candidate');}
    const targetClip=p.clips.find(c=>c.clipId===(target.clipId||clip?.clipId));
    const targetSlot=target.occurrenceId||targetClip?.occurrences.find(o=>o.frameVersionId===target.frameVersionId)?.occurrenceId;
    if(targetSlot){setSelected(targetSlot);if(target.action!=='frame-review')setCanvasTarget('timeline');}
    switch(target.action){
      case 'save':void s.save();break;
      case 'frame-review':case 'clip-review':
        setInspectorTab('review');setView('inspector');
        requestAnimationFrame(()=>{const panel=document.getElementById(`${id}-inspector-review`);if(target.action==='clip-review')panel?.querySelector('.aw-clip-review')?.scrollIntoView({block:'start'});else if(panel)panel.scrollTop=0;});break;
      case 'pixel':setInspectorTab('pixel');setView('inspector');break;
      case 'clip-settings':setInspectorTab('slot');setView('inspector');break;
      case 'inspect':setInspectorTab('next');setView('inspector');requestAnimationFrame(()=>document.getElementById(`${id}-inspector-next`)?.querySelector('.workflow-inspection')?.scrollIntoView({block:'start'}));break;
      case 'create-clip':setNewClipOpen(true);setLibraryTab('clips');setView('library');break;
      case 'candidates':setLibraryTab('candidates');setView('library');break;
      default:onAction?.(target.action,{frameVersionId:target.frameVersionId,assetId:target.assetId});
    }
  }
  function closePane(){const previous=view;setView('canvas');(previous==='library'?libraryToggle:inspectorToggle).current?.focus();}
  function timelineKeys(event:KeyboardEvent<HTMLDivElement>){
    if((event.target as HTMLElement).matches('input,select,textarea')||!clip||!occurrence||blocked)return;
    if(event.key==='ArrowLeft'||event.key==='ArrowRight'){
      event.preventDefault();const delta=event.key==='ArrowLeft'?-1:1;
      if(event.altKey)move(delta);else selectOccurrence(clip.occurrences[Math.max(0,Math.min(clip.occurrences.length-1,index+delta))].occurrenceId);
    }
    if(event.key==='Home'||event.key==='End'){event.preventDefault();selectOccurrence(clip.occurrences[event.key==='Home'?0:clip.occurrences.length-1].occurrenceId);}
    if(event.key==='Delete'){event.preventDefault();clipEdit('removeOccurrence',{occurrenceId:occurrence.occurrenceId});}
  }

  return <div className="animation-workspace" data-view={view} onKeyDown={e=>{if(e.key==='Escape'&&view!=='canvas'){e.preventDefault();closePane();}}}>
    <div className="aw-layout">
      <header className="aw-toolbar" aria-label="애니메이션 편집 도구">
        <div className="aw-view-switch" aria-label="편집 패널 전환">
          <button ref={libraryToggle} type="button" aria-pressed={view==='library'} aria-controls={`${id}-library`} onClick={()=>setView(v=>v==='library'?'canvas':'library')}><PanelLeft size={15}/><span>라이브러리</span></button>
          <button type="button" aria-pressed={view==='canvas'} aria-controls={`${id}-canvas`} onClick={()=>setView('canvas')}>캔버스</button>
          <button ref={inspectorToggle} type="button" aria-pressed={view==='inspector'} aria-controls={`${id}-inspector`} onClick={()=>setView(v=>v==='inspector'?'canvas':'inspector')}><PanelRight size={15}/><span>속성</span></button>
        </div>
        <div className="aw-document"><Layers size={15}/><strong>{clip?.name||'애니메이션'}</strong><span>{clip?.occurrences.length||0} 슬롯 · {duration}ms</span></div>
        <div className="aw-toolbar-actions"><button type="button" className="aw-next-button" aria-label={`다음 작업 ${work.length}개`} title={work[0]?.label||'다음 작업'} onClick={()=>{setInspectorTab('next');setView('inspector');}}><span>{work[0]?.label||'다음 작업'}</span> · {work.length}</button>
          <button type="button" aria-pressed={compare} onClick={()=>{setCompare(v=>!v);setView('canvas');}} title="승인된 외형 기준과 나란히 비교">기준 비교</button>
        </div>
      </header>

      <button type="button" className="aw-backdrop" tabIndex={-1} aria-label="열린 패널 닫기" onClick={closePane}/>
      <aside id={`${id}-library`} className="aw-library aw-pane" aria-label="동작과 후보 라이브러리">
        <div className="aw-pane-heading"><h2>라이브러리</h2><button type="button" className="aw-pane-close" aria-label="라이브러리 닫기" onClick={closePane}><X size={15}/></button></div>
        <div className="aw-source-actions" aria-label="자료 준비 도구">
          <button type="button" disabled={!onAction} onClick={()=>action('assets')}><ImagePlus size={14}/>자료</button>
          <button type="button" disabled={!onAction} onClick={()=>action('generate')}><Sparkles size={14}/>AI 생성</button>
          <button type="button" disabled={!onAction} onClick={()=>action('extract',selectedFrame?{frameVersionId:selectedFrame.frameVersionId,assetId:selectedFrame.rawAssetId}:undefined)}><Scissors size={14}/>추출</button>
        </div>
        <div className="aw-tabs" role="tablist" aria-label="라이브러리 종류" onKeyDown={tabKeys}>
          {(['clips','candidates'] as const).map(tab=><button type="button" key={tab} id={`${id}-library-tab-${tab}`} role="tab" aria-selected={libraryTab===tab} aria-controls={`${id}-library-${tab}`} tabIndex={libraryTab===tab?0:-1} onClick={()=>setLibraryTab(tab)}>{tab==='clips'?'동작':'후보'}<span>{tab==='clips'?p.clips.length:p.frames.length}</span></button>)}
        </div>
        <div id={`${id}-library-clips`} className="aw-library-content" role="tabpanel" aria-labelledby={`${id}-library-tab-clips`} hidden={libraryTab!=='clips'}>
          <div className="aw-scroll aw-clip-list">
            {p.clips.map(c=><button type="button" key={c.clipId} className={`aw-clip ${clip?.clipId===c.clipId?'is-selected':''}`} aria-pressed={clip?.clipId===c.clipId} onClick={()=>selectClip(c.clipId)}><span className="aw-clip-icon"><Layers size={15}/></span><span><strong>{c.name}</strong><small>{c.occurrences.length} 슬롯 · {c.loop?'반복':'단발'}</small><span className="aw-state">{approvalLabel(c.review,c.reviewInvalidatedReason)}</span></span></button>)}
            {!p.clips.length&&<p className="aw-empty">아직 동작이 없습니다.<br/>아래에서 첫 동작을 만드세요.</p>}
          </div>
          <div className="aw-pane-footer">
            <button type="button" className="aw-wide" aria-expanded={newClipOpen} onClick={()=>setNewClipOpen(v=>!v)}><Plus size={14}/>새 동작</button>
            {newClipOpen&&<form className="aw-create-clip" onSubmit={e=>{e.preventDefault();createClip();}}><Input label="새 동작 이름" value={name} required maxLength={200} onChange={e=>setName(e.target.value)} autoFocus/><button type="submit" className="primary aw-wide" disabled={blocked||!name.trim()}>동작 만들기</button></form>}
          </div>
        </div>
        <div id={`${id}-library-candidates`} className="aw-library-content" role="tabpanel" aria-labelledby={`${id}-library-tab-candidates`} hidden={libraryTab!=='candidates'}>
          <div className="aw-filter"><Check label="숨긴 후보 포함" checked={includeHidden} onChange={setIncludeHidden}/></div>
          <CandidateLibrary snapshot={p} jobs={s.jobs} includeHidden={includeHidden} selectedFrameId={selectedFrame?.frameVersionId} onSelect={fid=>{setCandidate(fid);setCanvasTarget('candidate');setView('canvas');}} onUse={(cid,oid)=>{onClip(cid);selectOccurrence(oid);setView('canvas');}} onSource={assetId=>action('extract',{assetId})}/>
          <div className="aw-pane-footer"><button type="button" className="primary aw-wide" disabled={blocked||!clip||!selectedFrame} onClick={addCandidate}><Plus size={14}/>선택 후보를 순서에 추가</button>{!clip&&<small>동작 탭에서 먼저 동작을 만드세요.</small>}<button type="button" className="aw-wide" disabled={!selectedFrame} onClick={()=>{setInspectorTab('review');setView('inspector');}}>선택 후보 수동 승인</button></div>
        </div>
      </aside>

      <section id={`${id}-canvas`} className="aw-center" aria-label="애니메이션 캔버스">
        <div className="aw-canvas-heading"><div className="aw-target-switch" aria-label="중앙 미리보기 선택"><button type="button" aria-pressed={canvasTarget==='timeline'} onClick={()=>setCanvasTarget('timeline')}>재생 순서</button><button type="button" disabled={!selectedFrame} aria-pressed={canvasTarget==='candidate'} onClick={()=>setCanvasTarget('candidate')}>후보 원본</button></div><span>{canvasTarget==='timeline'?(occurrence?`슬롯 ${index+1} · ${occurrence.durationMs}ms`:'빈 타임라인'):selectedFrame?`후보 ${p.frames.indexOf(selectedFrame)+1}`:'후보 없음'}</span></div>
        <div className={`aw-canvas-area ${compare?'with-reference':''}`}>
          {compare&&<section className="aw-reference" aria-label="승인 외형 기준"><div className="aw-reference-heading"><strong>승인 기준</strong><small>{short(reference?.referenceRevisionId)}</small><button type="button" aria-label="기준 비교 닫기" onClick={()=>setCompare(false)}><X size={13}/></button></div><div className="aw-reference-image checker">{referenceAsset?<img src={referenceAsset.url} alt="승인된 외형 기준 원본"/>:<div className="aw-empty"><p>승인한 기준이 없습니다.</p><button type="button" disabled={!onAction} onClick={()=>action('reference')}>기준 정하기</button></div>}</div><p title={reference?.fixedTraits}>{reference?.fixedTraits||'동작에 연결된 승인 기준입니다.'}</p></section>}
          <div className="aw-canvas-host">{canvasTarget==='timeline'?<EditorCanvas snapshot={p} clip={clip} selected={occurrence?.occurrenceId||''} onSelect={selectOccurrence} onPixel={pixel} tool={tool} onion={onion}/>:<div className="aw-raw-preview"><div className="aw-raw-heading"><span className="badge">후보 원본 · 순서에 자동 추가되지 않음</span><button type="button" className="primary" disabled={blocked||!clip||!selectedFrame} onClick={addCandidate}>순서에 추가</button></div><div className="aw-raw-image checker">{candidateAsset?<img src={candidateAsset.url} alt="선택한 후보 원시 이미지"/>:<p className="aw-empty">후보 원본을 찾을 수 없습니다.</p>}</div><div className="aw-raw-caption"><span>{candidateAsset?`${candidateAsset.width} × ${candidateAsset.height} · ${candidateSource?.label}`:'자료 없음'}</span>{candidateSource?.originLabel&&<span>{candidateSource.originLabel}</span>}<button type="button" disabled={!selectedFrame} onClick={()=>{setInspectorTab('review');setView('inspector');}}>수동 승인 열기</button></div></div>}</div>
        </div>
      </section>

      <section className="aw-timeline" aria-label="재생 순서와 표시 시간">
        <div className="aw-timeline-heading"><h2>재생 순서 <span>{clip?.occurrences.length||0}</span></h2><span>{duration}ms · {clip?.loop?'반복':'마지막 유지'}</span><div className="aw-sequence-actions"><button type="button" aria-label="재생 순서 리버스" title="리버스 · 전체 재생 순서 뒤집기" disabled={blocked||!clip||clip.occurrences.length<2} onClick={reverse}><ArrowLeftRight size={14}/>리버스</button><button type="button" aria-label="선택 슬롯 앞으로 이동" title="앞으로 · Alt+←" disabled={blocked||index<=0} onClick={()=>move(-1)}><ArrowLeft size={14}/></button><button type="button" aria-label="선택 슬롯 뒤로 이동" title="뒤로 · Alt+→" disabled={blocked||!clip||index<0||index>=clip.occurrences.length-1} onClick={()=>move(1)}><ArrowRight size={14}/></button><button type="button" aria-label="슬롯 복제" title="슬롯 복제" disabled={blocked||!occurrence} onClick={duplicate}><Copy size={14}/></button><button type="button" aria-label="순서에서 제거" title="순서에서 제거 · Delete" className="danger-text" disabled={blocked||!occurrence} onClick={()=>occurrence&&clipEdit('removeOccurrence',{occurrenceId:occurrence.occurrenceId})}><Trash2 size={14}/></button></div></div>
        <div className="aw-timeline-scroll" tabIndex={0} aria-label="재생 순서. 좌우 키로 선택, Alt 좌우로 순서 이동, Delete로 제거" onKeyDown={timelineKeys}>
          <div className="aw-timeline-track">{clip?.occurrences.map((o,i)=>{
            const frame=frameById.get(o.frameVersionId),asset=frame?assetById.get(frame.imageAssetId):undefined;
            const frameNumber=frameNumberById.get(o.frameVersionId);
            const frameLabel=frameNumber?`후보 ${String(frameNumber).padStart(2,'0')}`:'후보 없음';
            return <button type="button" key={o.occurrenceId} className={`aw-frame-slot ${occurrence?.occurrenceId===o.occurrenceId?'is-selected':''}`} aria-pressed={occurrence?.occurrenceId===o.occurrenceId} aria-label={`슬롯 ${i+1}, ${frameLabel}, ${o.durationMs}밀리초`} title={`${frameLabel} · 재생 순서 ${i+1}\n${asset?.originalFilename||''}\n${o.frameVersionId}`} onClick={()=>selectOccurrence(o.occurrenceId)}>
              <span className="aw-slot-number">{frameLabel}</span>
              <span className="aw-slot-image checker">{asset&&<img src={asset.url} alt=""/>}</span>
              <span className="aw-slot-details"><span className="aw-slot-position">순서 {String(i+1).padStart(2,'0')}</span><span>{o.durationMs} ms</span></span>
            </button>;
          })}{!clip?.occurrences.length&&<div className="aw-timeline-empty"><span>재생할 프레임이 없습니다.</span><button type="button" onClick={()=>{setLibraryTab('candidates');setView('library');}}>후보에서 추가</button></div>}</div>
        </div>
        <div className="aw-timing-controls">{occurrence?<><Select label="슬롯 표시 시간" value={occurrence.timingMode} onChange={e=>clipEdit('setTiming',{occurrenceId:occurrence.occurrenceId,timingMode:e.target.value,durationMs:e.target.value==='fps'?Math.round(1000/clip!.defaultFps):occurrence.durationMs})}><option value="fps">기본 FPS 따름</option><option value="explicit">직접 지정</option></Select><Num label="표시 시간 (ms)" value={occurrence.durationMs} min={1} max={60000} onChange={durationMs=>clipEdit('setTiming',{occurrenceId:occurrence.occurrenceId,timingMode:'explicit',durationMs})}/><span className="aw-timing-hint">같은 후보도 슬롯마다 독립적으로 저장됩니다.</span></>:<span>빈 순서는 출력되지 않습니다. 후보를 추가하세요.</span>}</div>
      </section>

      <aside id={`${id}-inspector`} className="aw-inspector aw-pane" aria-label="선택 항목 속성">
        <div className="aw-pane-heading"><h2><SlidersHorizontal size={14}/>속성</h2><button type="button" className="aw-pane-close" aria-label="속성 패널 닫기" onClick={closePane}><X size={15}/></button></div>
        <div className="aw-tabs" role="tablist" aria-label="속성 종류" onKeyDown={tabKeys}>{(['slot','pixel','review','next'] as const).map(tab=><button type="button" key={tab} id={`${id}-inspector-tab-${tab}`} role="tab" aria-selected={inspectorTab===tab} aria-controls={`${id}-inspector-${tab}`} tabIndex={inspectorTab===tab?0:-1} onClick={()=>setInspectorTab(tab)}>{{slot:'슬롯',pixel:'픽셀',review:'수동 승인',next:'다음 작업'}[tab]}</button>)}</div>
        <div id={`${id}-inspector-slot`} className="aw-inspector-content aw-scroll" role="tabpanel" aria-labelledby={`${id}-inspector-tab-slot`} hidden={inspectorTab!=='slot'}>
          {selectedFrame&&<section className="aw-property-group" aria-label="선택 이미지 파일 정보"><h3>선택 이미지 파일</h3><dl className="aw-file-info">
            <dt>후보</dt><dd>후보 {String(frameNumberById.get(selectedFrame.frameVersionId)).padStart(2,'0')}</dd>
            {canvasTarget==='timeline'&&occurrence&&<><dt>재생 순서</dt><dd>{index+1} / {clip?.occurrences.length}</dd></>}
            <dt>파일명</dt><dd>{candidateAsset?.originalFilename||'파일 정보 없음'}</dd>
            <dt>크기</dt><dd>{candidateAsset?`${candidateAsset.width} × ${candidateAsset.height} px`:'정보 없음'}</dd>
            <dt>형식</dt><dd>{candidateAsset?.mediaType||'정보 없음'}</dd>
            <dt>출처</dt><dd>{candidateSource?.label||'출처 확인 필요'}{candidateSource?.originLabel&&<> · {candidateSource.originLabel}</>}</dd>
            {candidateRawAsset&&candidateRawAsset.assetId!==candidateAsset?.assetId&&<><dt>원본 파일</dt><dd>{candidateRawAsset.originalFilename}</dd></>}
          </dl></section>}
          {clip?<><section className="aw-property-group"><h3>동작</h3><Input label="동작 이름" value={clip.name} maxLength={200} onChange={e=>clipEdit('updateClip',{changes:{name:e.target.value}})}/><Select label="동작에 사용할 승인 기준" value={clip.referenceRevisionId||''} onChange={e=>clipEdit('updateClip',{changes:{referenceRevisionId:e.target.value}})}><option value="">기준 연결 필요</option>{p.references.filter(r=>r.approval==='approved').map(r=><option key={r.referenceRevisionId} value={r.referenceRevisionId}>승인 {short(r.referenceRevisionId)}</option>)}</Select><Num label="기본 FPS" value={clip.defaultFps} min={1} max={60} onChange={defaultFps=>clipEdit('updateClip',{changes:{defaultFps}})}/><Check label="반복 재생" checked={clip.loop} onChange={loop=>clipEdit('updateClip',{changes:{loop}})}/><small>단발 재생은 마지막 프레임을 유지합니다.</small></section>{occurrence?<><section className="aw-property-group"><h3>슬롯 {index+1} · 이동·변형</h3><div className="number-grid">{(['dx','dy','scaleX','scaleY','rotationDeg','shearX','shearY'] as const).map(k=><Num key={k} label={{dx:'이동 X',dy:'이동 Y',scaleX:'가로 배율',scaleY:'세로 배율',rotationDeg:'회전 (°)',shearX:'기울기 X',shearY:'기울기 Y'}[k]} value={transform[k]} step={['scaleX','scaleY','shearX','shearY'].includes(k)?.05:1} min={k.startsWith('scale')?.05:undefined} max={k.startsWith('scale')?8:undefined} onChange={v=>setTransform({[k]:v})}/>)}<Num label="변형 중심 X" value={transform.pivot.x} onChange={x=>setTransform({pivot:{...transform.pivot,x}})}/><Num label="변형 중심 Y" value={transform.pivot.y} onChange={y=>setTransform({pivot:{...transform.pivot,y}})}/></div><Check label="좌우 반전" checked={transform.flipX} onChange={flipX=>setTransform({flipX})}/><Check label="상하 반전" checked={transform.flipY} onChange={flipY=>setTransform({flipY})}/><button type="button" disabled={blocked} onClick={()=>setTransform(defaultTransform(defaultPivot))}>변형 초기화</button></section><section className="aw-property-group"><h3>편집 보기</h3><Check label="이전·다음 프레임 겹쳐 보기" checked={onion} onChange={setOnion}/><button type="button" disabled={!onAction} onClick={()=>action('align',{frameVersionId:occurrence.frameVersionId})}>공통 크기·발 정렬 열기</button></section></>:<p className="aw-empty">후보를 순서에 추가한 뒤 슬롯을 선택하세요.</p>}</>:<div className="aw-empty"><p>먼저 동작을 만드세요.</p><button type="button" onClick={()=>{setLibraryTab('clips');setNewClipOpen(true);setView('library');}}>새 동작 만들기</button></div>}
          {clip&&<ClipTools key={`${p.projectId}:${clip.clipId}`} s={s} clipId={clip.clipId} onClip={selectClip} onSelectOccurrence={selectOccurrence}/>}
        </div>
        <div id={`${id}-inspector-pixel`} className="aw-inspector-content aw-scroll" role="tabpanel" aria-labelledby={`${id}-inspector-tab-pixel`} hidden={inspectorTab!=='pixel'}>
          <section className="aw-property-group"><h3>슬롯 픽셀·알파 보정</h3>{!occurrence&&<p className="aw-empty">먼저 재생 순서에 후보를 추가하세요.</p>}<fieldset disabled={!occurrence||blocked}><Select label="도구" value={tool} onChange={e=>{setTool(e.target.value);setCanvasTarget('timeline');}}><option value="select">선택</option><option value="pen">픽셀 펜</option><option value="eraser">알파 지우개</option></Select><Input label="펜 색" type="color" value={color} onChange={e=>setColor(e.target.value)}/><Num label="펜 알파 (0–255)" value={alpha} min={0} max={255} onChange={setAlpha}/><div className="number-grid"><Num label="픽셀 X" value={pixelX} min={0} max={(group?.cell.width||512)-1} onChange={setPixelX}/><Num label="픽셀 Y" value={pixelY} min={0} max={(group?.cell.height||512)-1} onChange={setPixelY}/></div><button type="button" className="aw-wide" disabled={tool==='select'} onClick={()=>pixel({x:pixelX,y:pixelY})}>지정 픽셀에 적용</button></fieldset><p className="caption">캔버스 또는 좌표로 입력합니다. 변형 전 셀 좌표에 적용하며 선택 슬롯만 변경합니다.</p><div className="aw-button-pair"><button type="button" disabled={blocked||!s.commands.length} onClick={s.undo}>되돌리기</button><button type="button" disabled={blocked||!s.redoCommands.length} onClick={s.redo}>다시 적용</button></div></section>
        </div>
        <div id={`${id}-inspector-review`} className="aw-inspector-content aw-scroll" role="tabpanel" aria-labelledby={`${id}-inspector-tab-review`} hidden={inspectorTab!=='review'}>
          {selectedFrame?<section className="aw-property-group"><h3>후보 {p.frames.indexOf(selectedFrame)+1} 수동 승인</h3><div className="aw-review-actions"><button type="button" disabled={!onAction} onClick={()=>action('align',{frameVersionId:selectedFrame.frameVersionId})}>이 후보 크기·발 정렬</button><button type="button" disabled={blocked} onClick={()=>s.edit({type:'setFrameReview',frameVersionId:selectedFrame.frameVersionId,review:'approved'})}><CheckCircle2 size={14}/>후보 수동 승인</button><button type="button" disabled={blocked} onClick={()=>s.edit({type:'setFrameReview',frameVersionId:selectedFrame.frameVersionId,review:selectedFrame.review,hidden:!selectedFrame.hidden})}>{selectedFrame.hidden?'후보 다시 표시':'후보 숨기기'}</button><button type="button" disabled={blocked||!clip||!occurrence} onClick={()=>{if(occurrence){clipEdit('replaceFrameVersion',{occurrenceId:occurrence.occurrenceId,frameVersionId:selectedFrame.frameVersionId});setCanvasTarget('timeline');}}}>선택 슬롯을 이 후보로 교체</button></div><CandidateReview key={`${selectedFrame.frameVersionId}:${clip?.referenceRevisionId||''}`} s={s} frame={selectedFrame} clip={clip} onSource={assetId=>action('extract',{assetId})}/></section>:<p className="aw-empty">검수할 후보가 없습니다.</p>}
          <details className="aw-clip-review" open><summary>동작 수동 승인·팀 테두리</summary><div className="aw-review-inset"><ReviewStep s={s} clipId={clip?.clipId} onNavigate={navigateWork}/></div></details>
        </div>
        <div id={`${id}-inspector-next`} className="aw-inspector-content aw-scroll" role="tabpanel" aria-labelledby={`${id}-inspector-tab-next`} hidden={inspectorTab!=='next'}><NextWorkPanel s={s} clip={clip} onNavigate={navigateWork}/></div>
      </aside>
    </div>
  </div>;
}
