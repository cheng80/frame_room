> 보관 안내(2026-10-13): 이 문서는 2026-10-12~13 프레임 선별 실험·검수 당시의 기록이다. 여기 적힌 Laya·Jev·관찰 모델 비교 등의 선택지와 실행 방법은 현재 기본이 아니다. 현재 기본은 로컬 Codex catalog의 최신 Luna 관찰과 규칙 판정이며 [FRAME_SELECTION_RULES_CLEANUP_2026-10-13.md](FRAME_SELECTION_RULES_CLEANUP_2026-10-13.md)를 따른다. 시험 수, `output/`·`/tmp` 증거 경로와 작업 ID는 당시 작업 폴더 기준이며 이 저장소에 포함되지 않는다. 키 값과 비밀 파일 해시는 기록하지 않았다.

# 프레임 선별 Jev(TypeSafe) 판정 준비 (2026-10-12)

작성: 구현 담당 Claude Opus 5.5 · High (Orca `task_9ac76b3bd2f2`, dispatch `ctx_89062c04bc22`). 검수는 별도 GPT-6.1 Sol · Medium이 맡는다. commit·push·PR·배포는 하지 않았다. 원자료는 `output/frame-selection-jev/`에 있다.

## 결과 요약

- **준비까지만 완료했다. live 비교는 실행하지 않았다.** TypeSafe 호출 0회, Luna 관찰 호출 0회다. 새 프로젝트나 작업도 만들지 않았다. 키 값은 읽거나 출력하지 않았다. 결과가 없으므로 Jev와 Laya 중 어느 쪽이 나은지는 판단하지 않는다.
- 키 입력용 루트 `.env`(mode 600, git-ignored)와 `.env.example`을 새로 만들었다. 기존 파일은 없었다. 입력 변수는 `TYPESAFE_API_KEY`이고 `TYPESAFE_MODEL=jev-1.13.0`은 미리 채웠다. 작성 직후 PM에 경로와 변수 이름만 통보했다(`msg_8acd46a63644`). 작업 중 `.env` 크기가 110→217바이트로 바뀐 것을 `stat`으로만 확인했다. 사용자가 입력한 것으로 보이며 내용은 열지 않았다.
- 옵트인 `frameJudge: "jev"`를 구현했다. 기존 `auto`/`rules`/`laya`, 기본값, Laya `QUESTION_VERSION`·`_state`·`QUESTION`, 관찰 `PROMPT`·캐시 키는 그대로다. `auto`는 Jev를 고르지 않는다.
- 비교 러너 `output/frame-selection-jev/scripts/run_jev_comparison.py`를 준비했다. 기본은 dry-run이고 `--live`는 다음 task에서 PM이 실행한다. dry-run 결과는 **ready**다. 두 영상 모두 Luna 관찰 23개가 캐시에 있고 파싱 문제는 0건이다. 입력 bytes도 원 프로젝트와 같다.

## 공식 문서 확인 (2026-10-12, 확장자 없는 페이지와 `.md` 둘 다 접근됨)

`llms.txt`, `/api`, `/models`, `/primitives/choice`, `/confidence`, `/cookbooks/citation_check`와 `~/.codex/skills/typesafe-ai/SKILL.md`를 읽었다.

- `POST https://api.typesafe.ai/v1/systemone`, `Authorization: Bearer <key>`. 요청 `{model, state, questions}`, 응답 `{model, answers, usage{input_tokens, output_tokens}}`.
- Choice 답변: `type`, `choice`(최고 확률 옵션), `probabilities`(모든 옵션, 합 1), `confidence`(0..1). Choice confidence는 `(p_max − 1/n)/(1 − 1/n)`이다. 분포의 집중도이며 확률이 아니다.
- 질문 id는 모델에 전달되지 않는다. `instructions`는 객체로 줄 수 있고 state 경로를 backtick으로 가리킨다.
- `jev-1.13.0`은 텍스트만 받는다. 응답 `model`은 실제로 답한 버전 id다. alias(`jev-latest`)는 바뀔 수 있으므로 버전 id를 고정했다.
- 오류: 401, 422, 429, 529. 문서는 backoff 재시도를 권하지만, 이번 작업은 자동 재시도 금지 조건을 따른다.

