# AI 스프라이트 에디터 — 구현 가능성 및 핵심 연결 설계

> 2026-10-06 자료 정리: 아래 조사·실험의 원본, 비교 결과와 전용 스크립트는 사용자 요청으로 삭제했다. 제품 결정·구현 기록은 보존하며 과거 경로를 현재 실행 가능한 자료로 해석하지 않는다.

2026-10-04 KST · 착수 전 설계 기록. 이후 웹 기능 연결은 [영상 에디터 구현 결과](VIDEO_EDITOR_INTEGRATION_2026-10-04.md)를 따른다.

후속 실측: Grok Build 재로그인 후 **실제 영상 1건 → 투명 73프레임 → 28프레임 반복 시트·GIF**까지 확인했다. 인증·요청 횟수·검증 범위는 Grok 로그인 영상 제작 실측 (리서치 정리로 삭제)에 기록했다. 아래 오프라인 테스트 절은 이 실측 이전의 검증 기록이다.

## 판단

**현재 코드에 Grok 영상 생성과 영상 후처리를 연결하여 같은 종류의 AI 스프라이트 제작·편집 흐름을 구현할 수 있다.** 재사용할 엔진과 편집기가 모두 있다. 다만 실제 서비스와 같은 성공률·자연스러움은 코드만으로 확정할 수 없고, 같은 기준 캐릭터를 사용한 실제 생성·편집·출력으로 확인해야 한다.

현재 목표는 로그인·회원·크레딧 판매·결제·공개 배포가 아니다. 다음 흐름을 로컬 에디터에서 완주하는 것이다.

`기준 그림 → 동작·방향 지정 → Grok 영상 → 투명 프레임 → 구간 선택·정렬 → 편집·검수 → 게임용 출력`

기존 웹 역기획 (리서치 정리로 삭제)의 인증·과금 분석은 참고 자료로 남긴다. 그 기능의 구현이나 대상 웹사이트 로그인을 에디터 개발의 선행 조건으로 삼지 않는다.

## Grok을 API로 붙인 서비스인가

서비스의 공개 표시에는 영상 공급자가 **xAI Grok Imagine Video**이고, 개인정보 안내에는 생성 작업 실행이 Modal, 스틸·영상 생성이 xAI라고 명시돼 있다. 공개 엔진의 실제 코드도 `https://api.x.ai/v1/videos/generations`에 POST하고 `GET /videos/{request_id}`로 결과를 확인한다. 웹 서버에서 영상 API를 호출하는 구조라는 판단을 뒷받침한다.

다만 대상 서비스의 서버 소스와 개별 생성 요청은 확보하지 않았으므로, 실제 운영 인증 경로·모델 ID·옵션별 매핑까지 확인했다고 표현하지 않는다. 공개 엔진은 구독 로그인과 `XAI_API_KEY` 두 경로를 지원한다. 이 사실만으로 운영 서비스가 어느 인증 경로를 쓴다고 단정할 수는 없다.

