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
    {frame.selectionDecision&&<SelectionDecisionNote decision={frame.selectionDecision}/>}
    <CandidateComparison s={s} frame={frame} clip={clip} navigation={navigation}/>
    <CandidateRejection key={frame.frameVersionId} s={s} frame={frame}/>
  </section>;
}

const SELECTION_LABELS:Record<string,string>={keep:'사용 추천',reject:'제외 제안',review:'확인 필요'};
// LAYA_*/JEV_* codes and the laya-mlx/jev sources only appear in records saved 2026-10-12~13; kept so they stay readable.
const SELECTION_REASONS:Record<string,string>={ALL_CHECKS_OK:'관찰 항목 이상 없음',OBSERVATION_MISSING:'관찰 결과 없음',OBSERVATION_FAILED:'관찰 호출 실패',
  NO_KEEP_CANDIDATE_UNIFORM_KEPT:'확실한 대체 후보가 없어 균등 프레임 유지',CONFLICT_LAYA_VS_RULES:'Laya와 규칙 판정 불일치',
  CONFLICT_EDGE_TOUCH_VS_NOT_CROPPED:'가장자리 접촉과 관찰 결과 불일치',LAYA_ABSTAINED:'Laya 신뢰도 부족',LAYA_TRUNCATED:'Laya 입력 잘림',
  LAYA_OPTIONS_COLLAPSED:'Laya 선택지 충돌',LAYA_ERROR:'Laya 실행 오류',LAYA_CHOICE:'Laya 판정',CODE_EMPTY_FRAME:'빈 프레임',
  JEV_CHOICE:'Jev 판정',JEV_LOW_CONFIDENCE:'Jev 신뢰도 부족',CONFLICT_JEV_VS_RULES:'Jev와 규칙 판정 불일치'};
const OBSERVED:Record<string,string>={same_character:'다른 캐릭터',extra_or_missing_parts:'신체·장비 추가/누락',body_cropped:'잘림',
  blur_or_smear:'흐림·번짐',background_residue:'배경 잔여',colour_contamination:'기준과 다른 색 얼룩',pose_fits_neighbors:'앞뒤 자세 불연속'};
export function selectionReason(code:string){
  const [kind,field]=code.split(':');
  if(field&&kind==='OBSERVED')return `관찰: ${field.split(',').map(f=>OBSERVED[f]||f).join(', ')}`;
  if(field&&kind==='JEV_ERROR')return `Jev 호출 실패: ${field}`;
  if(field&&kind==='UNKNOWN')return `판단 불가: ${field.split(',').map(f=>OBSERVED[f]||f).join(', ')}`;
  return SELECTION_REASONS[code]||code;
}
export const selectionLabel=(decision:NonNullable<Frame['selectionDecision']>)=>decision.role==='uniform-alternative'?'교체된 균등 프레임':SELECTION_LABELS[decision.label||'']||'판정 미기록';

/** Automatic recommendation only: it never changes review/hidden and the user can swap slots freely. */
function SelectionDecisionNote({decision}:{decision:NonNullable<Frame['selectionDecision']>}) {
  return <div className="approval-explanation"><strong>영상 프레임 선별 · {selectionLabel(decision)}</strong>
    <p>{decision.role==='uniform-alternative'?`슬롯 ${(decision.slot??0)+1}의 원래 균등 프레임입니다. 필요하면 이 후보로 바꿀 수 있습니다.`:
      `슬롯 ${(decision.slot??0)+1}${decision.changed?` · 균등 위치 ${decision.uniformSourceFrameIndex}번 대신 선택`:' · 균등 위치 유지'}${decision.slotStatus==='review'?' · 확실한 대체 후보가 없어 확인 필요':''}`} · 판정 {decision.source==='laya-mlx'?'Laya MLX':decision.source==='jev'?'Jev(TypeSafe)':decision.source==='rules'?'규칙':'FrameRoom 정책'}</p>
    {decision.reasons?.length?<p>{decision.reasons.map(selectionReason).join(' · ')}</p>:null}
    <p className="caption">자동 추천이며 검토·숨김 기록과 별개입니다.</p></div>;
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