## 변경 (이번 증분만, `incremental.diff`, 14파일 +813/−20)

| 파일 | 내용 |
| --- | --- |
| `adapters/spritegen/typesafe_judge.py` (신규) | stdlib `urllib` 전송(새 의존성 없음). 키는 판정 직전에만 읽는다. 프로세스 환경 값이 있으면 빈 값이라도 그 값을 쓰고, 없으면 루트 `.env`의 `KEY=VALUE` 줄을 읽는다(`export`·따옴표 허용, 셸 해석 없음). `os.environ`에 넣지 않는다. `capability()`는 로컬 확인만 한다(키 유무, `TYPESAFE_MODEL`이 비었거나 고정값인지). HTTP는 쓰지 않는다. `evaluate()`는 POST 1회만 보낸다. 오류는 코드와 HTTP 상태만 남기고 응답 본문은 읽지 않는다(`from None`으로 원인 예외도 떼어 낸다). `check_choice()`는 답변 하나를 검증한다 |
| `adapters/spritegen/frame_selection.py` | `JEV_QUESTION_VERSION="jev-frame-choice-v1"`, `jev_questions`, `jev_request`(캐시·receipt), `jev_judge`, `resolve_judge("jev")`, `select(jev_post=, observation_cache_only=)`. codex 관찰 subprocess 환경에서 `TYPESAFE_API_KEY`를 제거한다 |
| `adapters/spritegen/video_processing.py` | `frameJudge`에 `jev` 추가. `jev`는 `vision`에서만 쓸 수 있다. 선택 옵션 `observationCacheOnly: true`를 추가했다. 오류 문구에 판정 이름을 넣었고 `VIDEO_FRAME_OBSERVATION_CACHE_MISS`를 추가했다 |
| `adapters/spritegen/video_provider.py` | 같은 검증(`VIDEO_SETTING`). capability `frameSelection.judges`에 `jev`를 추가했고 `frameSelection.jev`도 넣었다 |
| `apps/web/src/VideoStep.tsx`, `videoWorkflow.ts`, `CandidateReview.tsx` | 기존 "선별 판정" Select에 `Jev(TypeSafe) 필수 · 유료 API 1회 · 불가하면 중단` 옵션 1개를 추가했다. 키가 없으면 비활성이고 제출 전에 막는다. 판정 출처와 이유 라벨 몇 개를 추가했다. 새 화면이나 컨트롤은 없다 |
| `packages/contracts/VIDEO.md` | Jev 계약과 `observationCacheOnly`를 적었다 |
| `tests/integration/test_frame_selection_jev.py`, `tests/integration/conftest.py` (신규), web test 2개 | 아래 검증. conftest는 모든 integration 테스트에서 실제 키 환경 변수와 실제 `.env`를 막는다 |
| `.env.example` (신규), 러너 스크립트 | 키 입력 안내와 비교 실행 |

## 판정 계약

- **입력은 Laya와 같다.** 코드 정책이 정하지 않은 후보마다 Laya가 받는 `_state(obs, prev, next)`(관찰에서 만든 영어 결함 목록과 이웃 결함, 픽셀 없음)를 쓴다. 이 상태를 영상당 요청 1회의 `state.frames.<Fxxx>`에 모두 넣는다. 질문은 후보마다 독립 Choice이고 criteria는 Laya `QUESTION`과 같다(keep/reject/review). 질문 id를 모델이 읽지 않으므로 `instructions`를 `{frame_id, question}` 객체로 두고 `frames.<id>`를 backtick으로 가리킨다. 공정성 차이: Laya는 후보 하나만 보고, Jev는 같은 요청 안에서 다른 후보 상태를 문맥으로 함께 본다.
- 코드 정책(빈 프레임, 관찰 누락·필드 누락·`unknown`·가장자리 충돌)은 Jev 앞에서 먼저 적용하고 질문에서 뺀다. 규칙 판정과 keep/reject가 엇갈리면 `CONFLICT_JEV_VS_RULES`로 review다. `confidence` 0.6 미만은 `JEV_LOW_CONFIDENCE`로 review다. **0.6은 Laya와 같은 미보정 실험값이다. TypeSafe confidence는 확률이 아니라 분포 집중도다.** 슬롯 선택·시퀀스 롤백·균등 유지 규칙은 기존과 같다.
- **신뢰 경계:**

