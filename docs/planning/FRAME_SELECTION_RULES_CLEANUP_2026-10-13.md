> 보관 안내(2026-10-13 게시 준비): 이 문서는 원본 작업 폴더의 미커밋 전체 상태에서 진행한 구현·검수 기록을 그대로 옮긴 지침 문서다. 문서의 시험 수, 실행 앱 재시작, `output/`·`/tmp` 증거 경로, 다른 계획 문서 참조는 그 작업 폴더 기준이며 이 저장소에 포함되지 않는다. 이 커밋 범위만 분리해 실행한 검증은 [FRAME_SELECTION_PUBLISH_2026-10-13.md](FRAME_SELECTION_PUBLISH_2026-10-13.md)에 따로 기록한다.

# 프레임 선별: Luna+규칙 기본화와 Laya·Jev 제거 (2026-10-13)

요청: "Luna+규칙을 기본으로 쓰고, 걷어 내자. 기존 후보와 작업 데이터는 보존해." 후속 지침에 따라 고정 `gpt-6-luna` 대신 로컬 Codex catalog에서 최신 Luna를 고르고, 쓸 수 있는 Luna가 없으면 규칙만 적용한다. 계약은 `packages/contracts/VIDEO.md`의 "후보 프레임 선별" 절을 먼저 고친 뒤 코드를 바꿨다.

## 결과

- Laya MLX와 Jev(TypeSafe) 판정의 import, 전송, capability, UI 옵션, 의존성 bootstrap 경로를 없앴다. 판정은 FrameRoom 코드 정책과 규칙(`frame-rules-v1`)만 쓴다.
- `frameJudge`: `rules`만 받는다. 예전 값 `auto`는 `rules`로 정규화한다. `laya`/`jev`는 관찰 전에 거절한다. API와 worker 재검증은 `VIDEO_SETTING`, 직접 `process_clip`은 `VIDEO_INVALID_PARAMS`다.
- 관찰 모델: `frameObserver`를 생략하면 요청마다 먼저 `shutil.which("codex")`로 Codex CLI가 PATH에 있는지 확인한다(조회만, 실행 없음). 그다음 `$CODEX_HOME/models_cache.json`(기본 `~/.codex`)을 다시 읽는다. 인정하는 행은 `gpt-<숫자 버전>-luna`이면서 `visibility`가 정확히 `"list"`, `input_modalities`가 `image`를 포함한 배열, `supported_reasoning_levels`가 `{"effort": "medium"}` 객체를 포함한 배열인 것뿐이다. 문자열 `"image"`, `{image: true}`, 문자열 `"medium"` 같은 형식은 거절한다. 이 중 숫자 버전이 가장 높은 모델을 골라 medium으로 관찰한다. 관찰 id는 `<model>-medium`이다.
  - 현재 이 컴퓨터의 catalog로는 `gpt-6-luna`·medium이 선택된다(`output/frame-selection-rules-cleanup/after/capability-local-catalog.json`). 따라서 기존 `gpt-6-luna-medium` 관찰 캐시 키가 그대로 맞는다.
  - catalog의 `fetched_at`은 `2000-01-01`, `client_version`은 `0.0.0`이다. 여기서 "최신"은 이 로컬 파일 기준이며, 온라인 목록을 확인한 결과가 아니다. 앱은 catalog를 갱신하지 않는다.
  - CLI가 없거나(`CODEX_CLI_MISSING`) Luna가 없거나 catalog를 읽을 수 없으면 관찰 함수에 들어가지 않는다. 관찰 호출 없이(`observation.calls=0`) 코드 정책만 적용하고, 다른 모델로 대체하지 않는다. 빈 프레임은 reject, 나머지 후보는 `OBSERVATION_MISSING` review가 되어 균등 프레임을 유지한다. 기록에는 `observer.available=false`와 `reason`이 남는다. `/v1/providers` capability도 같은 사전 확인을 쓴다. 사전 확인 뒤 실행 시점에 CLI가 사라지는 경합은 따로 처리한다(실행 실패 1회 → `OBSERVATION_FAILED` review, 캐시 없음, 재시도·대체 없음).
