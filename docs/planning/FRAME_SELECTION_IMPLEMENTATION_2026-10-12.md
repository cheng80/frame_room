> 보관 안내(2026-10-13): 이 문서는 2026-10-12~13 프레임 선별 실험·검수 당시의 기록이다. 여기 적힌 Laya·Jev·관찰 모델 비교 등의 선택지와 실행 방법은 현재 기본이 아니다. 현재 기본은 로컬 Codex catalog의 최신 Luna 관찰과 규칙 판정이며 [FRAME_SELECTION_RULES_CLEANUP_2026-10-13.md](FRAME_SELECTION_RULES_CLEANUP_2026-10-13.md)를 따른다. 시험 수, `output/`·`/tmp` 증거 경로와 작업 ID는 당시 작업 폴더 기준이며 이 저장소에 포함되지 않는다. 키 값과 비밀 파일 해시는 기록하지 않았다.

# 후보 프레임 선별 구현·실험 기록

작성: 2026-10-12. 구현 담당 Claude Opus 5.5(`claude-opus-5-5`, `CLAUDE_EFFORT=high` 확인). 검토 문서 [FRAME_SELECTION_LAYA_MLX_REVIEW_2026-10-12.md](FRAME_SELECTION_LAYA_MLX_REVIEW_2026-10-12.md)와 초기 검수 조건을 반영했다. 계약은 [VIDEO.md의 후보 프레임 선별](../../packages/contracts/VIDEO.md#후보-프레임-선별-2026-10-12-선택-기능)에 있다. commit·push·배포는 하지 않았다.

## 결과 요약

최종 상태: 사용자 지시에 따라 검수 모델을 **GPT-6.1 Sol · Medium**으로 변경했다. Orca `run_216cd4fd9ce6`에서 구현(`task_4be05707dbd3`)과 검수 지적 수정(`task_48cf04f608ff`)은 Opus 5.5 High, 독립 최종 검수(`task_c3ebce56b495`)는 GPT-6.1 Sol · Medium이 담당했다. 초기 P1/P2 3건과 기존 MLX 설치의 sync 보존 문제를 수정하고 재검수해 **no blocking findings**로 완료했다. [최종 검수 기록](FRAME_SELECTION_FINAL_REVIEW_2026-10-12.md), 수정 diff·보고서는 `output/frame-selection-laya/review-fixes.diff`와 `review-fixes.md`에 보존했다. 수정 후 관련 Python 185건이 통과했으며 검수자는 선별 22건·UI 계약 91건·저장 재시도 4건과 설치 dry-run을 독립 확인했다. 실제 영상에서의 슬롯 교체·품질 개선·Laya 우월성은 입증하지 못했다.

- 기존 균등 샘플링이 기본값이다. `frameSelection: vision`을 고른 경우에만 균등 위치 주변 후보를 코드 측정 → `gpt-6-luna` 관찰(캐시) → 규칙 또는 Laya MLX 판정 → 시퀀스 검사로 고른다. 출력 장수·순서·루프·총 재생 시간은 유지한다.
- 실제 기존 Grok 걷기 영상 2개(성직자, 해적), 각 23개 후보로 실험했다. Luna 호출은 총 5회다(한도 8, 재시도 없음). 두 영상 모두 **실제 슬롯 교체는 0건**이다. 해적 영상은 448px 시트에서 슬롯 2의 후보 19~23 전부에 녹색 키 잔여가 관찰되어 균등 프레임을 유지하고 슬롯을 review로 표시했다. 대체 가능한 깨끗한 이웃이 없는 결함이므로 선별로 해결할 수 없다는 판단이 기록됐다.
- 균등·관찰+규칙·관찰+Laya 결과의 재생(셀 해시, 슬롯 시간, GIF/WebP 해시)은 모두 같다. 차이는 프레임별 추천 기록과 review 표시뿐이다.
- Laya zero-shot은 그대로 쓰기 어려웠다. 첫 질문 형식(v1)은 결함 프레임도 keep으로 답했다. 결함을 영어 목록으로 주는 v2에서는 정상 keep 0.89, 잘림+흐림 reject 0.81로 나아졌다. 그래도 `unknown`은 keep으로 답하므로 코드 정책이 먼저 review로 보낸다. 실험에서 Laya와 규칙의 슬롯 결과는 같았다. Laya가 규칙보다 나은 점은 아직 확인하지 못했다.

## 변경 파일

구현 diff(기존 미커밋 변경을 기준으로 한 이번 변경만): `output/frame-selection-laya/implementation.diff`.

| 파일 | 내용 |
| --- | --- |
| `adapters/spritegen/frame_selection.py` (신규) | 후보 창, 측정, 시트, Codex 관찰·캐시, 규칙/Laya 판정, 슬롯 선택, 시퀀스 검사, worker 인터프리터 감지 |
| `adapters/spritegen/video_processing.py` | `frameSelection`/`frameJudge` 옵션, 균등 인덱스 직후 선별 연결, 표시 경계 함수, 교체된 균등 프레임 보존(`alternateFrames`) |
| `adapters/spritegen/video_provider.py` | 선택 필드 검증(생략 시 기존 형태 유지), 주기 맞춤 병용 거부, capability `frameSelection` |
| `services/worker/video_task.py` | 관찰 캐시 위치 전달, 대체 후보 등록(슬롯 없음), `selectionDecision` 기록, FPS·출력 장수를 슬롯 기준으로 계산 |
| `apps/web/src/{types,videoWorkflow}.ts`, `VideoStep.tsx`, `CandidateReview.tsx`, `CandidateLibrary.tsx` | 선별 사용·판정 선택, worker backend/불가 사유, 후보별 추천·이유 표시 |
| `tests/integration/test_frame_selection.py` (신규), `apps/web/tests/{videoWorkflow,candidateHistory}.test.ts` | 아래 검증 |
| `packages/contracts/VIDEO.md`, `engine/requirements-laya-mlx.txt` (신규) | 계약, 선택 설치 pin |

## 설치와 pin

- worker 인터프리터 `engine/sprite-gen/.venv/bin/python`(native arm64, Python 3.12.13, macOS 26.7, Apple M4)에 `uv pip install`로 `laya-mlx @ git+https://github.com/mizorewww/laya-mlx@9f00d592fcf843753e6d3edd2eab63ec2b44f3c9`(0.4.0)를 설치했다. 함께 `mlx 0.32.3`, `mlx-metal 0.32.3`, `huggingface-hub 1.33.0`, `tokenizers 0.23.3` 등 13개 패키지가 **추가만** 됐고 기존 패키지 버전 변경은 없다(`output/frame-selection-laya/baseline/venv-freeze-before.txt`, `venv-freeze-after.txt`).
- 가중치: `aac6fef/laya-mlx` revision `047678560251f28113ee8f5df4be82102c7bf336`을 `.data/tools/laya-mlx/<revision>`에 받았다. `model.safetensors` 실제 SHA-256 `b9c07bf14be2fa5c78a9193a3e6d840ac80e89e62fc40f425834c3d8a6eaa3de`는 포트 게시 기록(`benchmarks/results/hub-publication.json`의 `weight_sha256`)과 같다. capability 감지도 이 해시를 확인한다.
- `mlx.core.metal.is_available()` True, `default_device()` gpu. 실제 판정 23건 1.4~2.5초(warm), 가중치 로드 약 0.3초.
- 설치 유지: `engine/requirements-laya-mlx.txt`는 실제 설치된 13개 패키지를 모두 고정한다. `scripts/setup.sh`와 `scripts/start.sh`의 복구 `uv pip sync`는 venv에 `laya_mlx`가 이미 있을 때만 이 파일을 함께 넣는다. 그래서 설치·복구 후에도 Laya가 남는다(오프라인 dry-run: lock만이면 13개 제거, 함께 넣으면 변경 없음). 설치하지 않은 환경과 다른 플랫폼은 기존처럼 lock만 sync한다. 새 환경에서는 파일 안의 opt-in 설치 명령을 쓴다. 설치가 없으면 감지가 불가 사유를 표시하고, `auto`는 규칙 판정으로 넘어간다.

## 실제 Luna 호출

전송 경로: `codex exec --ignore-user-config -c model_provider="openai" -c forced_login_method="chatgpt" -m <model> --output-schema`. API 키·base URL·부모 thread 환경변수는 제거했다. 실제 모델은 각 세션 rollout의 `turn_context.model`로 확인했다. 원문 증거는 `output/frame-selection-laya/luna-calls.json`과 각 `observation/` 폴더에 있다.

| # | 모델(실제) | 대상 | 입력/출력 tokens | 시간 | 비고 |
| --- | --- | --- | --- | --- | --- |
| 1 | gpt-5.6-luna | 성직자 224px 시트 | 20,188 / 1,173 | 9.2s | 최초 smoke. 이후 사용자 지시로 모델 전환. 증거 보존 |
| 2 | gpt-6-luna | 성직자 224px | 21,221 / 1,050 | 25.4s | gpt-6-luna smoke. 앱 작업 2건이 캐시 hit |
| 3 | gpt-6-luna | 해적 224px | 22,058 / 1,051 | 24.5s | 앱 작업 1건 호출, 1건 캐시 hit |
| 4 | gpt-6-luna | 해적 448px | 21,303 / 1,302 | 13.8s | 해상도 탐침. 앱 작업 2건이 캐시 hit |
| 5 | gpt-6-luna | 성직자 448px | 21,404 / 1,051 (cached 11,008) | 10.9s | 앱 작업 1건 호출, 1건 캐시 hit |

오류·재시도·다른 모델 fallback은 0회다. 새 영상 생성이나 이미지 생성은 하지 않았다. 구독 경로라 금액은 기록하지 않았다.

224px 시트에서는 두 영상 모두 결함 0건이었다. 해적 영상을 확대해 직접 보니 부츠에 녹색 키 잔여가 있었다(`F019`~`F024`). 448px 시트로 다시 관찰하자 19~23에서 `background_residue`를 보고했다. 24는 여전히 놓쳤다. 입력 tokens는 거의 같아 기본 셀 높이를 448px로 바꿨다. 이 비교는 영상 1개의 결과이며 일반 정확도로 해석하지 않는다.

## 비교 실험(앱 작업 경로)

재시작한 실행 중 앱 API로 새 비교 프로젝트 `5f83bfb7-a661-4fdc-a495-8a05c6df8dcc`(“비교 · 프레임 선별 균등/관찰+규칙/관찰+Laya (2026-10-12)”)를 만들었다. 기존 MP4와 기준 그림 사본을 등록한 뒤 `process_video` 10건을 실행했다. 기존 프로젝트는 읽기만 했다. 원자료: `output/frame-selection-laya/experiment/`(`state.json`, 작업 JSON, `playback/`, `playback-comparison.json`, `library-verification.json`).

| 영상 | 구간·출력 | 변형 | 상태 | 판정 수 keep/reject/review | 교체 |
| --- | --- | --- | --- | --- | --- |
| 성직자 | 33–59, 8장, 1083ms, 루프 | 균등 / 관찰+규칙 / 관찰+Laya (224·448) | uniform-kept | 23/0/0 | 0 |
| 해적 | 18–42, 8장, 1000ms, 루프 | 균등 / 224 규칙·Laya | uniform-kept | 23/0/0 | 0 |
| 해적 | 동일 | 448 규칙 | review | 18/5/0 | 0, 슬롯 2 확인 필요 |
| 해적 | 동일 | 448 Laya | review | 18/4/1 (23은 Laya 신뢰도 부족) | 0, 슬롯 2 확인 필요 |

- 시퀀스 검사: 성직자 최대 간격 1.231배, 이음 비율 1.167(균등과 같음). 해적 1.0배, 1.02. 경고는 없다.
- 재생 비교: 10개 동작 모두 균등 기준과 원본 인덱스·슬롯 시간·셀 SHA-256·미리보기 GIF/WebP 해시가 같다.
- 라이브러리 저장: 앱 작업 게시 트랜잭션과 프로젝트 폴더 반영 후 폴더의 `project.sqlite3`를 읽기 전용으로 다시 열었다. 10개 clip 모두 8슬롯, 동작 `walk`, 루프, 지속 시간(1083/1000ms), 원본 프레임 번호와 이미지 연결을 확인했다(revision 15).
- 지연: 작업 전체 14~40초. 관찰 미스는 Luna 11~25초를 포함하고, 캐시 hit는 16~22초다. Laya 판정 23건은 1.4~1.9초다.
- 사람 라벨링, false accept/reject 비율, 비전 직접 판정 비교군은 이번 범위에서 하지 않았다. 해적 448 결과의 false accept 1건(24)은 직접 확대해 본 판단이다.

## UI 확인(ego-browser)

새 TaskSpace 18에서 `http://127.0.0.1:5173`을 열어 확인한 뒤 종료했다. 사용자 창·마우스, Chrome은 사용하지 않았다. 스크린샷: `output/frame-selection-laya/ui/`.

- 3단계 기존 영상 처리에 `영상 프레임 선별`(기본 균등)과 `선별 판정`이 표시된다. `작업 처리기 판정: Laya MLX · metal · arm64` 안내도 나온다. 확인 후 선택값을 균등으로 되돌렸고 추출 버튼은 누르지 않았다.
- 4단계 후보 목록에는 `영상 선별 · 사용 추천/제외 제안`이 보인다. 후보 확인 탭에는 “제외 제안 · 슬롯 2 · 균등 위치 유지 · 확실한 대체 후보가 없어 확인 필요 · 판정 규칙 · 관찰: 배경 잔여”가 나온다. 저장 상태 v15는 그대로이며 초안 변경은 없다. 슬롯 교체에는 기존 `선택 슬롯을 이 후보로 교체`를 사용한다. 새 승인 관문은 없다.

## 실행한 검증

- `PYTHONPATH=. engine/sprite-gen/.venv/bin/python -m pytest -q tests/integration -p no:cacheprovider -W ignore`: 2399 passed, 1 skipped(최종 코드, 149.7초).
- `tests/integration/test_frame_selection.py` 19 passed. 합성 영상과 가짜 관찰기만 사용하며 실제 Laya checkpoint smoke 1건은 설치 환경에서 실행된다. 검사 범위: 기본·uniform 동일성, 요청 형태 유지·잘못된 값 거부, 후보 창 순서·상한, 장수 과다 시 관찰 생략, 첫 슬롯 교체의 루프·단발 총시간 보존과 대체 후보, VFR 경계, 잘못된 JSON·ID·중복·필드 누락·unknown → review, 캐시 hit·기준 변경 분리·손상 무시·실패 미저장, codex 명령의 모델·구독 경로·환경 제거, Laya 잘림·선택지 충돌·abstention·예외·규칙 불일치 → review, 명시 Laya 불가 실패와 auto 규칙 대체, 주기 맞춤 경로 관찰 생략, 보간 계보가 선택 인덱스를 따름, 시퀀스 간격 검사, 작업 게시 시 사용자 review 필드·기존 clip 불변과 대체 후보 무슬롯 등록, 재실행 시 재관찰 없음.
- `apps/web`: `npx tsc --noEmit -p .` 통과, `npx vitest run` 503 passed, `npm run build` 통과. prebuild 설명서 생성 전후 `public/guide` 해시가 같다.

## 최종검수 지적 수정 (2026-10-12)

수정 diff `output/frame-selection-laya/review-fixes.diff`, 보고 `output/frame-selection-laya/review-fixes.md`.

- `unknown`이 있으면 결함이 함께 관찰돼도 reject가 아니라 review다(`UNKNOWN:*` + `OBSERVED:*`).
- Laya 모델 초기화는 관찰 전에 한다. 실패하면 명시 `laya`는 작업 실패(Luna 호출 없음), `auto`는 규칙 판정과 `fallbackReason`을 기록한다. 개별 예측 오류·잘림은 판정 모드와 관계없이 review다.
- 시퀀스 검사로 균등 위치로 되돌린 슬롯은 균등 프레임 판정으로 상태를 다시 계산한다. 사유(`SEQUENCE_REVERTED_UNIFORM_KEPT`, `SEQUENCE:*`)는 `frame.selectionDecision.slotReasons`에 저장된다.
- 검증: `test_frame_selection.py` 23 passed(신규 4), 관련 영상 처리·작업 시험 포함 185 passed. 전체 2399 재실행과 frontend 검사는 하지 않았다(UI 변경 없음).

## 데이터 보존

- 시작 시점 기준: `output/frame-selection-laya/baseline/`(HEAD, git status, 기존 diff, 미커밋 파일과 `.data`/`output` 전체 SHA-256 manifest 10,866개).
- 종료 시 manifest 대조: 기존 `.data`·`output` 파일 중 바뀐 것은 앱 인덱스 `.data/app.sqlite3` 하나다. 새 프로젝트 등록과 작업 기록 때문이다. 기존 5개 프로젝트 폴더와 원본 MP4·자산은 그대로다. 추가된 것은 새 비교 프로젝트 폴더, `.data/cache/frame-selection/`, `.data/tools/laya-mlx/`, `output/frame-selection-laya/`뿐이다.
- 미커밋 파일 96개 중 바뀐 파일은 위 변경표의 8개와 `AGENTS.md`다. `AGENTS.md`는 21:00에 외부에서 수정됐고(검수 역할 변경) 구현 worker는 편집하지 않았다. 8개 파일은 `implementation.diff` 기준으로 이번 변경만 추가·대체됐다.
- 앱 재시작: PM 승인 후 진행 중 작업이 없음을 확인했다. `scripts/launch.py --dev`만 SIGTERM으로 종료하고 같은 설정에 `SPRITE_OPEN_BROWSER=0`을 주어 다시 시작했다(로그 `output/frame-selection-laya/app-restart.log`). 다른 프로세스는 건드리지 않았다.

## 남은 한계

- 실제 교체가 일어난 실데이터 사례는 없다. 교체 경로는 합성 fixture 시험으로만 확인했다. 두 영상 모두 결함이 없거나, 결함이 이웃 후보 전체에 퍼져 있었다.
- Luna는 448px에서도 일부 잔여(24)를 놓쳤다. 신체 이상·외형 불일치 실데이터 사례는 없었다. 판정 품질에는 사람 라벨이 필요하다.
- Laya 신뢰도 0.6은 보정하지 않은 zero-shot 값이다. 이번 데이터에서는 규칙 판정과 차이가 없었으므로 채택 근거가 아직 없다. 규칙만으로 충분할 가능성이 높다.
- 출력 슬롯 수 대비 후보 상한(32) 때문에 기본 32장 같은 동작은 이웃 후보가 없어 균등을 유지한다. 주기 맞춤(`matchClipId`)과는 함께 쓸 수 없다.
- 관찰 캐시는 앱 데이터 폴더의 공용 캐시다. 프로젝트 폴더 복사에는 포함되지 않는다(다시 관찰하면 된다).