| 경우 | 처리 |
| --- | --- |
| 키 없음(빈 프로세스 값 포함), `TYPESAFE_MODEL`이 고정값과 다름 | 관찰 전 `SelectionUnavailable` → `VIDEO_FRAME_JUDGE_UNAVAILABLE`. 유료 호출 0회 |
| 401/403 | 같은 오류로 작업 중단. 게시하지 않는다. 관찰 캐시는 남는다 |
| 422·429·529·기타 HTTP, timeout, 네트워크, 깨진 JSON, `answers` 형식 오류, 응답 `model` ≠ `jev-1.13.0` | 열린 후보 전부 `JEV_ERROR:<code>`로 review. 캐시하지 않는다. 재시도와 다른 모델 fallback은 없다 |
| 답변 누락·`type`≠choice·라벨 밖 choice | 해당 후보 review |
| probabilities: 라벨 집합이 정확히 keep/reject/review, 유한 수 0..1(bool·초대형 정수 제외), `fsum` 합 1±0.001, choice가 최대값 | 어긋나면 review |
| confidence: 유한 수 0..1(bool·문자열·초대형 정수 제외) | 어긋나면 review |

- **기록:** `judge.jev`에 요청·실제 모델, protocol, 질문 버전, 캐시 키, state·questions SHA-256, 질문 수, 사용량, 지연, HTTP 상태, 호출 수, `automaticRetry:false`, `fallbackModel:null`을 남긴다. 결정별 `jev`에는 choice·confidence·probabilities(비유한 값은 null로 바꿔 store의 `allow_nan=False`를 지킨다)·질문 SHA-256을 남긴다.
- **캐시** `<cache>/jev/<key>.json`: 키 재료는 protocol `typesafe-systemone-v1`, 고정 모델, 질문 버전, state, questions다. API 키는 넣지 않는다. 검증된 응답만 저장한다. 깨진 항목은 무시한다.
- **`observationCacheOnly`:** 관찰 함수를 "호출 시 실패"하는 함수로 바꿔 끼운다. 캐시 hit가 아니면 Jev 호출 전에 `ObservationCacheMiss` → `VIDEO_FRAME_OBSERVATION_CACHE_MISS`로 중단한다. Luna를 다시 호출하는 경로는 없다.

## 비교 준비 (dry-run, 오프라인)

```
engine/sprite-gen/.venv/bin/python output/frame-selection-jev/scripts/run_jev_comparison.py --help
engine/sprite-gen/.venv/bin/python output/frame-selection-jev/scripts/run_jev_comparison.py --dry-run
```

dry-run은 키를 읽지 않는다. HTTP 호출과 프로젝트·작업 생성도 하지 않는다. 기존 `job-{pirate,cleric}-{luna-rules,luna-laya}.json`과 관찰 캐시만 읽는다. 결과는 `prepared/dry-run.json`이다.