- 프롬프트, 관찰·스키마·selection 버전, 캐시 키 구성은 바꾸지 않았다. 다음 정책도 그대로다.
  - 이웃 교체 정책: 균등 프레임이 reject이거나 규칙도 review로 볼 때만 keep 이웃으로 바꾼다.
  - 빈(blank) 프레임 → 코드 정책 reject. 그 밖의 unknown, 충돌, 누락 → review.
  - 슬롯 수, 재생 시간, 루프 여부, 시퀀스 되돌리기, `uniform-alternative`가 유지된다. `review`/`hidden`은 바꾸지 않는다.
- 자동 기본값과 수동 비교를 구분한다. 자동 기본값은 위 catalog 최신 Luna·medium뿐이다. `frameObserver` 고정 허용 목록(`gpt-6-luna-medium`/`gpt-6.1-sol-medium`)은 사용자가 명시한 비교 요청 전용이며, 자동 기본값이 실패할 때 대체 모델로 쓰지 않는다.

## 신규와 기존의 기본값 경계

| 경로 | `frameSelection` 생략 시 |
|---|---|
| 웹 UI 새 설정 | `vision`. 클라이언트는 항상 명시해서 보낸다. 균등도 `uniform`으로 명시한다. 필드가 없는 예전 설정 객체는 `uniform`으로 보낸다. 주기 맞춤을 고르면 `uniform`이다. |
| `POST /v1/projects/{pid}/jobs`(`generate_video`/`process_video`), `POST …/video-batches` 항목 | 해시 계산 전에 `{frameSelection: "vision", frameJudge: "rules"}`를 요청에 넣어 저장한다. `matchClipId`가 있으면 기존처럼 균등이다. |
| 이미 저장된 작업 요청의 worker 재검증 | `uniform`(변경 없음). 저장된 요청은 다시 쓰지 않는다. |
| 직접 `process_clip`(예: `scripts/cleric-*.py`) | `uniform`(변경 없음). |

이 경계 때문에 기존 작업과 스크립트에는 관찰 모델 호출이 추가되지 않는다.

멱등성: `enqueue()`는 같은 제출 키의 기존 작업이 있으면 저장된 해시를 원본 요청 해시, 그리고 기본값을 넣은 요청 해시와 비교한다. 둘 중 하나와 같으면 그 작업을 그대로 돌려준다(새 작업·관찰·기본값 기록 없음). 그래서 기본값 도입 전에 생략·`auto` 형태로 저장된 작업도 같은 원본 요청으로 재전송할 수 있다. 신규 기본값 작업과 명시 `uniform` 작업의 재전송도 같은 작업을 돌려준다. 같은 키로 내용을 바꿔 보내면 계속 `IDEMPOTENCY_CONFLICT`(409)다. 묶음 제출은 원본 본문 해시로 묶음을 찾으므로 그대로 호환된다.

과거 기록은 지우거나 다시 쓰지 않는다. 대상은 다음과 같다.

- `judge.backend`/`decision.source`의 `laya-mlx`/`jev` 값
- `laya`/`jev` 필드
- `LAYA_*`/`JEV_*`/`CONFLICT_*_VS_RULES` 이유 코드
- `.data/cache/frame-selection/jev/`

UI의 이유·출처 표시는 이 값을 계속 읽는다(`CandidateReview.tsx`).

## 변경한 파일

수정:

- `packages/contracts/VIDEO.md`: 후보 프레임 선별 절 재작성. 기본값 경계, 거절 오류, catalog 선택, 과거 기록 호환, capability 형태를 다룬다.
- `adapters/spritegen/frame_selection.py`:
  - Laya 감지·로드·판정과 Jev 요청·판정·캐시 코드를 삭제했다.
  - `SelectionUnavailable`을 없애고 `ObservationCacheMiss`만 남겼다.
  - `catalog_path()`와 `latest_luna()`를 추가했다. `latest_luna()`는 Codex CLI 사전 확인과 엄격한 catalog 행 검증을 한다.
  - `_observer`와 `codex_observe` 허용 조건에 catalog Luna·medium을 넣었다.
  - `select()`는 규칙 전용이다. 관찰 모델이 없으면 관찰을 건너뛴다.
