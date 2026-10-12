import {Input, Select} from './ui';
import {VIDEO_DIRECTIONS} from './videoWorkflow';
import type {VideoBaseSettings} from './videoBasePrompt';
import {BodyPlanField} from './BodyPlanField';

export function VideoBasePreset({value, onChange}: {value: VideoBaseSettings; onChange: (value: VideoBaseSettings) => void}) {
  return <details className="source-tool-details" open>
    <summary>영상용 기준 그림 준비</summary>
    <Select label="기준 그림의 보기 방향" value={value.direction} onChange={e => onChange({...value, direction: e.target.value})}>
      {VIDEO_DIRECTIONS.map(view => <option key={view.id} value={view.id}>{view.label}</option>)}
    </Select>
    <Select label="기준 그림의 좌우" disabled={value.direction === 'front' || value.direction === 'back'} value={value.facing} onChange={e => onChange({...value, facing: e.target.value})}>
      <option value="right">오른쪽</option><option value="left">왼쪽</option>
    </Select>
    <Select label="영상 시작 자세" value={value.pose} onChange={e => onChange({...value, pose: e.target.value})}>
      <option value="walk">이동 중간 자세</option><option value="idle">대기 자세</option>
    </Select>
    <BodyPlanField label="기준 그림의 신체 구조" value={value.bodyPlan} onChange={bodyPlan => onChange({...value, bodyPlan})}/>
    <Input label="기준 그림의 장비와 손" value={value.equipment} maxLength={2000} onChange={e => onChange({...value, equipment: e.target.value})} placeholder="예: sword:right; shield:left"/>
    <p className="caption">캐릭터 자신의 손을 기준으로 지정합니다. 정면·뒷면에서는 보기의 좌우를 적용하지 않으며 장비를 든 손은 유지합니다.</p>
    <p className="caption">설명과 저장 기준의 기존 보기 방향을 정리하고, 선택한 방향·자세·신체 구조·장비를 새 후보 생성 요청에 반영합니다.</p>
    <p className="caption">새 후보 생성 후 결과 그림을 영상의 기준 이미지로 선택하세요. 영상은 자동 생성하지 않습니다.</p>
  </details>;
}
