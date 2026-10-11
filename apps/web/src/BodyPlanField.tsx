import {Select} from './ui';
import BODY_PLANS from '../../../packages/contracts/body-plans.json';

const presetFor = (value: string) => BODY_PLANS.find(plan => plan.value === (value.trim().toLowerCase() || 'biped'));
export const bodyPlanLabel = (value: string) => presetFor(value)?.label ?? value;

export function BodyPlanField({label, value, onChange}: {label: string; value: string; onChange: (value: string) => void}) {
  const preset = presetFor(value);
  return <>
    <Select label={label} value={preset?.value ?? value} onChange={e => onChange(e.target.value)}>
      {BODY_PLANS.map(plan => <option key={plan.value} value={plan.value}>{plan.label}</option>)}
      {!preset && <option value={value} disabled>기존 복합 설정 · 유지 중</option>}
    </Select>
    <p className="caption">목록에 없는 형태는 ‘기준 그림의 구조 그대로 유지’를 선택하세요.</p>
    {!preset && <p className="caption">이전에 저장한 복합 설정을 유지합니다. 위에서 형태를 선택하면 선택한 형태로 변경됩니다.</p>}
  </>;
}