| | 해적 | 성직자 |
| --- | --- | --- |
| 영상 SHA-256 (`c314768d` 사본 = `5f83bfb7` 원본) | `90828bce4736…` | `9a1945d761bb…` |
| 기준 그림 SHA-256 | `3990e5a231cd…` | `a9dda9449824…` |
| 구간 / 균등 인덱스 | 18–42 · 18,21,24,27,30,33,36,39 (8장, 1000ms) | 33–59 · 33,36,39,42,46,49,52,55 (8장, 1083ms) |
| Luna 관찰 캐시 키 (rules·Laya 작업 동일, 보낸 이미지 9장 SHA 동일) | `52ffc6259d4c…` | `0d94d02fc1f2…` |
| 캐시 파싱 / 문제 | 23/23 · 0 | 23/23 · 0 |
| Jev 질문 수 / 코드 정책 결정 | 23 / 0 | 23 / 0 |
| 요청 본문(키 제외) | 12,852 B, state `27e578b41e58…`, questions `131e5af5070e…` | 12,222 B, state `749ef7a1eaa5…`, questions `6e0f1f2bc0f4…` |

`prepared/{pirate,cleric}-jev-request.preview.json`은 worker가 같은 이미지에서 만들 요청 본문이다. 기록된 metrics와 캐시 관찰로 다시 만들었다.

## 다음 live 실행 (새 task, PM 실행)

1. 사용자가 `.env`에 키를 넣었다고 PM이 확인한다.
2. 실행 중인 API는 이 코드 이전에 시작돼 `frameJudge:"jev"`와 `observationCacheOnly`를 거부한다. 진행 중 작업이 0건인지 확인한다. 그다음 `scripts/launch.py --dev`만 종료하고 같은 환경으로 다시 시작한다. 이번 task에서는 재시작하지 않았다(작업 34건, 마지막 갱신 22:03, 진행 중 없음).
3. `--live`를 실행한다. 다음 조건에서는 아무것도 만들지 않고 종료한다: 키 없음(exit 2), API가 `jev`를 제공하지 않음(exit 3), Luna 캐시 없음(exit 4). 통과하면 새 프로젝트 "비교 · Luna 관찰 + Jev 판정 (2026-10-12)"를 만든다. 같은 영상·기준 그림 bytes를 올리고 영상마다 `process_video` 1건을 실행한다(`frameJudge:"jev"`, `frameObserver:"gpt-6-luna-medium"`, `observationCacheOnly:true`, idempotency `jev-comparison-2026-10-12-{name}-luna-jev`). **TypeSafe POST는 최대 2회다.** 실패한 작업은 다시 돌리지 않는다. receipt에 오류가 있거나 호출 예산을 넘으면 중단한다. 관찰 캐시 키나 이미지 SHA가 Luna 작업과 다르면 중단한다.
4. 산출물: `experiment/state.json`, `job-*-luna-jev.json`, `comparison-*.json`(rules/Laya/Jev 적용 인덱스, 개수, 프레임별 label·confidence·probabilities, Jev receipt). 프로젝트 폴더의 동작·프레임·재생 시간 저장 검증은 그 task에서 한다.

## 실행한 검증

- `PYTHONPATH=. engine/sprite-gen/.venv/bin/python -m pytest -q tests/integration -p no:cacheprovider -W ignore`: **2457 passed, 1 skipped** (166.6초, `tests/integration.txt`). 신규 Jev 36건과 실제 Laya checkpoint smoke를 포함한다. 직전 기준은 2406 passed였다.
- 신규 테스트는 fake HTTP와 패치한 `urlopen`만 쓰는 **오프라인 계약 경계 시험**이다. 실제 TypeSafe 동작이나 Jev 정확도를 검증한 것이 아니다. 확인 항목은 다음과 같다.
  - capability가 로컬 확인만 하는지, `.env` 파싱(빈 값, 따옴표, `export`, `$(…)` 미실행), 프로세스 값 우선(빈 값 포함), 모델 고정
  - 키가 없을 때 관찰 전에 실패하는지(관찰 호출 0), `auto`가 Jev를 고르지 않는지, `jev`가 `vision`을 요구하는지
  - 영상당 요청 1회, Laya `_state`·criteria 재사용, 질문마다 `frame_id`가 있는지
  - 캐시 hit 시 POST가 없는지
  - 답변 검증 18가지, 요청 수준 오류 9가지(재시도 0, 캐시 없음), 401 시 작업 중단
  - Bearer 헤더, URL, timeout
  - 키·`Authorization`·`Bearer`가 record·캐시·예외에 없는지, codex 환경에 키가 넘어가지 않는지
  - `observationCacheOnly` 캐시 miss는 관찰·판정 0회로 중단하고, 캐시 hit는 같은 캐시 키로 판정 1회만 하는지