- `adapters/spritegen/video_provider.py`:
  - `frameJudge`는 `auto|rules`만 허용하고 `auto`는 `rules`로 바꾼다. `laya`/`jev`는 제거 안내 오류로 거절한다.
  - `with_fresh_selection()`을 추가했다.
  - capability는 `{modes, judges:["rules"], defaultMode, defaultJudge, observer}`를 돌려준다.
- `adapters/spritegen/video_processing.py`: `frameJudge` 검증(`auto|rules`)과 `rules` 고정. Laya/Jev 분기와 `VIDEO_FRAME_JUDGE_UNAVAILABLE` 경로를 삭제했다. 생략한 observer는 catalog에 맡긴다.
- `services/api/main.py`: `enqueue()`에서 영상 작업의 신규 요청에 `with_fresh_selection()`을 적용한다(해시 계산 전). 기존 작업 재전송은 원본 요청 해시로도 맞춘다.
- `scripts/setup.sh`, `scripts/start.sh`: Laya 선택 설치를 유지하던 `SYNC` 분기를 지웠다(HEAD와 동일).
- `apps/web/src/videoWorkflow.ts`: 기본값을 `vision`으로 바꾸고 `frameJudge` 설정을 없앴다. 선택을 항상 명시하고, 주기 맞춤은 `uniform`으로 보낸다.
- `apps/web/src/VideoStep.tsx`: Laya/Jev 판정 선택과 경고를 삭제했다. 관찰 모델은 capability `observer`로 표시하고, Luna가 없으면 경고한다. 주기 맞춤 중에는 선별 선택을 끈다.
- `apps/web/src/CandidateReview.tsx`: 과거 기록용 라벨을 유지한다는 주석만 추가했다.
- 테스트:
  - `tests/integration/conftest.py`: TypeSafe 키 차단 대신 fixture catalog와 가상 Codex CLI(`shutil.which("codex")`만 대체)를 쓴다. 실제 `codex_observe` 호출은 차단한다.
  - `tests/integration/test_frame_selection.py`: Laya 테스트를 삭제했다. 다음 시험을 추가했다.
    - catalog 선택·부재, 잘못된 형식의 catalog 행 9종 거절과 요청마다 다시 읽기
    - CLI 부재 사전 확인(관찰 진입 금지, `calls=0`)과 사전 확인 뒤 CLI가 사라지는 경합
    - 캐시 호환·격리, 제거된 판정 거절, 캐시 전용
    - API 신규 기본값·명시 uniform·저장 요청 검증
  - `tests/integration/test_video_jobs.py`: 선별과 무관한 4개 시험에 명시 `uniform`을 넣었다.
  - `tests/integration/test_video_prompt.py`: 저장 요청 기대값에 신규 기본값을 반영했다.
  - `tests/integration/test_video_batches.py`: 기본값 도입 전 저장 형태(생략, `frameJudge: auto`, `vision`+`auto`)의 원본 요청 재전송, 신규 기본값·명시 uniform 재전송, 내용 변경 시 409를 확인한다.
  - `apps/web/tests/videoWorkflow.test.ts`, `apps/web/tests/candidateHistory.test.ts`

삭제(작업 시작 시 모두 git 미추적. 원본은 `output/frame-selection-rules-cleanup/baseline/worktree-snapshot/`에 있다):

- `adapters/spritegen/typesafe_judge.py`
- `engine/requirements-laya-mlx.txt`
- `.env.example`(Jev 전용 템플릿)
- `tests/integration/test_frame_selection_jev.py`

손대지 않은 것:

- 사용자 `.env`(읽지 않음)
- `.data`, 기존 `output` 실험 결과, 과거 계획·검토 문서(`FRAME_SELECTION_*_2026-10-12/13.md`)
- 생성된 가이드(`apps/web/public/guide` 26개 파일 해시가 빌드 전후 같다. 작업 시작 시점과 비교하면 21개는 HEAD와 같고 4개는 작업 시작 스냅샷과 같으며 1개는 git 무시 ZIP이다. `followup/guide-*.sha256`, `followup/guide-vs-task-start.txt`)
- 공용 sprite-gen 스킬
- 전역 Python 패키지, Laya checkpoint(`.data/tools/laya-mlx`)

