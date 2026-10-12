import {VIDEO_DIRECTIONS} from './videoWorkflow';
import BODY_PLANS from '../../../packages/contracts/body-plans.json';

export type VideoBaseSettings = {direction: string; facing: string; pose: string; bodyPlan: string; equipment: string};

export const DEFAULT_VIDEO_BASE_SETTINGS: VideoBaseSettings = {direction: 'front', facing: 'right', pose: 'walk', bodyPlan: '', equipment: ''};

/** Keep a non-biped's base prompt free of human-only pose instructions. */
export function buildVideoBasePrompt({direction, facing, pose, bodyPlan, equipment}: VideoBaseSettings): string {
  const biped = !bodyPlan.trim() || bodyPlan.split(';').every(spec => spec.trim().split('=').at(-1)?.trim().toLowerCase() === 'biped');
  const anatomy = BODY_PLANS.find(plan => plan.value === bodyPlan.trim().toLowerCase());
  const side = facing === 'right' ? '오른쪽' : '왼쪽';
  const views: Record<string, string> = {
    side: `정확한 측면에서 본 모습. 몸과 얼굴, 발끝 모두 ${side}을 향한다.`,
    front: '정확한 정면. 머리·가슴·골반·양발 끝이 모두 관찰자를 향하고 얼굴은 양 귀 가운데에 둔다. 참조 그림의 측면 각도를 따르지 않는다.',
    back: '정확한 뒷면. 머리·어깨·골반을 완전히 뒤로 돌리고 뒤통수·등·양발 뒤꿈치가 관찰자를 향한다. 얼굴이 보이거나 고개만 돌아보지 않는다.',
    front_diagonal: `앞 대각선 45도. 몸과 머리를 함께 ${side}으로 돌리고 가슴과 얼굴이 같은 방향을 본다. 발끝은 화면 아래 ${side} 대각선을 향한다.`,
    back_diagonal: `뒤 대각선 45도. 몸과 머리를 화면 위 ${side}으로 함께 돌린다. 얼굴을 숨기고 뒤돌아보지 않는다. 발끝은 화면 위 ${side} 대각선을 향하며 신발 뒤쪽이 보인다.`,
  };
  return [
    '영상 시작용 2D 게임 캐릭터 그림 한 장. 선택한 참조의 외형·의상·색·머리·신체 비율·화풍을 유지한다.',
    biped ? views[direction] : `${VIDEO_DIRECTIONS.find(view => view.id === direction)?.label}. 몸 전체가 같은 보기 방향을 유지한다.${['side', 'front_diagonal', 'back_diagonal'].includes(direction) ? ` 몸 전체는 ${side}을 향한다.` : ''}`,
    !biped ? `신체 구조: ${bodyPlan.trim()}. ${anatomy?.imageText ?? '각 대상은 지정한 구조와 지지 방식을 유지하고 없는 팔다리를 만들지 않는다.'} ${pose === 'walk' ? '자신의 구조에 맞는 자연스러운 이동 중간 자세.' : '자신의 구조에 맞는 편안한 대기 자세.'}` : pose === 'walk'
      ? '걷기의 중간 걸음 자세. 한 발은 자기 골반 바로 아래에 평평하게 딛고, 다른 발은 자기 골반 아래에서 무릎을 조금 굽혀 살짝 든다. 두 다리는 골반 너비로 떨어지고 사이에 빈틈이 보인다. 어깨와 골반은 선택한 방향을 유지하고 팔은 다리와 반대로 작게 움직인다.'
      : '두 발을 지면에 둔 편안한 대기 자세. 몸 전체가 선택한 방향을 유지한다.',
    '장비의 좌우 및 부착 방식을 유지한다. 눈높이 시점에서 전신을 가운데 두고 몸이나 장비가 잘리지 않도록 사방에 여백을 둔다. 시트·분할 칸·글자 없이 한 자세만 그린다.',
    '평면적인 2D 도트 화풍과 선명한 픽셀을 유지한다. 3D 렌더링과 입체 조명 효과를 사용하지 않는다. 광채·후광·입자·마법 효과·잔상·바닥 그림자를 제외한다. 구슬이 있는 장비는 구슬을 효과 없는 단색 구체로 그린다.',
    equipment.trim() ? `장비 배치: ${equipment.trim()}. ${biped ? 'right는 캐릭터 자신의 오른손, left는 왼손이다. 보기 방향이 달라져도 장비를 반대 손으로 옮기지 않는다.' : 'right는 캐릭터 자신의 오른쪽, left는 왼쪽이다. 보기 방향이 달라져도 원래 부착 위치와 운반 방식을 유지하고 장비를 반대편으로 옮기지 않는다.'}` : '',
  ].filter(Boolean).join('\n');
}
