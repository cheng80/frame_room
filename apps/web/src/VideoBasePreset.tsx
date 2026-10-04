import {useState} from 'react';
import {Select} from './ui';
import {VIDEO_DIRECTIONS} from './videoWorkflow';

/** Still-view and mid-step guidance adapted from the public v2.19 batch prompts. */
export function VideoBasePreset({onApply}: {onApply: (prompt: string) => void}) {
  const [direction, setDirection] = useState('front');
  const [facing, setFacing] = useState('right');
  const [pose, setPose] = useState('walk');
  const side = facing === 'right' ? '오른쪽' : '왼쪽';
  const views: Record<string, string> = {
    side: `정확한 측면에서 본 모습. 몸과 얼굴, 발끝 모두 ${side}을 향한다.`,
    front: '정확한 정면. 머리·가슴·골반·양발 끝이 모두 관찰자를 향하고 얼굴은 양 귀 가운데에 둔다. 참조 그림의 측면 각도를 따르지 않는다.',
    back: '정확한 뒷면. 머리·어깨·골반을 완전히 뒤로 돌리고 뒤통수·등·양발 뒤꿈치가 관찰자를 향한다. 얼굴이 보이거나 고개만 돌아보지 않는다.',
    front_diagonal: `앞 대각선 45도. 몸과 머리를 함께 ${side}으로 돌리고 가슴과 얼굴이 같은 방향을 본다. 발끝은 화면 아래 ${side} 대각선을 향한다.`,
    back_diagonal: `뒤 대각선 45도. 몸과 머리를 화면 위 ${side}으로 함께 돌린다. 얼굴을 숨기고 뒤돌아보지 않는다. 발끝은 화면 위 ${side} 대각선을 향하며 신발 뒤쪽이 보인다.`,
  };
  const prompt = [
    '영상 시작용 2D 게임 캐릭터 그림 한 장. 승인된 참조의 외형·의상·색·머리·신체 비율·화풍을 유지한다.',
    views[direction],
    pose === 'walk'
      ? '걷기의 중간 걸음 자세. 한 발은 자기 골반 바로 아래에 평평하게 딛고, 다른 발은 자기 골반 아래에서 무릎을 조금 굽혀 살짝 든다. 두 다리는 골반 너비로 떨어지고 사이에 빈틈이 보인다. 어깨와 골반은 선택한 방향을 유지하고 팔은 다리와 반대로 작게 움직인다.'
      : '두 발을 지면에 둔 편안한 대기 자세. 몸 전체가 선택한 방향을 유지한다.',
    '장비와 손의 좌우 및 잡는 방식을 유지한다. 눈높이 시점에서 전신을 가운데 두고 머리카락·발·무기가 잘리지 않도록 사방에 여백을 둔다. 시트·분할 칸·글자 없이 한 자세만 그린다.',
  ].join('\n');
  return <details className="source-tool-details">
    <summary>영상용 기준 그림 준비</summary>
    <Select label="기준 그림의 보기 방향" value={direction} onChange={e => setDirection(e.target.value)}>
      {VIDEO_DIRECTIONS.map(view => <option key={view.id} value={view.id}>{view.label}</option>)}
    </Select>
    <Select label="기준 그림의 좌우" value={facing} onChange={e => setFacing(e.target.value)}>
      <option value="right">오른쪽</option><option value="left">왼쪽</option>
    </Select>
    <Select label="영상 시작 자세" value={pose} onChange={e => setPose(e.target.value)}>
      <option value="walk">중간 걸음 · 보행용</option><option value="idle">두 발 대기</option>
    </Select>
    <p className="caption">정면·뒷면 보행은 두 다리가 구별되는 중간 자세로 시작할 수 있습니다. 방향과 자세 설명을 추가하고 요청을 한 장으로 설정합니다.</p>
    <button type="button" onClick={() => onApply(prompt)}>기준 그림 설명 추가</button>
    <p className="caption">설명 추가만으로 생성하지 않습니다. 새 후보 생성 후 결과 그림을 영상의 기준 이미지로 선택하세요.</p>
  </details>;
}