다만 엔진 venv에 `laya_mlx`가 설치돼 있다면 다음 `scripts/setup.sh` 실행 때 `uv pip sync`가 lock 기준으로 지운다. HEAD와 같은 동작이다.

## 검증

다음은 모두 오프라인이다. 유료 Luna·Jev·Laya 호출, 영상 생성, 모델 설치는 하지 않았다. 테스트의 Codex catalog는 fixture이고, 실제 `codex_observe`는 conftest가 차단한다.

- pytest 묶음 1: `test_frame_selection`, `test_video_jobs`, `test_video_prompt`, `test_video_batches`, `test_provider`, `test_api`. 1756 passed(`output/frame-selection-rules-cleanup/after/pytest-focused.txt`). 그 뒤 Codex CLI가 없는 경우(`FileNotFoundError` → `OBSERVATION_FAILED` review, 균등 유지, 캐시 없음) 시험 1건을 추가했고, `test_frame_selection`은 46 passed(`after/pytest-frame-selection-final.txt`).
- pytest 묶음 2: 영상·API 관련 12개 파일을 처음 돌렸을 때 2005 passed, 17 failed였다. 실패는 모두 신규 기본값(vision)이 바뀐 데서 온 기대값 차이와 차단된 관찰 호출이었다. `test_video_jobs`·`test_video_prompt`를 고친 뒤 두 파일은 1427 passed. 나머지 integration 파일은 403 passed, 1 skipped.
- 웹: `vitest run` 25 files, 503 passed. `tsc -b --noEmit` exit 0. `vite build`는 scratchpad outDir로 통과했다(앱의 `dist`와 가이드는 다시 만들지 않음).
- 보존 확인: `.data`, `output`, `artifacts` 해시를 비교했다(`.env*`, `*.log`, 이번 증거 폴더 제외). 기준은 작업 시작 시 `baseline/data-output.sha256`, 대상은 `after/data-output.sha256`이며 16,493개 파일 중 다른 것은 `.data/app.sqlite3` 하나다.
  - 이 차이는 실행 중인 worker의 `meta.worker_heartbeat` 갱신이다.
  - 읽기 전용 조회 결과 projects와 jobs의 최신 `updated`는 `2026-10-12T15:00:31Z`(작업 시작 전)다.
  - 작업 상태는 `needs_review` 27, `succeeded` 9이고 실행 중인 작업은 없다(`after/app-db-readonly-check.txt`).
  - 프로젝트 폴더 7개는 모두 `.data` 안에 있어 해시 비교 범위에 포함된다.
- 작업트리: 작업 시작 시 dirty 상태(`baseline/git-status.txt`, `worktree.diff`, `worktree-snapshot/`)와 비교했다. 바뀐 파일은 위 목록과 정확히 같다. 이번 작업분 diff는 `after/task.diff`에 있다.

## 후속 수정과 실행 앱 적용 (같은 날, task_1958375711dc)

- 검수 지적 세 가지를 제품 코드에서 고쳤다.
  - Codex CLI 사전 확인
  - catalog 형식 엄격화
  - 기본값 도입 전 원본 요청의 멱등 재전송
- 영향 시험: `test_frame_selection`, `test_video_batches`, `test_video_prompt`, `test_video_jobs`, `test_provider`, `test_api`에서 1771 passed(`followup/pytest-affected.txt`). 검수자 독립 시험 `/tmp/frame-selection-rules-review-independent.py`는 8 passed(`followup/reviewer-independent-tests.txt`). 웹 코드는 바뀌지 않아 이전 결과(vitest 503 passed, tsc 0)를 그대로 쓴다.
- 웹 `dist`: `npx tsc -b && npx vite build`로 다시 만들었다(`followup/web-build.txt`). 가이드 생성은 실행하지 않았다.
- 실행 앱 재시작 절차:
  - 확인한 상태: 소유 launcher는 PID 2368(`scripts/launch.py --dev`, 23:59 시작, `.data/launcher.lock` 보유)이었다. 환경 변수는 `SPRITE_GEN_DIR=/Users/cheng80/.codex/skills/sprite-gen`, `SPRITE_OPEN_BROWSER=0`이었다. `/v1/health`는 api·worker 모두 ready였고, 실행·대기 작업은 0이었다(`needs_review` 27, `succeeded` 9).
  - 재시작: 그 PID에만 SIGTERM을 보냈고, 하위 프로세스가 모두 종료된 것을 확인했다. 같은 환경 변수로 `scripts/launch.py --dev`를 다시 띄웠다(새 PID 59932). 출력은 `runtime/app.log`에 남는다(`runtime/pre-restart.txt`, `runtime/post-restart-processes.txt`).
