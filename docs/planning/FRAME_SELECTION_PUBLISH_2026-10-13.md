# 후보 프레임 선별 게시 준비 (2026-10-13)

사용자 "커밋 / 푸시" 승인에 따라 Luna+규칙 후보 프레임 선별 기능을 HEAD 위의 독립 커밋 하나로 게시할 수 있게 추출·stage했다. Orca task `task_dbddf641f590`, 담당 Claude Opus 5.5 High. 이 단계는 준비만 한다. commit·push·PR·merge는 하지 않았고, PM의 staged 검수 뒤 별도 task에서 진행한다.

## 기준

| 항목 | 값 |
|---|---|
| 작업 폴더 | `/Users/cheng80/orca/workspaces/frame_room/frame-selection-luna-rules` (Orca 격리 worktree) |
| branch | `codex/frame-selection-luna-rules` (`cheng80/frame-selection-luna-rules`에서 이 worktree 안에서만 이름 변경, upstream 없음) |
| base | `4b75d3cea4e44524d1de00bc6ff3e6e2ae01a527` (`main`) |
| 원격 | `git fetch origin` 후 `origin/main` = `4b75d3c…`, ahead/behind 0/0. 원격에 이 branch 없음. 통합·rebase 불필요 |
| 원본 작업 폴더 | `/Users/cheng80/Desktop/Current_works/frame_room` (`main`, HEAD 같음). 읽기만 했다 |

staged tree ID와 staged diff는 이 보고서 자체를 포함하므로 보고서 안에 적지 않는다. `output/frame-selection-publish/`(git 무시, 커밋하지 않음)에 있다.

## 원본 보존

- 시작 시 원본 index의 staged 경로 0개, `git status --porcelain` 113줄(수정 89, 미추적 24)이었다. 목록 SHA-256 `af90fdce21c47e7edd9f90166f2a70a7c92a06db75d366da5dd429ed34677e9a`.
- 원본에서 읽은 파일 20개의 SHA-256을 시작 시 기록했고 종료 시 다시 비교했다(`output/frame-selection-publish/orig-sources-*.sha256`). 원본 파일·index·branch·`.data`·`output`·`.env`·모델 catalog·공용 sprite-gen·`node_modules`에는 쓰지 않았다. `.env`는 열지 않았다.
- 원본의 HEAD 대비 dirty 변경(기준 승인 제거, 6단계 production workflow, generation approval, export gate, standalone library 저장 보호, guide/README/AGENTS 등)은 원본에 그대로 남아 있다.

## 포함 범위

원본 diff를 파일 단위로 복사하지 않고 hunk 단위로 골랐다. "전체"는 그 파일의 원본 diff가 모두 선별 기능이라 전부 적용한 경우다.

| 경로 | 포함 | 근거 |
|---|---|---|
| `adapters/spritegen/frame_selection.py` | 신규 전체 | 후보 창·측정·시트·Codex 관찰/캐시·catalog 최신 Luna·규칙 판정·시퀀스 검사 |
| `adapters/spritegen/video_processing.py` | 전체 | `frameSelection`/`frameJudge`/`frameObserver`/`observationCacheOnly` 검증, 선별 연결, 표시 경계, `alternateFrames` |
| `adapters/spritegen/video_provider.py` | 4/7 hunk | 필드 허용·검증(laya/jev 거절, auto→rules), `with_fresh_selection`, `frame_selection_capability`, capability 연결 |
| `services/api/main.py` | 1/4 hunk | `enqueue()` 신규 기본값과 raw/defaulted 해시 멱등 재전송 |
| `services/worker/video_task.py` | 전체 | 관찰 캐시 위치, 대체 후보 무슬롯 등록, `selectionDecision`, FPS·출력 수를 슬롯 기준으로 |
| `packages/contracts/VIDEO.md` | 1/3 hunk | "후보 프레임 선별" 절 |
| `apps/web/src/types.ts` | 부분 | `Frame.selectionDecision`과 `FrameSelectionDecision` 타입만 |
| `apps/web/src/videoWorkflow.ts` | 부분 | `frameSelection` 설정 필드, 기본 `vision`, 요청 직렬화 |
| `apps/web/src/VideoStep.tsx` | 부분 | capability observer 표시 3줄과 "영상 프레임 선별" 선택 블록 |
| `apps/web/src/CandidateReview.tsx` | 부분 | `SelectionDecisionNote`, `selectionLabel`/`selectionReason`(과거 Laya/Jev 코드 표시 포함) |
| `apps/web/src/CandidateLibrary.tsx` | 부분 | `selectionLabel` import와 후보 목록 표시 1곳. HEAD의 `candidateApprovalLabel`은 그대로 |
| `tests/integration/conftest.py` | 신규 전체 | fixture catalog, 가상 Codex CLI, 실제 `codex_observe` 차단 |
| `tests/integration/test_frame_selection.py` | 신규 전체 | 선별 회귀 65건 |
| `tests/integration/test_video_{jobs,prompt,batches}.py` | 전체 | 명시 `uniform`, 신규 기본값 기대값, 멱등 재전송 |
| `apps/web/tests/videoWorkflow.test.ts` | 부분 | 선별 설정 시험 블록과 요청 기대값의 `frameSelection`/`frameJudge` 두 필드 |
| `apps/web/tests/candidateHistory.test.ts` | 부분 | 선별 라벨 시험 블록 |
| `docs/planning/FRAME_SELECTION_RULES_{CLEANUP,FINAL_REVIEW}_2026-10-13.md` | 복사 + 보관 안내 | 원본 dirty 전체 상태의 구현·검수 기록. 이 분리 검증과 다르다는 안내를 머리에 붙였다 |
| `docs/planning/FRAME_SELECTION_PUBLISH_2026-10-13.md` | 신규 | 이 보고서 |

