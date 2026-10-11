import {useRef,useState} from 'react';
import type {Studio} from './useStudio';
import type {Frame,Clip} from './types';
import {Field} from './ui';
import {approvalLabel} from './workflow';
import {PropertyHelp} from './PropertyHelp';
import {CandidateComparison,type ComparisonNavigation} from './CandidateComparison';

/** Frame-level review, independent from an occurrence's timing and transforms. */
export function CandidateReview({s,frame,clip,onSource,navigation}:{s:Studio;frame:Frame;clip?:Clip;onSource?:(assetId:string)=>void;navigation?:ComparisonNavigation}) {
  return <section className="candidate-review" aria-label="승인 기준과 후보 비교">
    <div className="row"><h3>승인 기준과 후보 비교</h3><span className={`badge ${frame.review==='approved'?'success':'warn'}`}>{approvalLabel(frame.review)}</span><PropertyHelp title="승인 기준과 후보 비교" description="승인한 외형 그림과 선택한 후보를 나란히 확인합니다. 두 이미지 크게 비교로 확대할 수 있습니다. 여기서 고른 기준은 비교용이며 동작에 연결된 기준은 바뀌지 않습니다."/></div>
    <p className="approval-explanation">수동 승인은 직접 확인한 상태입니다. 자동 검사 통과를 뜻하지 않습니다. 기존 기록에 승인자 정보가 없으면 누가 승인했는지 판단하지 않습니다.</p>
    {frame.extractionReview&&<div className="approval-explanation"><strong>추출 검사 기록</strong><p>{frame.extractionReview.belowMinArea?'작은 조각 확인 필요':frame.extractionReview.warnings?.length?'추출 경계 확인 필요':'추출 경고 기록 없음 · 종합 자동 검사와 별개'}</p>{frame.extractionReview.warnings?.length||frame.extractionReview.belowMinArea?<button onClick={()=>onSource?.(frame.rawAssetId)} disabled={!onSource}>원본 추출 영역 확인</button>:null}</div>}
    <CandidateComparison s={s} frame={frame} clip={clip} navigation={navigation}/>
    <CandidateRejection key={frame.frameVersionId} s={s} frame={frame}/>
  </section>;
}

export function CandidateRejection({s,frame}:{s:Studio;frame:Frame}) {
  const [reason,setReason]=useState(frame.reviewReason||'');
  const [error,setError]=useState('');
  const reasonField=useRef<HTMLTextAreaElement>(null);
  const reasonIsDraft=s.commands.some(c=>c.operation.type==='setFrameReview'&&c.operation.frameVersionId===frame.frameVersionId&&c.operation.reason!==undefined);
  function reject(){
    if(!reason.trim()){setError('후보를 거절하는 이유를 입력해 주세요.');reasonField.current?.focus();return;}
    setError('');
    s.edit({type:'setFrameReview',frameVersionId:frame.frameVersionId,review:'rejected',reason:reason.trim()});
    s.setNotice('거절 사유를 초안에 적용했습니다. 상단 저장을 누르면 다시 열어도 유지됩니다.');
  }
  return <>
    {frame.reviewReason&&<div className="review-reason"><strong>{frame.review==='rejected'?(reasonIsDraft?'초안 거절 사유':'저장된 거절 사유'):'마지막 검수 사유'}</strong><p>{frame.reviewReason}</p></div>}
    <Field label="후보 거절 사유" hint={error||'외형·장비·비율·알파 등 문제를 기록하세요. 사유를 적용한 뒤 상단 저장을 눌러 확정합니다.'}>
      <textarea ref={reasonField} value={reason} maxLength={2000} aria-invalid={!!error} onChange={e=>{setReason(e.target.value);if(error)setError('');}} placeholder="예: 승인 기준과 달리 오른쪽 장갑이 사라지고 무기가 잘렸습니다."/>
    </Field>
    <div className="row"><button className="danger-text" disabled={s.busy} onClick={reject}>사유 기록·후보 거절</button><span className="caption">후보와 원본은 보존됩니다. 거절된 후보는 재검수 승인 전까지 출력할 수 없습니다.</span></div>
  </>;
}