- 실행 중인 API(읽기 전용) 결과는 `runtime/api-readonly-check.json`에 있다.
  - `capabilities.frameSelection`은 `{modes:[uniform,vision], judges:[rules], defaultMode:vision, defaultJudge:rules, observer:{model:gpt-6-luna, effort:medium, available:true}}`이다.
  - 프로젝트 7개의 프레임·동작·영상·작업 수가 그대로 읽힌다.
  - 비교 프로젝트의 과거 `selectionDecision.source`(`jev`, `laya-mlx`, `rules`, `code-policy`)도 그대로 읽힌다.
- ego-browser 화면 확인: 새로 만든 TaskSpace 23만 썼고, 끝난 뒤 한 번 종료했다. 읽기 전용이며 제출·편집·유료 호출은 없었다.
  - 프로젝트 목록의 동작/후보 수가 API와 같다(2/18, 10/94, 10/80, 16/128, 2/16, 1/8, 4/28).
  - 비교 프로젝트(`Luna/Sol`, 저장됨 v15 유지)의 영상 설정에서 `영상 프레임 선별`의 기본값은 `Luna 관찰 + 규칙 판정 · 기본`이고, 선택지는 이 항목과 `균등 간격 · 기존 방식` 둘뿐이다.
  - 안내 문구는 `gpt-6-luna · medium`을 표시한다. `선별 판정` 선택이나 Laya/Jev/TypeSafe 문구는 없다(`followup/ui-*.png`).
- 보존: 작업 시작 기준(`baseline/data-output.sha256`, 16,493개)과 비교해 다른 파일은 `.data/app.sqlite3` 하나다. 읽기 전용 조회 결과는 다음과 같다(`followup/app-db-readonly-check.txt`).
  - projects/jobs 최신 `updated`는 `2026-10-12T15:00:31Z`로 그대로다.
  - 표 행 수(revisions 57, assets 1127, jobs 36, events 292, artifacts 314, videos 25)가 같다.
  - 바뀐 것은 worker heartbeat와 재시작 때 새로 발급된 session token뿐이다.
- 코드·문서 고정 해시: `followup/freeze-code.sha256`.

## 내부 관찰 모델 검증 보완 (같은 날, task_c7a775fcd018)