공식 API 문서도 비동기 영상 생성과 첫/마지막 프레임 지정을 지원한다. 첫·끝 그림을 지정하는 것은 영상 구간을 제어하는 수단이며, 그 사이의 보행이나 장비 유지까지 보장하는 기능은 아니다. [xAI 영상 생성](https://docs.x.ai/developers/model-capabilities/video/generation), [첫·마지막 프레임](https://docs.x.ai/developers/model-capabilities/video/reference-to-video)

## 이미 있는 것과 빠진 연결

| 구성 | 현재 확인한 구현 | 필요한 연결 |
| --- | --- | --- |
| 영상 API | `engine/sprite-gen/sprite_gen/gen/video.py`의 `generate_video`, request ID 폴링, MP4 파일 검사 | 웹용 영상 어댑터·명시적 인증 경로·중단 후 조회 재개 |
| 영상용 입력 | `video/canvas.py`의 동작별 여백 | 승인 기준 그림을 동작용 캔버스로 준비하고 원본과 구분 |
| 영상 후처리 | `video/frames.py`, `video/loop.py` | worker에서 실행하고 추출 프레임·시간·구간을 앱 데이터로 등록 |
| 이미지 생성 | `adapters/spritegen/provider.py`의 Codex 경로 | 유지. 필요할 때 스틸 재생성과 영상 요청을 별도 작업으로 연결 |
| 작업 실행 | `services/worker/main.py`, `task.py` | 영상 단계·request ID·부분 완료 상태·외부 접수 불명을 처리 |
| 저장 | 프로젝트 snapshot, immutable PNG asset, frame/group/clip | 원본 MP4 artifact와 PNG 프레임의 연결·프레임 시각·보간 출처 |
| 후편집 | 공통 배율·앵커·순서·시간·픽셀·Undo·검수 | 새 영상 후보를 기존 편집 기능으로 넘기기 |
| 출력 | 동일 bake의 atlas/runtime/Aseprite 호환 JSON/QA | 영상에서 온 후보에도 같은 출력 계약 적용 |

현재 앱은 `generate`를 Codex 이미지 생성 어댑터에 연결하고, 해당 어댑터의 Grok 항목은 비활성 상태다. API의 허용 `operation`에도 영상 작업이 없으며 입력 asset은 PNG/WebP다. **엔진에 코드가 있다는 것과 앱에서 완성된 기능을 제공한다는 것은 다르다.**

## ‘많이 나아졌다’는 부분을 어디서 재현할 것인가

현재 고정 엔진 v2.12.1과 사이트 표시 버전 v2.19.0을 파일로 비교했다.

| 파일 | 실제 차이 | 의미 |
| --- | --- | --- |
| `gen/xai.py` | 동일 | 인증·HTTP 통신을 새로 만드는 것이 핵심은 아님 |
| `gen/video.py` | 변경 2구간, 대각선 방향 허용 추가 | 영상 생성/폴링의 기본 API 연결은 이미 있음 |
| `video/batch.py` | 436 → 757줄 | 동작·방향별 프롬프트와 시작 자세·처리 순서 개선이 큼 |
| `video/loop.py` | 1,070 → 1,269줄 | 루프 선택 이후 보정·출력 처리 개선 |
| `video/auto_motion.py` | 203 → 229줄 | 이동 분석 처리 개선 |
| `video/canvas.py` | 동일 | 현재도 동작용 여백 처리를 재사용 가능 |

이는 선택한 파일의 정적 비교이며 성능·품질 개선 비율을 의미하지 않는다. 모델 서비스 자체의 변경 효과와 엔진 개선 효과도 아직 분리 측정하지 않았다.

구체적으로 검토할 공개 엔진 개선은 다음과 같다.

- 방향별 제자리 이동·시점 유지 문구, Lite 모델의 과장된 보행을 줄이는 문구.
- 정면·후면 걷기에서 차렷 자세 대신 중간 걸음 자세의 그림으로 시작하는 옵션. 추가 스틸 생성이 필요할 수 있으므로 자동으로 숨겨 실행하지 않는다.
- 반복 주기를 먼저 찾고 연결 구간의 연속성을 비교하는 선택 방식과 실패 시 제한적인 재탐색.
- 선택적 RIFE 보간을 이용한 튀는 프레임 보정, 여러 방향의 주기 맞춤.
- 출력 리사이즈에서 알파와 색을 분리해 경계의 밝은 띠·키 색 오염을 줄이는 처리.

최신 엔진을 통째로 덮어쓰면 현재 Codex·추출·cyan cutout 패치와 앱 출력 계약을 훼손할 수 있다. 도입할 영상 기능의 의존 모듈을 함께 확인해 프로젝트 전용 엔진에 이식하거나 검증된 버전으로 통합한다. 원본 manifest·LICENSE·NOTICE와 로컬 패치를 보존한다. 공용 스킬은 수정하지 않는다.

## 최소 구현 계약

아래는 제안이며 기존 API에 이미 존재하는 명령이 아니다.

### 요청과 단계

기존 `/v1/projects/:id/jobs`에 영상 제작용 작업을 추가한다. 명칭 예시는 `generate_video`이며 기존 `generate`의 PNG 반환 계약은 유지한다.

```ts
type GenerateVideoParams = {
  referenceRevisionId: string;
  baseAssetId: string;
  state: 'idle' | 'walk' | 'run' | 'jump' | 'attack';
  direction: 'side' | 'front' | 'back';
  motionPrompt: string;
  model: string;
  durationSeconds: number;
  resolution: string;
  loopMode: 'auto' | 'periodic' | 'one-shot' | 'pinned';
};
```

기존 job envelope의 `inputRevision`, `idempotencyKey`를 그대로 사용한다. 모델별 유효한 길이·해상도·pin 조합은 서버 capability에서 검증한다. 초기에 모든 모델·방향·동작 조합을 열 필요는 없다. 반환 프레임 수는 요청한 정수와 일치한다고 가정하지 않고 실제 FPS·선택 길이·샘플링 결과로 기록한다.

`prepare → submit → poll → download → extract → cutout → select_cycle → import_candidates → needs_review`

영상 제출 직후 받은 `request_id`를 먼저 저장해야 한다. 현재 엔진의 일괄 실행 함수는 성공 결과에 ID를 담지만, 앱 재시작 후 무과금 조회 재개를 위해서는 **제출 직후의 저장과 기존 ID 조회**를 연결해야 한다. 외부 POST의 응답 자체를 받지 못한 경우에는 접수 불명으로 남기고 자동으로 다시 생성하지 않는다.

완성된 MP4를 내려받았으면 이후 배경 제거·루프 선택·후편집은 그 파일에서 다시 실행한다. 이런 로컬 후처리 실패 때문에 영상을 다시 생성하지 않는다. 로컬 작업 중단이 외부 생성 취소나 환불을 의미하지 않도록 상태를 구분한다.

### 원본과 편집 데이터

현재 `register_asset`·백업 복원은 이미지 검증을 전제로 한다. MP4를 기존 이미지 asset에 억지로 넣으면 가져오기·미리보기·백업이 깨진다.

- 원본 MP4·생성 receipt·후처리 report는 artifact로 보존한다.
- 추출 PNG는 기존 이미지 asset과 frame으로 등록한다.
- 각 프레임에는 `sourceVideoArtifactId`, `sourceFrameIndex`, `sourceTimeMs`, 원본 hash를 연결한다.
- RIFE로 만든 프레임은 원본 추출과 구분하고 입력 이웃 프레임·보간 비율·도구 버전을 기록한다.
- 시간 정보는 기존 occurrence의 `durationMs`로 연결한다. 프레임을 건너뛰면 총 동작 시간이 보존되도록 간격을 반영한다.
- 같은 동작의 후보는 공통 scale group에 두고, 몸 기준과 앵커는 기존 에디터에서 확인한다. 동작마다 bbox 높이를 동일하게 늘리지 않는다.
- 백업 ZIP은 영상·후처리 메타데이터를 포함하도록 별도 형식과 호환 복원 경로를 추가한다. 기존 PNG 프로젝트의 백업은 계속 열려야 한다.

### 사용자가 보는 흐름

1. 기존 기준 그림을 선택한다.
2. ‘영상으로 동작 만들기’에서 동작·방향·길이를 정하고 시작한다.
3. 그림·영상·배경 제거·구간 선택의 진행과 중간 결과를 본다.
4. 추천 구간을 재생하고 시작/끝을 바꾸거나 다른 후보 구간을 선택한다.
5. 기존 에디터에서 크기·발 위치·순서·시간·픽셀을 보정한다.
6. 원본 영상, 보정 전후 재생, 최종 bake를 대조한 뒤 내보낸다.

AI 대화 입력은 이 구조화된 요청을 만들고 기존 편집 명령을 제안하는 층으로 추가할 수 있다. 영상 한 동작의 제작·편집이 이어지는 검증을 먼저 끝내야 대화형 화면만 만들고 실질 기능이 빠지는 일을 피할 수 있다.

## 첫 완성 단위와 수용 기준

첫 범위는 **기존 기준 캐릭터 하나·측면 동작 하나**다. 영상 생성→후처리→후보 등록→타임라인→최종 출력까지 연결한다. 이후 idle/run/attack, 다방향, 보간·묶음 제작을 넓힌다.

| 완료 조건 | 검증 방법 |
| --- | --- |
| 실제 기준 그림으로 영상이 만들어짐 | 원본 MP4, 공급자 request ID·모델·설정·receipt 보존 |
| 같은 캐릭터로 사용할 수 있음 | 보정 후 주요 요소·스타일 확인. 미세 픽셀 차이만으로 탈락시키지 않음 |
| 동작이 자연스럽게 읽힘 | 실시간·느린 재생으로 교대·접지·방향·처음/끝 연결 검수 |
| 편집으로 개선할 수 있음 | 구간 선택·공통 배율·앵커·순서·시간 수정이 실제 결과에 반영 |
| 재작업 때 생성 비용 중복이 없음 | 내려받은 영상으로 후처리 재실행, 중단 후 기존 request ID 조회 재개 |
| 게임용 파일이 동일하게 재생됨 | 기존 확정 bake·runtime의 프레임 및 duration과 최종 출력 대조 |
| 파일을 다시 열 수 있음 | 저장·재시작·백업 복원 후 원본 계보와 편집 유지 |

Grok의 영상 생성이 성공한 것만으로 이 표를 통과한 것으로 보지 않는다. 반복 유사도 점수도 왼발·오른발 의미를 직접 판정하지 않는다. 최종적인 동작 검수와 실패 시 수정 흐름이 에디터의 역할이다.

## 이번에 실제로 검증한 것

현재 프로젝트 엔진의 기존 테스트 중 필요한 항목만 실행했다. **18 passed in 0.31s.**

- 영상 요청 body·상태 조회·MP4 게시: 주입한 fake transport로 확인.
- API 실패·잘못된 MP4·잘못된 요청의 거부: fake 응답으로 확인.
- 첫·마지막 프레임 지정: fake transport의 요청 body로 확인.
- 반복 주기 선택, 서 있는 몸 높이와 동작별 목표 크기: 합성 시험 프레임으로 확인.

이는 기존 v2.12.1 엔진의 오프라인 회귀 검사다. 실제 Grok 호출, 웹 UI 연결, v2.19.0 전체 실행, 생성 품질 검증이 아니다. 새 테스트나 기능 코드를 만들지 않았다. 생성 크레딧·API 사용료 지출은 0이다.

기존 서비스의 500크레딧은 필요한 관찰 데이터를 확보하는 데만 사용한다. 자체 Grok API 호출 비용으로 이전되는 잔액은 아니며 이번 분석에서는 둘 다 사용하지 않았다.

## 근거

- 현재 [영상 API 코드](../../engine/sprite-gen/sprite_gen/gen/video.py), [xAI 통신](../../engine/sprite-gen/sprite_gen/gen/xai.py), [앱 provider](../../adapters/spritegen/provider.py).
- 현재 [worker 작업](../../services/worker/task.py), [worker 복구·게시](../../services/worker/main.py), [작업 API](../../services/api/main.py), [파일 저장](../../services/api/store.py), [생성 UI](../../apps/web/src/SourceSteps.tsx).
- 비교 기준 [v2.19.0 영상 API](https://github.com/aldegad/sprite-gen/blob/v2.19.0/sprite_gen/gen/video.py), [동작 제작](https://github.com/aldegad/sprite-gen/blob/v2.19.0/sprite_gen/video/batch.py), [루프 처리](https://github.com/aldegad/sprite-gen/blob/v2.19.0/sprite_gen/video/loop.py), [영상 파이프라인](https://github.com/aldegad/sprite-gen/blob/v2.19.0/docs/video-pipeline.md).
- 다운로드 원본·SHA-256: 추가 소스 기록 (리서치 정리로 삭제). 위 비교는 공개 태그의 코드 기준이며 운영 서버의 실제 바이너리를 검사한 것은 아니다.
