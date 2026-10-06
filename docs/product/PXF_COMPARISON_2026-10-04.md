# 이펙트 에디터와 스프라이트 에디터 기능 비교

2026-10-04 · 실제 구현과 제안을 구분한 검토. 대상 채팅은 [PXF 앱·설명서 고도화](codex://threads/01a1019e-b5a1-7b41-921e-90d8fc9b7ce0)다. 채팅의 설명뿐 아니라 두 프로젝트의 현재 소스를 대조했다.

**PXF의 강점은 AI가 만든 JSON을 제한된 엔진의 실행 가능한 제작 레시피로 사용하는 데 있다. 스프라이트 에디터에 가장 유용한 부분은 이 계약을 중심으로 한 편집·검증·변형 방식이다.** 현재 스프라이트도 JSON으로 정렬·재생·출력을 제어한다. 보완할 부분은 JSON의 도입 자체보다, 생성 조건과 편집 제안의 구조화 및 검증 경로의 통일이다.

다만 PXF가 생성하는 것은 도형·파티클·합성으로 계산하는 효과다. 스프라이트는 생성하거나 가져온 캐릭터 PNG를 사용한다. 이 차이 때문에 PXF에서 직접 계산할 수 있는 조건과 이미지 생성기에 요청해야 하는 조건의 보장 수준이 다르다.

## 실제 기능별 대조

아래의 ‘없음’은 조사한 현재 앱 구현에서 확인되지 않았다는 의미다. 핸드오프 문서의 향후 계획은 구현으로 계산하지 않았다.

| 기능 | PXF 이펙트 에디터 | 현재 스프라이트 에디터 | 판단 |
|---|---|---|---|
| 제작 데이터 | `settings/nodes/links/game`으로 효과 전체를 기술 | 원본 PNG와 `Frame/Group/Alignment/Clip/Occurrence`를 연결 | 둘 다 JSON 기반. PXF는 픽셀 생성식까지, 스프라이트는 이미지의 사용·보정 방법을 기술 |
| AI 제작 | 설명과 엔진 계약을 보내 새 그래프 JSON 생성. 파싱·정규화 후 미리보기 | 승인된 외형·스타일·포즈 참조와 설명을 보내 PNG 생성. 원본·요청·영수증 보존 | 생성 결과의 성격이 다름. JSON 형식으로 바꾼다고 PNG의 포즈가 엔진 계산으로 바뀌지는 않음 |
| AI로 기존 작업 수정 | 현재 그래프 입력·변경 diff·고정 조건 검사 미구현 | 선택 프레임 재생성 구현. 기존 슬롯 자동 교체는 하지 않음 | PXF의 대화형 수정은 계획. 현재 스프라이트가 이미 가진 단일 프레임 재생성을 중복 개발할 필요 없음 |
| 노드 편집 | 29종 노드, 추가·삭제·복제·포트 연결, 순환 방지, 위치 이동, 노드별 미리보기 | 후보와 재생 슬롯을 선택·추가·복제·교체·삭제 | 노드 UI 전체 이식의 이득은 낮음. 캐릭터 제작 흐름에는 슬롯 UI가 더 직접적 |
| 수치·색상 편집 | 노드 정의에 따라 숫자·선택값·색·팔레트·seed UI 제공 | 이동·배율·회전·기울기·반전·중심점, 픽셀 펜·알파 지우개, 테두리 | 필드 정의에서 UI와 validator를 연결하는 방식은 유용. PXF가 범용 픽셀 페인팅 앱인 것은 아님 |
| 시간 변화 | 숫자 파라미터 고정값, A→B 보간, 키프레임 목록, 이징 | 후보 이미지 배열과 슬롯별 `durationMs`, 기본 FPS 추종/개별 시간 | PXF는 수치 보간으로 새 프레임을 계산. 스프라이트의 슬롯 시간 조절과 목적이 다름 |
| 프레임 수 변경 | 기존 키프레임과 impactFrame을 새 구간에 재매핑 | 슬롯 추가·복제·제거로 실제 재생 순서를 변경 | PXF의 프레임 늘리기가 새 캐릭터 포즈 생성에 해당하지 않음 |
| 재생 | 균일 FPS. 단발 효과도 편집 미리보기에서는 550ms 쉬고 재시연 | 가변 슬롯 시간. 단발은 마지막 프레임 유지. 재생 속도·seek·겹쳐 보기 | 스프라이트의 시간 모델을 유지해야 함. PXF 미리보기 정책을 게임 재생 계약에 복사하면 안 됨 |
| 크기와 기준점 | 정사각 캔버스, 효과 좌표·Transform, 게임용 pivot/논리 크기 메타데이터 | 원본 기준 공통 배율·몸 기준점·발/공중 앵커·개별 오프셋·고정 셀 | 캐릭터 크기·접지 보정은 현재 스프라이트가 더 구체적. 이미 만든 정렬 기능을 유지 |
| 색·합성 효과 | Palette/Tint/Mask/Blend/Outline/Glow/Blur 등 그래프 연산 | 픽셀별 RGBA 보정과 팀 테두리. 범용 효과 노드망 없음 | 팔레트·효과 변형은 별도 확장 후보. 걷기 검수보다 우선할 이유는 약함 |
| 변형 후보 | 원본 그래프 복사로 2–24개 생성. seed·팔레트·수치 변동, 선택 적용·묶음 ZIP | 생성·추출 후보와 여러 동작은 보존하지만 변형안을 한 번에 만드는 전용 화면 없음 | 가장 직접적인 전이 대상. 순서·시간·정렬 설정의 여러 시안으로 바꾸어 적용 가능 |
| 후보 비교 | 변형 카드에 약 1/3 지점의 대표 프레임 표시 | 승인 기준 정지 이미지와 현재 동작을 나란히 비교 | 어느 쪽도 여러 동작의 동기화 A/B 재생을 완성한 상태는 아님 |
| 실행 취소 | 최대 80개 이전 그래프. 같은 group의 450ms 미만 입력 병합. 드래그는 종료 시 한 번 확정 | 초안 명령 단위 undo/redo. 저장은 명령별 ACK를 받아 남은 초안 보존 | 제스처·복수 명령을 하나로 묶는 방식은 유용. 저장·충돌 정책은 기존 스프라이트 구조에 맞춰야 함 |
| 임시 저장 | 출처별 localStorage. 재개 시 편집용 validator. 구형 키 fallback | 프로젝트별 `{base,commands}` localStorage, 서버 revision 충돌 표시 | PXF의 복원 시 검증을 참고할 가치가 큼. PXF도 범용 버전 migration 시스템은 아님 |
| 영구 이력·백업 | 현재 초안/그래프 파일/로컬 피드 저장. 생성 요청별 장기 기록은 미구현 | 프로젝트 revisions, 새 버전으로 복원, 복제, 원본 포함 백업, 생성 영수증·계보 | 이 영역은 스프라이트 기반이 더 충실. PXF 방식으로 교체할 필요 없음 |
| 자동 검사 | JSON 구조·허용 파라미터·그래프 참조·알려진 제한 그래프 fingerprint | 수정 명령·참조 무결성, 이미지 해시, 승인 버전, 알파·빈 프레임·overflow·출력 일치 | 검사 대상이 다름. 둘 다 검사 통과가 미적 완성도나 자연스러운 보행을 뜻하지 않음 |
| 사람의 검수 | 그래프 미리보기·선택 적용 | 외형·추출·앵커·동작 수동 승인, 변경 시 관련 승인 무효화 | 현재 검수 체계 유지. 미세 픽셀 차이 대신 주요 요소 누락·큰 스타일 변화·실제 재생을 확인 |
| 렌더 | DOM 없는 엔진을 Web Worker에서 실행. 전체 프레임 계산 후 재생에 사용 | 편집 JS Canvas, 확정 출력 Python renderer, 산출물 재생 RuntimePlayer | 완성 프레임 캐시와 렌더 입력 분리는 유용. Worker 이전은 실제 병목 측정 후 판단 |
| 파일 출력 | `.pxf.json`, PNG 가로/격자 시트, 메타데이터 ZIP, 프레임 PNG ZIP, 1–4배 | atlas, 슬롯 PNG ZIP, runtime/Aseprite JSON, QA·해시·계보, 프로젝트 백업 | 게임용 출력과 원본 추적은 현재 구조가 적합. PXF JSON만으로 sprite PNG를 대체할 수 없음 |
| JSON 가져오기 | AI 응답 붙여넣기·파일 가져오기·공통 parser/schema/rights 적용 | runtime/Aseprite 영역 가져오기, runtime 재생, 프로젝트 백업 복원 | 스프라이트의 영역 가져오기는 편집 프로젝트 전체 복원과 다름. AI 편집 레시피 import는 신규 기능 |
| 라이브러리 | 효과 피드/그리드·검색·프리셋 재편집·로컬 저장 | 캐릭터 프로젝트·동작·후보·생성/추출 이력·사용 슬롯 추적 | 프리셋 검색 UX는 참고 가능. 캐릭터 후보에 효과 커뮤니티 구조를 통째로 적용할 필요는 낮음 |
| 도움말 | 퀵스타트·상세 설명서·검색·스크린샷 확대·시간 계산·프롬프트 예제 | 퀵스타트·상세 설명서·검색·확대·실제 예제 재생·시간 실습·HTML ZIP | 상당 부분 중복. 새 도움말보다 보행 시안 비교·기준점 활용 사례 추가가 유용 |
| 실행 도구 | `.command`, 같은 앱 서버 재사용, 다른 포트 사용자 보존 | `.command`, API/worker 프로세스 관리·중복 실행 잠금 | 이미 양쪽에 있음. 재사용 UX의 차이만 개선 후보 |

핵심 구현 근거: PXF [노드 조작·프레임 재매핑·undo](/Users/cheng80/Desktop/Current_works/effect_editer/pxf-workshop/src/lib/native-graph.mjs:3), [속성 편집](/Users/cheng80/Desktop/Current_works/effect_editer/pxf-workshop/src/components/native-editor/inspector.tsx:63), [변형 생성](/Users/cheng80/Desktop/Current_works/effect_editer/pxf-workshop/src/lib/pxf-variations.mjs:6), [변형 화면](/Users/cheng80/Desktop/Current_works/effect_editer/pxf-workshop/src/components/native-editor/variations-dialog.tsx:39). 스프라이트 [편집 화면](/Users/cheng80/Desktop/Current_works/copy_spritegen/apps/web/src/AnimationWorkspace.tsx:217), [초안·저장](/Users/cheng80/Desktop/Current_works/copy_spritegen/apps/web/src/useStudio.ts:13), [기록·백업 UI](/Users/cheng80/Desktop/Current_works/copy_spritegen/apps/web/src/FinishSteps.tsx:106), [구현 통합 계약](/Users/cheng80/Desktop/Current_works/copy_spritegen/packages/contracts/IMPLEMENTATION.md:3).

29종 노드의 실제 범위도 구분할 필요가 있다. 아래는 이해를 위한 기능별 분류이며 앱의 내부 분류명은 아니다.

| 기능군 | 노드 | 실제 편집 의미 |
|---|---|---|
| 형태·텍스처 생성 | Shape, Noise, Gradient, Particles, Lightning, Arc, Spike, Checker, Grid, AuraShell, Revolve, Stroke | 도형·참격·번개·입자·패턴을 수치로 생성. Particles는 방출·수명·속도·중력·감속·바운스·자체 loop 등을 가짐 |
| 변형·반복·시간 잔상 | Transform, Repeat, Echo, Displace, Polar, Pixelate | 위치·형태·반복 배치를 바꾸거나 이전 프레임의 입력을 계산해 잔상 생성 |
| 필터·합성 | Blur, Glow, Levels, Dither, Blend, Mask | 흐림·발광·강도·디더링·합성·마스크를 연결 순서대로 적용 |
| 색·윤곽·출력 | Palette, Tint, Outline, Quantize, Output | 강도→색 대응, 색 보정, 윤곽선, 허용색으로 양자화, hard/soft 알파 출력 |

Palette의 `smooth`는 선언한 색 사이의 색도 만들며, 최종 허용색 집합을 제한하려면 Quantize 같은 연산의 위치까지 정해야 한다. PXF Outline은 형태학적 윤곽 계산이고 현재 스프라이트의 팀 테두리는 실루엣 복제 합성이므로, 이름이 같아도 결과는 같지 않다. 노드 썸네일·선택 노드 미리보기는 중간 단계 확인에 유용하지만 최종 Output의 알파 처리와 다를 수 있다. [엔진 정의·평가](/Users/cheng80/Desktop/Current_works/effect_editer/pxf-workshop/public/pxf/engine.mjs:146), [스프라이트 테두리](/Users/cheng80/Desktop/Current_works/copy_spritegen/alignment/pipeline.py:298).

## JSON이 실제로 수행하는 역할

### PXF: 생성·편집·렌더가 같은 그래프 계약을 사용한다

실제 처리 흐름은 다음과 같다.

1. 앱의 공개 프롬프트에 노드 종류, 입력 포트, 파라미터 타입·기본값·범위, 시간 표현, 예제 JSON을 포함한다.
2. 사용자의 효과 설명을 붙여 모델에 보내고 JSON 텍스트를 받는다.
3. `parseGraphText`가 일반 JSON 또는 단일 JSON 코드 블록을 읽는다. 임의 설명문을 분석해 그래프를 추측하지 않는다.
4. `normalizeGraph`가 엔진의 `PXF.DEFS`를 사용하여 허용된 데이터만 새 객체로 구성한다. 누락값에는 기본값을 넣고 범위·연결 등을 검사한다.
5. 알려진 제한 그래프의 fingerprint와 비교한다. 이것은 등록된 표본 일치 검사이며 모든 작품의 권리·독창성을 증명하는 기능이 아니다.
6. 미리보기 Worker가 다시 정규화한 뒤 같은 엔진으로 픽셀을 계산한다.
7. 사용자가 결과를 적용하면 그 그래프가 편집 상태가 되고, 속성 UI와 내보내기가 같은 데이터를 사용한다.

여기서 `schema.mjs`는 직접 작성된 JavaScript validator/normalizer다. **검토한 생성 요청에는 모델 공급자의 strict JSON Schema 출력 옵션이 없다.** 프롬프트로 계약을 알려주고 받은 응답을 로컬 코드로 검증한다. JSON을 요청했다는 사실만으로 모델의 모든 응답이 처음부터 유효해지는 구조는 아니다. 실패하면 오류를 반환하며 자동으로 유료 재생성을 반복하지 않는다.

schema와 속성 UI는 엔진 정의를 참조하지만, 생성 프롬프트는 정적 텍스트다. 따라서 노드 규격이 바뀔 때 프롬프트까지 자동으로 갱신되는 단일 규격 생성 파이프라인이 이미 완성됐다고 볼 수는 없다.

근거: [제작 프롬프트](/Users/cheng80/Desktop/Current_works/effect_editer/pxf-workshop/public/pxf/claude-prompt.txt:1), [응답 parser](/Users/cheng80/Desktop/Current_works/effect_editer/pxf-workshop/public/pxf/import.mjs:1), [실제 생성 요청·검증](/Users/cheng80/Desktop/Current_works/effect_editer/pxf-workshop/src/lib/server/ai-generation.mjs:214), [클라이언트 공통 검증](/Users/cheng80/Desktop/Current_works/effect_editer/pxf-workshop/src/lib/client.ts:13), [fingerprint 검사](/Users/cheng80/Desktop/Current_works/effect_editer/pxf-workshop/public/pxf/rights.mjs:15).

이 방식의 효과는 **허용된 부품과 숫자로 설계하게 한 뒤, 실행 가능한지 검증하고, 엔진이 실제로 계산한다**는 연결에서 나온다. 단순히 자유 문장을 JSON 필드 안에 넣는 것보다 훨씬 강한 제어가 가능하다.

### 코드로 강제되는 조건과 지침으로 남는 조건

| 조건 | PXF의 실제 처리 | 보장 범위 |
|---|---|---|
| 캔버스 크기 | 32·48·64·96·128 중 하나로 검사 | 최종 그래프가 선택한 정사각 크기로 계산됨 |
| 프레임 수·FPS | 프레임 1–32 정수, FPS 1–60, loop boolean 검사 | 지정 개수와 재생 설정. 서로 다른 자세나 자연스러운 리듬은 별도 |
| 입력 크기 | JSON 256KiB, 노드 64·연결 128, 키프레임 64 등 제한 | 과도한 구조를 거부. 모든 허용 그래프가 빠르게 렌더된다는 보장은 아님 |
| 노드·연결 | 알려진 종류·중복 없는 ID·유효 포트·포트당 한 연결·순환 금지·Output 하나 및 입력 연결 | 실행 가능한 연결 관계 |
| 파라미터 | 정의된 필드만 유지, 선택값·색 형식·수치 범위 검사, 기본값 보충 | 허용된 연산 범위. 계약 밖 값을 자동으로 의미 있게 구현하지 않음 |
| 키프레임·보간 | 프레임 범위·중복·순서, A/B 값, `0 ≤ t0 ≤ t1 ≤ 1` 검사 | 수치 시간표의 유효성. 기대한 동작인지 여부는 시각 검수 |
| 고정 seed | 노드에서 난수 계산의 입력으로 사용 | 같은 엔진·정규화 그래프·프레임의 재현성. 새로운 후보 묶음의 재생성까지 자동 보장하지 않음 |
| `game.pivot/logicalSize` | 허용 범위 검사·메타데이터 저장 | 게임 배치 정보. 효과가 프리뷰 안에서 자동으로 재정렬되는 기능은 아님 |
| 자연스러운 반복 | `loop`에 따라 시간 평가. 프롬프트에서 경계 연결을 지시 | 루프 경계의 형태·밝기 연속성을 판정하는 자동 품질 검사는 미구현 |
| 단발의 끝 소멸 | 프롬프트가 마지막 프레임의 완전 투명을 지시 | JSON validator가 마지막 픽셀 알파를 검사하거나 소멸 노드를 강제하지 않음 |
| 가독성·좋은 실루엣·색 조화 | 프롬프트에 제작 기준 기재 | 구조 검사로 보장하지 않음 |
| 요청한 조건 고정 | 새 그래프가 전역 허용 범위인지 검사 | ‘기존 작업의 크기를 유지’ 같은 원본 대비 잠금 검사는 현재 AI 수정 기능에 없음 |

근거: [schema의 상한·파라미터 검사](/Users/cheng80/Desktop/Current_works/effect_editer/pxf-workshop/public/pxf/schema.mjs:3), [그래프 정규화](/Users/cheng80/Desktop/Current_works/effect_editer/pxf-workshop/public/pxf/schema.mjs:69), [품질 지침](/Users/cheng80/Desktop/Current_works/effect_editer/pxf-workshop/public/pxf/claude-prompt.txt:21).

정규화는 모든 잘못된 입력을 거부하는 방식도 아니다. 알려지지 않은 legacy 파라미터는 버리고, 알려지지 않은 이징은 `linear`로 보정한다. 프롬프트는 정수 파라미터를 정수로 요구하지만 공통 파라미터 validator는 수치 범위를 검사하고 실제 엔진이 `int/seed`를 반올림한다. 따라서 ‘프롬프트에 적힌 제약’과 ‘validator가 거부하는 조건’도 구분해야 한다. 이식 시 현재 사용자 데이터가 조용히 달라지지 않도록 보정 내역을 보여주는 편이 좋다.

입력의 잘못된 `format`도 현재 정규화 과정에서 `pxf.graph@1`로 바뀌며 버전 불일치 오류가 되지 않는다. 모든 노드를 Output 경로에 연결하라는 프롬프트 지침과 달리 미연결 노드도 허용된다. 이 역시 정규화 통과를 요청 의도 보존으로 해석하면 안 되는 이유다.

### 숫자 하나가 실제 그림으로 이어지는 예

다음은 현재 PXF에서 사용하는 애니메이션 값의 형식이다. 실제 생성 결과가 아니라 코드 계약을 설명하기 위한 예다.

```json
{
  "opacity": {
    "a": 1,
    "b": 0,
    "e": "in",
    "t0": 0.5,
    "t1": 1
  }
}
```

이 값을 지원하는 노드에 넣으면 엔진이 재생 후반의 불투명도를 계산한다. 반면 `{ "mustAlternateFeet": true }`라는 필드를 PNG 생성 요청에 추가하는 것만으로는 반대발 포즈가 계산되지 않는다. 그것을 해석하는 생성·검사·수정 기능이 따로 있어야 한다.

`{ "k": [[0, 3, "out3"], [8, 20, "linear"], [23, 26]] }`도 동일하다. PXF는 수치 값을 보간한다. 기존 캐릭터 PNG에서 가려진 다리의 새 형태를 복원하는 관절 리그·이미지 변형 엔진은 현재 29종 노드에 없다. PNG 입력 노드도 현재 계약에 없다.

## 스프라이트의 기존 JSON은 어디까지 제어하는가

현재도 상당 부분이 실행 가능한 계약이다.

| 현재 데이터·명령 | 실제 적용 | 부족하거나 별도인 부분 |
|---|---|---|
| `Reference.fixedTraits/allowedChanges/forbiddenTransfers` | 생성 프롬프트에 참조 역할과 함께 전달 | 대부분 자유 문자열. 생성된 장비·스타일·보행을 자동 보증하는 규칙은 아님 |
| `Group.sharedScale/bodyMeasurement/cell/targetAnchor` | 공통 배율·셀·앵커에 따라 실제 픽셀 배치. 몸 기준점 모드에서는 목표 체고로 배율 산출 | 보정 전 크기가 다른 이유로 후보를 버릴 필요 없음. 승인된 기준점을 사용하는 기존 방식 유지 |
| `Alignment.sourceAnchor/contactMode/rootAnchor` | 접지/공중 기준과 오프셋 적용, 관련 버전 검사 | 앵커가 해부학적으로 맞는지는 사용자의 검수·교정 대상 |
| `reorderOccurrences` | 해당 동작의 모든 슬롯 ID를 중복 없이 지정하는지 검사하고 실제 순서 변경 | 순서만으로 없는 포즈를 만들 수 없음. 반대발 후보가 있으면 먼저 조합을 시험할 수 있음 |
| `setTiming` | 1–60000ms 정수, FPS 추종 또는 개별 시간 적용 | 자연스러운 가속·접지 시간은 재생 검수 |
| `setTransform/setPixelEdits` | 허용 필드·범위 검사 후 선택 슬롯에 비파괴 편집 | 의상/무기 의미를 이해하고 자동 보존하는 제약은 아님 |
| `expectedRevision`, 자산 hash, 버전 ID | 오래된 저장 요청·다른 입력·누락 참조를 감지 | 향후 AI 제안을 적용할 때는 서버 revision 외 미저장 초안 변경도 확인해야 함 |
| `runtime.json/qa.json/recipeHash` | 출력 배치·앵커·시간·출처·검사 결과·렌더 조건 기록 | JSON만 분리해도 원본 PNG가 복구되는 것은 아님. 백업은 이미지도 포함 |

근거: [생성 요청 검증·프롬프트](/Users/cheng80/Desktop/Current_works/copy_spritegen/adapters/spritegen/provider.py:126), [편집 명령 타입](/Users/cheng80/Desktop/Current_works/copy_spritegen/services/api/edits.py:7), [순서·시간·변형 검사](/Users/cheng80/Desktop/Current_works/copy_spritegen/services/api/edits.py:107), [공통 배율·앵커](/Users/cheng80/Desktop/Current_works/copy_spritegen/services/api/edits.py:138), [출력 레시피](/Users/cheng80/Desktop/Current_works/copy_spritegen/alignment/pipeline.py:609).

현재 생성 adapter는 참조 PNG의 SHA-256과 실제 전달 프롬프트를 `request-snapshot.json`에 기록한다. 결과에는 요청 프레임 수와 반환 이미지 수를 따로 보관하고 `actualFrameCount`는 추정해 채우지 않는다. 투명도도 요청값을 믿지 않고 실제 PNG 알파를 측정한다. 이 구분은 유지해야 한다. ‘8프레임을 요청한 JSON’은 ‘8개의 유효한 보행 포즈를 얻었다’는 증거가 아니다. [실제 요청·영수증 기록](/Users/cheng80/Desktop/Current_works/copy_spritegen/adapters/spritegen/provider.py:267).

## 유용하게 가져올 기능과 필요한 수정

**1. 허용된 편집 명령으로 JSON 제안을 받는 기능 — 효과가 가장 직접적이다.**

PXF처럼 모든 것을 새로 설계하기보다, 현재 스프라이트의 `Operation`을 재사용하는 편이 단순하다. 기존 후보를 유지한 채 순서·표시 시간·허용된 정렬 설정만 바꾸는 JSON 시안을 만들고, 임시 상태에서 렌더해 비교한 뒤 적용한다.

예를 들어 기존 슬롯만 대상으로 하는 아래 구조는 현재 편집 API의 형태다. ID와 revision은 설명용이며 실제 프로젝트에 맞는 값으로 치환해야 한다.

```json
{
  "expectedRevision": 25,
  "operations": [
    {
      "type": "reorderOccurrences",
      "clipId": "existing-clip-id",
      "occurrenceIds": ["slot-1", "slot-3", "slot-2", "slot-4"]
    },
    {
      "type": "setTiming",
      "clipId": "existing-clip-id",
      "occurrenceId": "slot-3",
      "durationMs": 125,
      "timingMode": "explicit"
    }
  ]
}
```

현재 API는 복수 명령을 transaction 안에서 적용할 수 있다. 다만 프런트는 로컬 임시 ID를 서버 ID로 치환하기 위해 명령별로 저장한다. 기존 ID의 순서·시간 변경부터 묶는 것은 비교적 작고, 새 동작·새 슬롯 생성까지 한 번에 묶으려면 임시 ID 해소 계약이 필요하다. 이를 구분하지 않고 ‘배열로 보내면 모두 해결된다’고 보면 안 된다.

AI가 임의의 프로젝트 전체 JSON이나 승인 상태를 덮어쓰게 할 필요는 없다. 제안에 사용할 명령의 부분집합을 정하고, 허용 필드·ID·잠금 조건 검사 후 기존 `applyDraft` 경로로 미리보기하면 된다. 이 제안 화면은 **현재 미구현**이며 PXF에도 전후 수정 diff는 계획 단계다.

**2. 생성·검수 조건을 구조화하되, 실행 규칙과 시각 판단을 구분한다.**

추가할 제약은 다음처럼 나누는 것이 적합하다. 아래는 제안이며 현재 지원되는 새 API 필드라고 해석하면 안 된다.

| 제약 종류 | 예 | 처리 방법 |
|---|---|---|
| 입력 고정 | 승인 Idle reference ID·hash, 사용할 후보 목록, 정렬 group revision | 실행 전 코드로 검사. 변경되면 재검토 |
| 편집 범위 | 순서·시간만 변경, 원본 자산·승인된 기준·공통 배율은 유지 | 제안 operations의 허용 필드 검사와 적용 전후 값 대조 |
| 출력 수치 | 셀 크기·nearest·앵커 좌표·슬롯 수·시간 범위 | 기존 renderer·validator가 직접 적용 |
| 시각 기준 | 머리·스카프·견갑·검·부츠 등 주요 요소 유지, 전반적인 스타일 호환 | 항목별 관찰 근거와 수동 확인. 미세 픽셀·명암 차이는 허용 |
| 동작 기준 | 양쪽 다리의 지지/스윙 후보 확인, 발 회수·접지·반복 이음새 | 프레임 관찰과 전체 재생을 별도로 확인. 모호한 항목은 `unknown` 보존 |

구조화된 제약이 있으면 생성 프롬프트, 검수 체크리스트, 비교 화면이 같은 항목을 공유할 수 있다. 그러나 모델이 JSON으로 `passed: true`를 반환한 것만으로 그림이 조건을 충족했다고 간주하면 안 된다. 관찰 이미지·영역·판단 주체·확신도를 기록하고 사람이 정정할 수 있어야 한다.

이번 보행 작업에서도 축소 이미지의 일괄 `unknown` 때문에 반대발 후보 조합을 놓쳤고, 원본을 재검토해 A4/A8과 B3/B4의 서로 다른 스윙 후보를 확인했다. 이 경험에 비춰 고정 8단계 라벨을 강제로 채우거나 `unknown`을 불합격으로 바꾸는 규칙은 부적절하다. [기존 실험과 교정 기록](/Users/cheng80/Desktop/Current_works/copy_spritegen/docs/product/WALK_EXPERIMENT_2026-10-04.md:5).

**3. 변형 후보 기능은 ‘여러 보행 편집안’으로 바꾸면 유용하다.**

PXF의 변형은 AI 재호출 없이 그래프의 seed·팔레트·수치를 바꾸는 로컬 기능이다. 스프라이트에서는 후보 PNG를 복제 생성하는 대신, 같은 후보를 참조하는 순서·시간 레시피 A/B/C를 만들 수 있다. 원본 후보와 기존 동작을 보존하면서 반대발 후보를 넣은 시안·접지 시간을 바꾼 시안을 비교하는 방식이다.

PXF의 현재 비교는 정지 카드이므로, 보행 검수에 필요한 동기 재생은 추가 구현이다. 두 모드를 구분해야 한다. 실제 속도 비교는 같은 경과 시간으로 재생하고, 주기가 다른 시안의 포즈 비교는 정규화된 주기를 사용한다. 이 비교를 위해 원본 `durationMs`를 수정해서는 안 된다. 적용과 undo는 시안 전체를 한 번에 처리하는 편이 좋다.

**4. 계약에서 편집 UI·프롬프트·검사를 연결하는 방식을 참고한다.**

PXF는 `PXF.DEFS`에 필드 타입·범위·기본값·옵션을 갖고, schema와 inspector가 이를 활용한다. 반면 현재 스프라이트의 TypeScript `Operation`은 열린 형태이고 서버는 Pydantic 명령과 수동 필드 검사를 사용하며, 일부 내부 dict 검증은 호출 지점에 흩어져 있다.

PXF의 수치 상한을 가져오는 대신 기존 스프라이트 계약을 명시적인 판별 union/공통 필드 규격으로 정리하는 것이 유용하다. 실제 서버 검증을 정본으로 유지하면서 생성 프롬프트·입력 UI·JSON import가 같은 의미를 쓰도록 해야 한다. 임의 JSON Schema 도입만으로 UI/서버의 의미 차이가 없어지지는 않는다.

**5. 복원 검증·undo 묶기는 제작 안정성에 도움이 된다.**

PXF의 출처별 초안과 복원 시 검증, 드래그 종료 시 한 번 확정하는 방식을 적용할 가치가 있다. 현재 스프라이트는 저장된 초안의 JSON 문법만 파싱하고 내부 구조를 신뢰한다. 버전·프로젝트 일치와 명령 형태를 검사한 뒤 복원하고, 손상된 초안은 별도로 보존한 채 서버 상태를 열 수 있어야 한다.

연속 수치 조작은 같은 대상·같은 필드·같은 제스처 안에서 묶고, 여러 슬롯을 바꾸는 시안은 한 작업 단위로 묶는다. PXF의 450ms/80개를 그대로 가져오기보다, 스프라이트의 명령 크기·저장 ACK·충돌 복구와 맞춰야 한다. 저장된 과거 버전을 되돌리는 기능과 미저장 초안 undo는 계속 구분한다.

**6. 렌더와 출력은 캐시·공통 입력·검증 경로를 차용한다.**

PXF는 이름·노드 배치·FPS처럼 픽셀 자체를 바꾸지 않는 값과 렌더 입력을 구분한다. 이미 계산한 프레임을 재생에 사용한다. 현재 스프라이트는 이미지 디코딩 캐시가 있지만 슬롯 표시 때 정렬·변형·테두리를 다시 합성한다. 픽셀 결과 캐시를 추가할 여지가 있다.

캐시는 자산 hash, 정렬·배율·앵커, 변형, 픽셀 수정, 테두리, renderer 버전으로 구분해야 한다. 현재 슬롯과 이웃부터 캐시하고 메모리 상한을 둔다. PXF의 작은 128px·32프레임 전체 선계산을 큰 raster 프로젝트에 그대로 적용하면 메모리 비용이 달라진다. Worker의 성능 우위는 이번에 측정하지 않았으므로 우선 도입 근거로 삼지 않는다.

PXF의 Output 미리보기와 내보내기는 동일 계산 엔진을 사용한다. 현재 스프라이트의 편집 Canvas와 최종 Python 출력은 다른 경로이고, 확정 산출물 미리보기는 실제 atlas를 재생한다. 현재 `fullRGBAParity`는 최종 렌더·atlas·PNG의 일치이며 편집 Canvas까지 증명하지 않는다. 같은 입력에 대한 두 렌더러의 동등성 검증은 유용하다. 이는 **출력 파이프라인의 정확성 검사**이며, Idle과 보행의 픽셀 동일성을 요구하는 외형 검수와는 목적이 다르다.

근거: [PXF 렌더 입력·프레임 재사용](/Users/cheng80/Desktop/Current_works/effect_editer/pxf-workshop/src/components/native-editor/native-editor.tsx:158), [Worker 결과 검사](/Users/cheng80/Desktop/Current_works/effect_editer/pxf-workshop/src/lib/pxf-render.ts:6), [현재 Canvas renderer](/Users/cheng80/Desktop/Current_works/copy_spritegen/apps/web/src/render.ts:2), [출력 RGBA 대조](/Users/cheng80/Desktop/Current_works/copy_spritegen/alignment/pipeline.py:635).

## 현재 PXF에 없는 기능과 이식하지 않을 항목

현재 그래프를 보내는 대화형 AI 수정, 전후 구조 diff, 원본 대비 고정 조건 확인, 장기 생성 버전 기록, 빈 결과·잘림·루프 경계 자동 품질 진단, 앱 이벤트와 연결된 단계별 튜토리얼은 핸드오프의 후속 계획이다. 노드별 키프레임 목록은 있지만 전체 시각 타임라인·곡선 편집기·어니언스킨과 다중 노드 선택/그룹/미니맵은 현재 완성 기능으로 확인되지 않았다. [실제 한계·후속 계획](/Users/cheng80/Desktop/Current_works/effect_editer/pxf-workshop/docs/handoff-app-guide-2026-10-03.md:79).

다음은 도입 우선순위가 낮거나 목적이 다른 항목이다.

- PXF 노드 그래프 전체로 캐릭터 에디터를 재작성: 현재 PNG·정렬·슬롯·원본 계보와 맞지 않는다. 향후 참격·잔상 같은 별도 효과 제작에는 가치가 있을 수 있다.
- A→B 수치 보간으로 반대발 포즈를 보충: 현재 엔진에는 캐릭터 관절·가림을 복원하는 기능이 없다.
- PXF 팔레트 변경을 캐릭터 전체에 자동 적용: 장비·의상색 구분을 잃을 수 있다. 영역/색 대응이 정의된 별도 편집 기능으로 검토해야 한다.
- 효과용 프레임·캔버스 상한, 단발 재시연 정책, fingerprint 제한 목록의 복사: 각 앱의 도메인·출력 계약이 다르다.
- 생성 연결·OAuth 구현의 교체: 기존 스프라이트 생성 경로와 무관한 변경이다. JSON 명령 검증과 로컬 비교에 별도 제공자 도입은 필수가 아니다.
- 설명서·백업·생성 이력의 중복 개발: 현재 스프라이트 구현을 먼저 활용하는 편이 낫다.

## 적용 순서와 완료 판단

검토에 따른 제안이며 이번에 앱 기능을 구현한 것은 아니다.

| 순서 | 작업 범위 | 완료를 판단할 구체적인 결과 |
|---|---|---|
| 1 | 기존 후보·슬롯 ID로 순서·시간 편집안 JSON 생성/가져오기, validator, 임시 비교 | 같은 원본으로 여러 시안을 재생. 잘못된 ID·누락/중복 슬롯·금지 변경 거부. 원본 유지 |
| 2 | 시안 단위 적용·undo, 적용 대상 버전/초안 확인 | 선택한 시안만 반영되고 undo 한 번으로 돌아감. 생성 중 편집된 원본에 구형 시안 자동 적용 금지 |
| 3 | 외형·동작 제약과 관찰 기록 구조화 | 주요 요소 누락·큰 스타일 변화와 경미한 차이를 구분. `unknown` 후보도 비교 가능. 사용자 정정 보존 |
| 4 | 공통 필드 계약·초안 복원 검증·렌더 캐시 | UI/서버/import의 같은 입력 해석, 손상 초안 복구, 동일 픽셀 유지 및 합성 횟수 측정 |
| 5 | 부족한 포즈의 선택 재생성 연결 | 순서·시간 비교 후 구체적으로 부족한 포즈만 요청. 생성된 후보를 기존 원본과 비교 후 채택 |

효과 평가는 스키마 통과율만으로 하지 않는다. 같은 생성 원본에서 사용 가능한 동작을 만드는 데 필요한 수동 편집 수, 시안 비교 시간, 추가 이미지 생성 횟수, 되돌리기·원본 복구 가능 여부를 함께 본다.

## 검토 근거와 실제 검증 범위

- 참조 채팅의 두 턴과 핸드오프를 읽고 현재 구현과 구분했다. 해당 채팅의 첫 제안은 코드 변경을 수행한 결과가 아니었다.
- PXF 기준 HEAD: `bac0ff79a2b898ffaa51b13e7bd16e3ad3d011b1`. 사용자 작업 트리의 README·핸드오프·launcher 변경을 포함하여 읽었으며 수정하지 않았다.
- 스프라이트 기준 HEAD: `33f06b09a20de7f79ed2b0c682f16f9b73fbdc4a`. 기존 보행 실험·cutout 변경은 보존했다.
- 생성 요청, validator, 편집 상태, renderer, 출력, 이력, 도움말, launcher 소스를 대조했다. Node에서 실제 `PXF.DEFS`를 불러 29종 노드를 확인했다.
- 별도 조사에서 공개 parser/schema/engine을 불러 메모리 안의 작은 fixture로 아래 기능을 실행 확인했다. 직접 작성한 계약 검증 입력이며 GPT 생성 이미지나 사용자 원본을 사용한 검수가 아니다.
- 테스트 소스는 근거로 읽었다. 기존 문서의 테스트 통과 수·실제 생성 성공 기록을 이번 실행 결과로 취급하지 않는다. 전체 테스트·빌드·브라우저 UI·성능 벤치마크·외부 AI 생성은 이번 검토에서 실행하지 않았다.
- 검토 문서와 조사 자료만 작성했다. 두 앱의 구현 코드·프로젝트 데이터·원본 이미지·실행 서버는 변경하지 않았다.

| 이번 로컬 실행 | 확인한 결과 |
|---|---|
| 32px·8프레임 그래프의 렌더 | 각 프레임 4096바이트 RGBA, 8프레임 반환 |
| size=33, frames=33, fps=0, loop 문자열 | 각각 schema 거부 |
| 정적 Shape→Palette→Output, loop=false | 마지막 프레임에도 가시 픽셀 448개. 첫/끝 RGBA 동일 |
| 입력 없는 Tint→Output | schema 통과하지만 두 프레임 모두 가시 픽셀 0 |
| Noise의 같은 seed·frame, JSON 재파싱/새 evaluator/cache clear | fixture의 RGBA 일치 |
| 같은 프레임에서 FPS만 12→60 | RGBA 동일. FPS는 표시 시간에 작용 |
| 8프레임 A=0→B=1 선형 보간의 마지막 샘플 | non-loop는 1, loop는 0.875. loop가 시간 샘플 규칙을 바꿈 |
| red/blue 두 색의 smooth Palette와 falloff | 선언한 두 색 이외 RGB의 가시 픽셀 368개. 최종 색 집합 제한과 구분 필요 |

Worker handler는 메모리 shim으로 실행했으며 실제 브라우저 Worker 스케줄링·전송 성능을 측정한 결과는 아니다. 재현성 확인도 해당 fixture·로컬 엔진 범위이며 모든 브라우저·PNG/ZIP 인코더의 바이트 동일성을 뜻하지 않는다.

추가 근거: [기능별 소스 조사](/Users/cheng80/Desktop/Current_works/copy_spritegen/.data/reviews/pxf-transfer-20261004/source-audit.md), [렌더·출력 조사](/Users/cheng80/Desktop/Current_works/copy_spritegen/.data/reviews/pxf-transfer-20261004/render-audit.md).