- 범위: 공개 API·`process_clip`의 동작은 바꾸지 않았다. 두 경로는 원래 `frameObserver`를 고정 허용 목록으로만 받았다(검수자 확인). 이번 수정은 공개 취약점 수정이 아니라 내부 경로의 지원 검증 강화다.
- 내부 `_observer`(`select`·`observe`·`codex_observe`가 공유)는 그동안 `gpt-<버전>-luna-medium` 형태면 catalog와 무관하게 받았다. 이제 고정 비교 목록이거나, 그 시점 로컬 catalog의 `latest_luna()` 결과와 같은 Luna일 때만 받는다. 그 밖의 값(`gpt-999-luna-medium`, catalog에 없거나 최신이 아닌 Luna)은 관찰 모델 호출 전에 `ValueError`(`select`·`observe`) 또는 `OBSERVER_NOT_ALLOWED`(`codex_observe`, subprocess 실행 전)로 거절한다. 패턴 전체를 허용 목록으로 바꾸지 않았다.
- catalog 버전 숫자: `LUNA` 정규식을 ASCII 숫자 1~4자리 부분 최대 4개로 제한했다. 5,000자리 버전, 비ASCII 숫자, 부분 5개 같은 행은 일치하지 않아 제외되며 `int()` 변환 오류가 capability나 `select` 밖으로 나가지 않는다. 그런 행만 있으면 `LUNA_NOT_IN_CATALOG`이고 호출 0회로 코드 정책만 적용한다. 정상 행이 함께 있으면 정상 행이 선택된다.
- 바꾸지 않은 것: 프롬프트·스키마·selection 버전, 캐시 키 구성(기존 `gpt-6-luna-medium` 캐시 키 그대로), 이웃 교체·시간·장수·루프·`uniform-alternative`·사용자 review 정책, 웹 코드와 `dist`.
- 시험(오프라인 fixture만, 유료 호출 없음): `test_frame_selection` 65 passed. 새 시험은 다음을 확인한다.
  - catalog 밖 동적 Luna의 `select`/`observe`/`codex_observe` 직접 호출이 관찰 함수·subprocess 전에 거절되고, 작업 폴더도 만들지 않는다.
  - 고정 비교 목록 유지, catalog 최신 Luna 수용.
  - 잘못된·과도한 버전 행 → 호출 0회, 빈 프레임 reject·나머지 review.
  - 기존 시험의 "catalog에 없는 `gpt-7-luna`도 `codex_observe`가 받음" 기대값은 catalog에 올린 경우만 받도록 고쳤다.
  - 경계 묶음 `test_frame_selection`+`test_provider`+`test_api` 347 passed, `test_video_jobs`/`test_video_prompt`/`test_video_batches`의 선별·관찰 관련 3 passed(`final-boundary/pytest-boundary.txt`). 전체 1771 묶음은 다시 돌리지 않았다.
- 실행 앱 백엔드 재시작(`final-boundary/runtime/`):
  - 확인한 상태: 소유 launcher PID 59932(`scripts/launch.py --dev`, cwd 이 프로젝트, `.data/launcher.lock` 보유), `SPRITE_GEN_DIR=/Users/cheng80/.codex/skills/sprite-gen`, `SPRITE_OPEN_BROWSER=0`, 실행·대기 작업 0(`needs_review` 27, `succeeded` 9).
  - 그 PID에만 SIGTERM을 보내고 하위 프로세스 종료를 확인한 뒤, 같은 환경 변수로 다시 띄웠다(새 PID 93268, 출력 `final-boundary/runtime/app.log`). 프런트 빌드·UI 재확인은 하지 않았다.
  - 읽기 전용 API 결과(`api-readonly-check.json`): health api·worker ready. `frameSelection` capability(`gpt-6-luna`·medium, vision/rules)와 프로젝트 7개의 프레임·동작·영상·작업 수, 과거 `selectionDecision.source`가 이전 확인(`runtime/api-readonly-check.json`)과 같다.
  - 실제 로컬 catalog 읽기 전용 확인(`observer-boundary-readonly.txt`, 호출 없음): `latest_luna()`=`gpt-6-luna`. `gpt-6-luna-medium`·`gpt-6.1-sol-medium`은 받고, `gpt-999-luna-medium`·`gpt-7-luna-medium`은 거절한다.
- 보존: 작업 시작 기준(`baseline/data-output.sha256`, 16,493개, `*.log` 제외)과 비교해 다른 파일은 `.data/app.sqlite3` 하나다(`final-boundary/data-output.diff`). 읽기 전용 조회 결과(`final-boundary/app-db-readonly-check.txt`)는 앞 단계와 같다. projects/jobs 최신 `updated` `2026-10-12T15:00:31Z`, 표 행 수 revisions 57, assets 1127, jobs 36, events 292, artifacts 314, videos 25. 모델 catalog, `.env`, 공용 `sprite-gen`은 바꾸지 않았다.
- 이번 단계 변경분: `final-boundary/task-start/`(작업 시작 시 사본, `followup/freeze-code.sha256`과 해시 일치)와 `final-boundary/task.diff`. 고정 해시는 `final-boundary/freeze-code.sha256`이다.

## 남은 한계

- 실제 Luna 관찰 품질과 더 새 catalog Luna의 선택은 fixture로만 검증했다(유료 호출 금지).
- catalog의 `fetched_at`은 `2000-01-01`이다. "최신"은 이 로컬 파일 기준이며, 앱은 catalog를 갱신하지 않는다.