## 제외 범위

- `video_provider.py` `generate(save_checkpoint=…)`, `video_finish.py`/`video_normalization.py` `save_metadata` 콜백: standalone library 저장 보호 기능. `selectionDecision`과 대체 후보는 worker 결과에서 직접 보존되므로 필요 없다.
- `services/api/main.py`의 기준 승인 조건 제거 2 hunk와 export gate 변경, `adapters/spritegen/provider.py`, `services/api/edits.py`: 승인 제거·export 기능.
- `services/worker/main.py` publication guard와 `tests/integration/test_animation_publication_guard.py`: 별도 기능.
- `CandidateReview.tsx` 승인 배지·설명·거절 문구 변경, `videoWorkflow.ts` `approvedVideoReference`→`videoReference`·단계 문구, `types.ts` `Job.attemptId`/`updatedAt`, `candidateHistory` 라벨 변경, `VideoStep.tsx` 기준 선택·`SpriteViewport` 변경, `VIDEO.md` 승인 문구 2 hunk.
- `tests/integration/test_api.py`, `test_provider.py`, `videoStep.test.tsx` 등: 승인 제거·UX 관련 기대값이라 제외. HEAD 시험은 그대로 통과한다.
- 과거 Laya/Jev/observer 비교 문서(`FRAME_SELECTION_*_2026-10-12.md`, `FRAME_SELECTION_JEV_*`), `output/` 원증거, browser 증거, `.env`, 모델 가중치, 원본 영상.
- Laya/Jev 활성 코드는 원본 최종 상태에도 없다. 남은 문자열은 `laya`/`jev` 명시 거절 안내, 과거 기록 표시, observer subprocess 환경에서 오래된 `TYPESAFE_API_KEY`를 지우는 처리뿐이다. 자동 기본값은 catalog 최신 Luna·medium뿐이고, 없으면 관찰 호출 없이 규칙만 적용한다. 수동 비교 허용 목록(`gpt-6-luna-medium`/`gpt-6.1-sol-medium`)은 명시 요청 전용이다.

## 분리 snapshot 검증

모두 이 worktree에서 오프라인으로 실행했다. 유료 호출, 설치, AI 생성, 원본 앱 재시작은 하지 않았다.

- Python: 원본 `engine/sprite-gen/.venv/bin/python`(3.12.13, pytest 9.1.1)을 재사용하되 `PYTHONPATH=<worktree>:<worktree>/engine/sprite-gen`으로 이 worktree의 `adapters`/`services`/`sprite_gen`이 import됨을 확인했다. `SPRITE_DATA_DIR`은 임시 디렉터리, `PYTHONDONTWRITEBYTECODE=1`.
  - `pytest -q -p no:cacheprovider -W ignore tests/integration/test_frame_selection.py`: 65 passed.
  - `pytest -q -p no:cacheprovider -W ignore tests/integration`: **2385 passed, 1 skipped** (164초). 실패·오류 0.
- Web: 원본 `apps/web/node_modules`의 항목을 이 worktree의 실제 `node_modules` 디렉터리 안에 개별 symlink로 두었다(git 무시, 커밋 안 함). vite/vitest 캐시는 worktree 쪽에 생긴다.
  - `npx vitest run`: 24 files, **445 passed**.
  - `npx tsc -b && npx vite build`: exit 0. guide 생성(prebuild)은 실행하지 않았다.
- 원본 작업 기록의 1771/503 등 수치는 원본 dirty 전체 기준이며 이 분리 검증의 근거로 쓰지 않는다. 실행 앱·브라우저 화면 확인은 이 단계에서 하지 않았다.

## 한계

- 실제 Luna 관찰 품질과 더 새 catalog Luna 선택은 fixture로만 확인했다.
- 원본에서 다른 dirty 기능과 함께 쓸 때의 상호작용은 원본 작업 기록을 따른다. 이 커밋만 HEAD에 얹은 상태는 위 시험 범위에서만 확인했다.