- 기존 `tests/integration/test_frame_selection.py`는 수정하지 않았다.
- `apps/web`: `npx tsc --noEmit -p .` 통과, `npx vitest run` **503 passed**(기존 테스트에 assertion 4개 추가), `npm run build` 통과. prebuild 전후 `public/guide` 해시가 같다(`tests/guide-*.sha256`).
- `git diff --check` 통과. venv는 바꾸지 않았다(`baseline/venv-freeze.txt`, 설치 없음). 코드 freeze: `freeze-code.sha256`(14개).
- Postman: contract-first로 공식 문서 계약을 테스트에 옮겼다. 외부 workspace·mock·login·push는 하지 않았다.

## 데이터 보존 (`preservation-check.json`, `scripts/preservation_check.py`)

- baseline(`baseline/`): HEAD, git status, 기존 diff, worktree 108개 해시, `.data`/`output` 15,981개 SHA-256, venv freeze, 수정 전 코드 사본. `.env`는 baseline과 산출물에 넣지 않았다. `CandidateReview.tsx`와 `candidateHistory.test.ts`는 편집 전에 사본을 남기지 못했다. 그래서 HEAD에 baseline `worktree.diff`를 적용해 다시 만들었고 baseline 해시와 같음을 확인했다.
- `.data`/`output`: 누락 0, 추가 0. 바뀐 파일은 둘이며 둘 다 실행 중인 앱 인스턴스가 쓴 것이다.
  - `.data/app.sqlite3`: 작업 수 34건 그대로, 마지막 작업 갱신 22:03.
  - `output/frame-selection-observer-comparison/followup/app-restart.log`: 이전 앱의 stdout이며 브라우저의 `GET /v1/health`, `GET …/c314768d…/jobs` 폴링 기록이 계속 쌓인다.
  - 이 둘은 이번 task가 쓴 것이 아니다. 나는 앱 API를 호출하지 않았다.
- worktree: 누락 0. 바뀐 9개는 위 변경표의 수정 파일뿐이다. 기존 비교 프로젝트, 실험 파일, Luna 캐시, Laya 버전, guide, `AGENTS.md`, 공용 sprite-gen skill은 편집하지 않았다.

## 검수 예비 finding 반영

1. 빈 프로세스 환경 값도 `.env`보다 우선한다. 빈 키는 unavailable이고, 빈 모델 값은 고정 기본값이다.
2. 확률 합 공차를 `SUM_TOLERANCE=1e-3`(`fsum`)으로 좁혔다. 1.005는 거절한다. `10**1000` 같은 초대형 정수는 `OverflowError` 없이 거절한다.
3. `frameJudge:"jev"`에 `frameSelection`이 없거나 `uniform`이면 API(`VIDEO_SETTING`)와 처리 계층(`VIDEO_INVALID_PARAMS`) 둘 다 거절한다. 기존 `laya`/`rules` 요청 형태는 그대로 받는다.

## 남은 한계

- live 결과가 없다. Jev 정확도, 응답 지연, 실제 응답 형식(공식 예시 밖의 필드나 반올림)은 확인하지 않았다.
- 0.6 게이트와 확률 합 공차는 미보정 값이다. Jev는 영어가 주 학습 언어이며 상태는 영어로 보낸다.
- 비교 근거는 기존과 같이 영상 2개, 모델 시각 라벨 기준이다. 사람 정답 라벨은 없다.
