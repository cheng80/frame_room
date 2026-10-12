> 보관 안내(2026-10-13): 이 문서는 2026-10-12~13 프레임 선별 실험·검수 당시의 기록이다. 여기 적힌 Laya·Jev·관찰 모델 비교 등의 선택지와 실행 방법은 현재 기본이 아니다. 현재 기본은 로컬 Codex catalog의 최신 Luna 관찰과 규칙 판정이며 [FRAME_SELECTION_RULES_CLEANUP_2026-10-13.md](FRAME_SELECTION_RULES_CLEANUP_2026-10-13.md)를 따른다. 시험 수, `output/`·`/tmp` 증거 경로와 작업 ID는 당시 작업 폴더 기준이며 이 저장소에 포함되지 않는다. 키 값과 비밀 파일 해시는 기록하지 않았다.

# 프레임 선별 관찰 보완과 Luna/Sol 관찰 비교 (2026-10-12)

작성: 구현 담당 Claude Opus 5.5 · High (Orca `task_6f288fe4d062`, dispatch `ctx_bae92d94a890`). 검수는 별도 GPT-6.1 Sol · Medium이 맡는다. commit·push·PR·배포는 하지 않았다. 이전 기록은 [구현 기록](FRAME_SELECTION_IMPLEMENTATION_2026-10-12.md)과 [최종 검수](FRAME_SELECTION_FINAL_REVIEW_2026-10-12.md)에 있다. 원자료는 모두 `output/frame-selection-observer-comparison/`에 있다.

## 결과 요약

- **실제 영상에서 교체가 일어났다.** 해적 걷기(구간 18–42, 8장)에서 기본 관찰 모델 `gpt-6-luna`가 F019–F024를 `colour_contamination`으로 reject했고 F025는 keep으로 봤다. 그래서 슬롯 3(0부터 세면 2)의 균등 프레임 F024가 같은 창의 F025로 바뀌었다. 규칙 판정과 Laya MLX 판정 모두 같은 결과다. 슬롯 2(F020–F022)는 깨끗한 이웃이 없어 F021을 유지하고 review로 표시했다.
- **F024 녹색은 키 잔여가 아니다.** 이 영상의 키 색은 magenta다. 녹색·올리브색 부츠는 원본 raw 프레임에도 있다. 배경 제거가 만든 잔여가 아니라 생성 영상 자체의 색 오염이다(`inspection/pirate-F023-F025-raw-vs-keyed-legs.png`). 그래서 `background_residue`가 아니라 새 관찰 항목 `colour_contamination`으로 다룬다.
- **관찰 입력 축소가 누락에 기여했을 가능성이 있다(추론).** 확인된 사실: Codex는 2048px를 넘는 이미지를 줄여 보낸다. v1의 "448px 셀" 시트(939×3824)는 rollout에 503×2048로 기록됐고 셀은 약 234px로 전달됐다. v2에서는 입력 크기와 새 `colour_contamination` 항목·프롬프트를 동시에 바꿨고, 그 뒤 Luna가 F024를 검출했다. 두 변경의 효과를 따로 분리하지 않았으므로 축소가 단독 원인이라고 말할 수는 없다. v2는 개요 1장과 슬롯별 확대 이미지 8장을 보낸다. 확대 이미지는 왼쪽에 기준 그림 `REF` 셀을 두고 후보 셀은 662~720px 높이다. 이번 rollout에는 이미지가 만든 크기 그대로(480×2048, 2000×746 등) 기록됐다.
- **Luna와 Sol 비교(같은 이미지 9장 SHA-256, 같은 프롬프트 파일, 같은 후보·게이트).** Luna는 내 사전 라벨 기준 defect 5/7을 잡았고 clean을 잡은 경우는 해적 0/8, 성직자 0/18이었다. Sol은 해적 defect 7/7을 잡았지만 clean 6/8, 성직자 clean 5/18도 결함으로 봤다. Sol은 해적에서 5개 슬롯, 성직자에서 1개 슬롯을 바꿨다. 사전 표의 clean 판정 수는 확정 오탐 수가 아니다. 독립 검수의 확대 확인에서 F027·F036은 mild 경계로 봤다. 사전 라벨(Opus 시각 판단)과 GPT 검수 라벨 모두 사람 정답이 아니다. 따라서 두 모델의 품질 우열은 단정하지 않는다. 기본값은 사용자 지정대로 Luna이며, 이번 결과는 Sol이 더 많이 지적하고 더 많이 교체한다는 관찰까지만 뒷받침한다. 영상 2개, 모델별 1회 호출이며 일반 정확도로 해석하지 않는다.
- 실제 관찰 호출은 4회다(예산 12회): Luna 2회, Sol 2회. 캐시 hit 4회, 오류·재시도·fallback은 0회다. 실제 모델은 각 rollout의 `turn_context.model`로 확인했다.

## 변경 (이번 증분만, `incremental.diff`)

| 파일 | 내용 |
| --- | --- |
| `adapters/spritegen/frame_selection.py` | v2 관찰 입력: 개요 시트를 긴 변 2048 이내로 맞춤. `detail_sheets`가 슬롯별 확대 이미지를 만든다(REF 셀, 2048×768 이내). 기준 그림에 투명도가 없으면 모서리 단색과 다른 영역으로 자른다. 항목 `colour_contamination`을 추가했다(기준 그림의 같은 부위에 없는 색만, 기준에 있는 색은 제외). 관찰 모델 허용 목록 `OBSERVERS`(`gpt-6-luna-medium` 기본, `gpt-6.1-sol-medium`)는 요청별 인자로만 전달한다. 전역 상수는 바꾸지 않는다. 캐시 키는 보낸 이미지 전체의 순서별 해시와 observer·model·effort로 만든다. 허용 목록 밖 model/effort 조합은 호출 전에 실패한다. `VERSION`과 `PROMPT_VERSION`을 v2로 올렸다 |
| `adapters/spritegen/video_processing.py` | 선택 옵션 `frameObserver`(지정한 경우에만 `select(observer=)`로 전달). 생략한 요청은 형태가 바뀌지 않는다 |
| `adapters/spritegen/video_provider.py` | `frameObserver` 허용. `vision`이 아니거나 허용 목록 밖이면 `VIDEO_SETTING` |
| `apps/web/src/CandidateReview.tsx` | 이유 라벨 1줄 `colour_contamination: 기준과 다른 색 얼룩`. 새 UI 컨트롤은 없다 |
| `tests/integration/test_frame_selection.py`, `apps/web/tests/candidateHistory.test.ts` | 아래 검증 |
| `packages/contracts/VIDEO.md` | v2 관찰 입력, `frameObserver`, 캐시 키 설명 |

유지한 계약: 결함 판정을 코드 색 검출기로 만들지 않았다. 결함 판정은 모델 관찰과 기존 code policy를 따른다(unknown·필드 누락·가장자리 충돌은 review). 균등 프레임이 reject이거나 규칙도 review로 본 경우에만 같은 창의 keep 이웃으로 바꾼다. 교체된 균등 프레임은 슬롯 없는 후보(`uniform-alternative`)로 남긴다. 장수·순서·루프·총 시간 검사와 롤백, `uniform` 기본 경로는 바꾸지 않았다. 모델 fallback, API route 변경, 자동 재호출은 없다.

## 실험 (앱 API 경로, 새 프로젝트)

- 새 프로젝트 `c314768d-2492-4a2e-97b8-fe3676826912` “비교 · 관찰 모델 Luna/Sol 프레임 선별 (2026-10-12)”을 만들었다. 이전 비교 프로젝트의 MP4·기준 그림 사본(원본 프로젝트와 같은 SHA-256)을 업로드했다. 원본: 해적 `여자 해적…/videos/…보존 Grok 원본.mp4`(`90828bce…`), 성직자 `SD 여성 성직자…/videos/…Grok-walk.mp4`(`9a1945d7…`).
- 영상마다 `process_video` 5건(uniform / Luna+규칙 / Sol+규칙 / Luna+Laya / Sol+Laya)을 순서대로 실행했다. 실행 스크립트는 `scripts/run_experiment.py`이며 idempotency key가 고정이라 다시 실행해도 재관찰하지 않는다.
- 앱 재시작: 진행 중 작업 0건(needs_review 15, succeeded 9)을 확인했다. API 프로세스가 `frameObserver` 검증 코드를 캐시하고 있었기 때문이다. `scripts/launch.py --dev`만 SIGTERM으로 종료했다. 같은 환경(`SPRITE_OPEN_BROWSER=0`, 기존 `SPRITE_GEN_DIR`)으로 다시 시작했다(`app-restart.log`). worker는 작업마다 새 하위 프로세스로 코드를 읽는다.

### 해적 (18–42, 8장, 루프 1000ms)

| 변형 | 적용 원본 인덱스 | 변경 슬롯(균등→선택) | review 슬롯 | keep/reject/review | 시퀀스 maxGap / seam(균등 1.02) |
| --- | --- | --- | --- | --- | --- |
| 균등 | 18,21,24,27,30,33,36,39 | — | — | — | — |
| Luna+규칙 | 18,21,**25**,27,30,33,36,39 | 3: 24→25 | 2 | 17/6/0 | 1.333 / 0.944 |
| Luna+Laya | 18,21,**25**,27,30,33,36,39 | 3: 24→25 | 1, 2 | 16/6/1 | 1.333 / 0.944 |
| Sol+규칙 | 18,20,25,26,30,33,37,38 | 2: 21→20, 3: 24→25, 4: 27→26, 7: 36→37, 8: 39→38 | 1, 5, 6 | 5/16/2 | 1.667 / 1.0 |
| Sol+Laya | 18,20,25,27,30,33,37,39 | 2: 21→20, 3: 24→25, 7: 36→37 | 1, 4, 5, 6, 8 | 3/16/4 | 1.667 / 0.96 |

(슬롯 번호는 1부터 센다. 내부 기록 `slot`은 0부터 센다.)

### 성직자 (33–59, 8장, 루프 1083ms) — 건강 데이터 오탐 점검

| 변형 | 적용 원본 인덱스 | 변경 슬롯 | review 슬롯 | keep/reject/review |
| --- | --- | --- | --- | --- |
| Luna+규칙 | 33,36,39,42,46,**48**,52,55 | 6: 49→48 | — | 22/1/0 |
| Luna+Laya | 33,36,39,42,46,**50**,52,55 | 6: 49→50 | — | 21/1/1 (F048 Laya 신뢰도 부족) |
| Sol+규칙 | 33,36,**40**,42,46,49,52,55 | 3: 39→40 | 6, 7 | 13/10/0 |
| Sol+Laya | 33,36,40,42,46,49,52,55 | 3: 39→40 | 1, 6, 7 | 10/10/3 |

성직자는 완전히 깨끗한 데이터가 아니었다. 확대해 보니 F049에 뒤쪽 다리·부츠의 빨강·초록 얼룩이 있었다(사전 라벨 defect). Luna는 이 프레임만 reject했다. Luna가 고른 이웃(규칙 49→48, Laya 49→50)은 둘 다 사전 라벨 mild다. 그래서 **깨끗한 이웃으로의 교체가 증명된 사례는 해적 24→25 하나뿐이다**. 성직자 교체는 결함이 덜한 이웃으로 옮긴 것이며 깨끗함은 증명되지 않았다. Sol은 흰 부츠의 "연녹색 착색"을 10프레임에서 보고했다. 그중 F034·F035·F039·F052·F053은 내 라벨로 clean이다. 이 판단 때문에 슬롯 3의 clean 균등 프레임 F039가 F040으로 바뀌었다.

## 사람 라벨과 정확도 근거

- 사전 라벨: `labels/human-labels-before-experiment.json`. 새 관찰 호출 전에 기록했다. 파일 안의 `recordedAt` 22:00은 잘못 적은 추정값이다. 실제 기록 시각은 파일 mtime 21:57:10이고 첫 실험 작업 생성(21:57:44)보다 앞선다. 원본은 그대로 두고 `labels/human-labels-metadata-correction.json`에 정정을 기록했다. 구현 담당 Claude Opus 5.5의 시각 판단이며 사람 정답 라벨이 아니다. 독립 라벨도 아니다. 범위는 하체·부츠 중심의 색 오염이다. 단계는 defect/mild/clean이고 금색 버클·음영은 clean으로 봤다. 근거 이미지: `inspection/pirate-legs-2x-*.png`, `inspection/cleric-lower-2x-part*.png`, `inspection/preview-*-v2/`.
- **F024: defect.** 오른쪽 부츠 정강이와 발에 올리브색이 있고 F023보다 약하다. raw·키잉 후보·최종 64×128 셀 모두에서 보인다(`replacement/pirate-F023-F025-raw-keyed-final.png`, `inspection/pirate-reference-and-final64x128-slots1-3-uniform.png`). F023은 강한 defect다. **F025는 clean이다.** 두 부츠가 기준 그림처럼 갈색이고 raw·키잉 후보·최종 셀 모두 같다.
- 정량 보조 지표(코드 경로 밖, `scripts/green_share_evidence.py`, `labels/green-share-pirate-keyed.json`): 하체 35%의 불투명 화소 중 갈색이 아니라 올리브색인 화소(R−G<12, G>B+12)를 셌다. F023 169px(2.3%), F024 99px(1.4%), **F025 1px(0.01%)**. F019 2.6~3.6%, F022 5.4%다. 성직자는 금색 장식 때문에 이 지표가 맞지 않아 쓰지 않았다. 이 지표는 판정에 쓰지 않는다.
- 사전 라벨 대비 결과(`comparison.json`의 `observerAgainstLabels`):

| | 해적 defect 검출 | 해적 사전 clean 중 결함 판정 | 성직자 defect 검출 | 성직자 사전 clean 중 결함 판정 |
| --- | --- | --- | --- | --- |
| Luna | 5/7 (F033·F034 놓침) | 0/8 | 1/1 | 0/18 |
| Sol | 7/7 | reject 5/8 (F027·F028·F029·F036·F040) + review 1/8 (F032, extra_or_missing_parts) | 1/1 | 5/18 |

- 사후 확인(라벨 파일은 고치지 않음): Sol이 지적한 F027–F029 "버클 주변 녹색"을 raw에서 4배로 다시 봤다. 버클에 실제로 녹황 tint가 있다(`inspection/pirate-buckle-4x-raw.png`). 그래서 경미한 오염으로 볼 여지가 있다. 나는 F036·F040에서 녹색을 찾지 못했지만, 독립 검수는 F036을 mild 경계로 봤다. 표의 Sol "clean 오탐" 수는 사전 표 기준 집계일 뿐 확정 오탐이 아니다.
- v1 입력 대조(이전 프로젝트, 읽기만 함): 같은 Luna가 v1의 448px 시트에서는 F024를 keep으로 봤다. v2에서는 reject로 봤다. 이번 실험은 영상 하나에 호출 1회라 반복성은 확인하지 않았다.

## 교체 사례 증거 (해적, Luna+규칙)

- 원본 인덱스: 균등 18,21,24,27,30,33,36,39 → 적용 18,21,25,27,30,33,36,39. 8슬롯, `walk`, 루프는 유지했다.
- 슬롯 시간: 균등 125×8 → 125,167,83,125,125,125,125,125. 총 1000ms는 같다. 각 프레임은 자기 원본 시각부터 다음 선택까지 표시되므로 F021(review, 오염 있음)의 표시 시간이 125ms에서 167ms로 늘었다. 교체의 부작용이며 그대로 기록한다.
- 시퀀스 검사: maxGap 1.333(한도 1.75), seam 0.944(균등 1.02). 롤백 없음.
- 대체 후보: F024는 `uniform-alternative`(slot 2, label reject)로 슬롯 없이 등록됐다. 이미지 파일이 있고 사용 횟수는 0이다.
- 재생 파일(`playback/`): GIF 프레임 시간 130,160,90,120,130,120,130,120(10ms 단위 반올림, 합 1000ms), WebP 125,167,83,125,125,125,125,125. 둘 다 8프레임, 무한 루프이고 artifact 표 해시와 일치한다. 전후 비교: `replacement/pirate-strips-before-after.png`, `playback/pirate-uniform-animation.{gif,webp}`, `playback/pirate-luna-rules-animation.{gif,webp}`.
- 저장 검증(`library-verification.json`, `scripts/verify_results.py`): 프로젝트 폴더 `project.sqlite3`를 읽기 전용으로 열었다. revision 15, clip 10개, 각 8슬롯·`walk`·루프다. 원본 인덱스·지속 시간 합(1000/1083ms)·이미지 파일이 있는지·대체 후보가 교체된 균등 프레임과 맞는지, GIF/WebP/strip 해시를 확인했다. 문제는 0건이다. 자동 추천 프레임의 사용자 필드는 모두 `pending`/숨김 아님/사유 없음이다. 저장 실패나 재시도는 없었다.
- Laya MLX 실제 추론(Luna+Laya, 같은 교체): worker 인터프리터, native arm64, Metal, mlx 0.32.3, laya-mlx 0.4.0, checkpoint `047678560251…`로 23건을 0.99초에 판정했다. F018은 Laya가 keep을 신뢰도 0.39로 답해 review로 바뀌었다(균등 프레임 유지). Laya가 규칙보다 나았다는 근거는 없다. 성직자에서는 Laya가 F048(이웃 F049에 결함)을 0.58 reject로 답해 F048 대신 F050이 선택됐다. 이웃 결함 정보가 Laya 판단을 흔든 것으로 보인다.

## 모델 호출 (`model-calls.json`)

전송 경로: `codex exec --ignore-user-config -c model_provider="openai" -c forced_login_method="chatgpt" -c model_reasoning_effort="medium" -m <model> --output-schema`. 구독 경로이므로 금액은 기록하지 않았다.

| # | 영상 | 요청 → 실제(rollout) | effort | 이미지(rollout 기록 크기) | 입력/출력 tokens | 시간 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 해적 | gpt-6-luna → gpt-6-luna | medium | 480×2048 + 1500×746 + 2000×746×7 | 36,963 / 1,228 | 13.3s |
| 2 | 해적 | gpt-6.1-sol → gpt-6.1-sol | medium | 같음 | 36,906 / 1,778 (reasoning 288) | 52.7s |
| 3 | 성직자 | gpt-6-luna → gpt-6-luna | medium | 468×2048 + 1428×746 + 1917×746×7 | 35,582 / 1,189 | 13.8s |
| 4 | 성직자 | gpt-6.1-sol → gpt-6.1-sol | medium | 같음 | 36,222 / 1,791 (reasoning 450) | 56.8s |

- Laya 작업 4건은 모델별 캐시 hit였다(호출 0). 작업 전체 시간은 Luna 28–32s, Sol 68–77s, 캐시 hit 16–22s, 균등 12–16s다.
- 같은 입력 증명(`same-input-proof.json`): 영상마다 네 작업의 보낸 이미지 9장 SHA-256 목록이 같다. 후보 ID 순서·기준 그림 해시·프롬프트 버전·`prompt.txt` 해시(해적 `b1db6908…`, 성직자 `721a0e65…`)·규칙/질문/신뢰도 게이트·균등 인덱스도 같다. 다른 것은 observer와 캐시 키뿐이다.
- Sol의 `note`는 한국어로 나왔다. 형식 검사는 통과했다.

## UI 확인 (ego-browser)

새 TaskSpace 19에서 `http://127.0.0.1:5173`을 열어 새 프로젝트의 Luna+규칙 동작을 확인했다. 확인 후 `finish`로 닫았다. 사용자 창·마우스·Chrome은 쓰지 않았다. 슬롯 3의 후보 확인에 “영상 프레임 선별 · 사용 추천 · 슬롯 3 · 균등 위치 24번 대신 선택 · 판정 규칙 · 관찰 항목 이상 없음”(영상편집-25, 83ms)이 표시됐다. 대체 후보(후보 17, 영상편집-24, 0회 사용)에는 “교체된 균등 프레임 · 슬롯 3의 원래 균등 프레임입니다 · 관찰: 기준과 다른 색 얼룩”이 표시됐다. 저장 상태는 v15 그대로이고 편집은 하지 않았다. 스크린샷: `ui/`.

## 실행한 검증

- `PYTHONPATH=. engine/sprite-gen/.venv/bin/python -m pytest -q tests/integration -p no:cacheprovider -W ignore`: **2406 passed, 1 skipped**(144.4초, `tests/integration.txt`). 실제 Laya checkpoint smoke도 포함된다.
- `tests/integration/test_frame_selection.py` 26 passed. 새로 추가한 3건은 다음을 확인한다. 관찰 모델 허용 목록 검증(API·처리 계층), 요청별 model/effort 전달, 두 observer가 같은 이미지 bytes를 받는지, observer별 캐시 분리와 두 번째 Sol 실행의 캐시 hit, 개요·확대 이미지의 2048/768 한도와 REF 셀, 확대 셀이 개요보다 큰지, 허용 목록 밖 effort 거부. 합성 fixture는 회귀 확인용이며 실사례가 아니다.
- `apps/web`: `npx tsc --noEmit -p .` 통과, `npx vitest run` 503 passed(라벨 assertion 1개 추가), `npm run build` 통과. prebuild 설명서 생성 전후 `public/guide` 해시가 같다(`tests/guide-*.sha256`).
- `git diff --check` 통과. venv freeze는 baseline과 같다(설치·제거 없음). 코드 freeze: `freeze-code.sha256`.

## 데이터 보존 (`preservation-check.json`)

- baseline: `baseline/`(HEAD, git status, 기존 diff, 미커밋 파일 105개 해시, `.data`/`output` 전체 13,553개 SHA-256, 수정 전 코드 사본).
- 종료 대조: 누락 0. 바뀐 기존 파일은 `.data/app.sqlite3`(새 프로젝트 등록·작업 인덱스)뿐이다.
- 투명 기록: `output/frame-selection-laya/app-restart.log`에도 214바이트가 덧붙었다. 이전 앱 인스턴스의 stdout이 이 파일로 연결돼 있었기 때문이다. 내용은 내 UI 라벨 수정의 vite HMR 1줄과 SIGTERM 종료 로그다. baseline 내용이 정확히 앞부분(27,540바이트)과 일치함을 확인했다. 덧붙은 부분은 `previous-app-instance-log-tail.txt`에 보존하고 파일을 원래 길이로 되돌렸다. 해시는 baseline과 같다. 이 파일을 연 프로세스는 더 없다.
- 추가: 새 프로젝트 폴더(파일 2,272개), `.data/cache/frame-selection/` v2 관찰 캐시 4개, 이번 `output/frame-selection-observer-comparison/`뿐이다. 이전 비교 프로젝트 `5f83bfb7…`, 원본 MP4, 이전 clip·검토·숨김 기록은 바뀌지 않았다.
- 미커밋 파일 중 바뀐 것은 위 변경표의 7개다(`incremental.diff`가 baseline 사본과의 차이). `AGENTS.md`·guide·공용 sprite-gen skill은 편집하지 않았다.

## 후속 수정 (검수 P2 두 건, task_c55791efd6b2)

새 관찰 호출 없이 수정했다. 기존 실험 파일·라벨 원본·receipt·10개 clip·원본 데이터는 바꾸지 않았다. 원자료는 `output/frame-selection-observer-comparison/followup/`에 있다(`followup.diff`, `freeze-code.sha256`, `before/` 수정 전 사본, `before-fix-repro.txt`, `related-tests.txt`).

1. **관찰 이미지 크기 한도.** 개요 시트는 높이만 2048로 제한하고 있었다. 그래서 가로로 긴 크롭(480×480 알파 bbox 10,200,470,240, 8행×3칸, REF 없음)에서 6165×2048이 됐다. 이제 셀 높이를 가로·세로 두 한도로 정하고, 반올림 뒤 넘치면 한 칸씩 줄인다. 검수 후속 지적에 따라 모든 이미지의 짧은 변도 768 이하로 맞춘다(고해상도 비전 입력의 짧은 변 한도, `IMAGE_SHORT_EDGE`). 그래서 같은 입력의 개요는 1809×768이 됐다. 크롭 비 2:1에서 1410×2048이던 개요는 768×1216, 4/3에서 915×2048이던 개요는 768×1752가 됐다. 확대 이미지는 반올림으로 폭이 2049(크롭 비 4/3, 3칸)·2050(3/5, 5칸)이 되던 것을 같은 방식으로 2043·2045로 줄였다. 극단적으로 넓은 REF에서 셀 높이 0으로 `ValueError`가 나던 것은 높이를 1 이상으로 두고 REF 폭을 남은 공간 안으로 줄여 막았다. 후보 자체가 극단적인 경우(불투명 5000×2, 8행×3칸)는 셀 높이 1에서도 7512px였다(수정 전 코드에서는 `ValueError`). 이런 경우만 최종 합성 이미지를 한도 안으로 줄여 저장한다(`_save_bounded`, 2048×67). 기록의 `size`는 실제 저장 크기이고, 줄였으면 `downscaledToFit: true`를 남긴다. 줄인 이미지는 해상도가 크게 떨어진다. 관찰이 `unknown`이면 기존 계약대로 review가 된다. 정상 세로 입력은 계산이 같다. 두 실험 영상의 개요 1장·확대 8장을 수정 코드로 다시 만들어 보니 기록된 SHA-256, 프로젝트 폴더 파일, 크기와 모두 같았다(`inspection/fixsize/identity-check.json`).
2. **`frameObserver` 비문자열.** `validate_params`가 `[]`/`{}`를 dict 멤버십 검사에 넣어 `TypeError`(API 500)가 났다. 이제 문자열이 아니면 기존 `VIDEO_SETTING`으로 거절한다. `process_clip`은 기존 `VIDEO_INVALID_PARAMS`, 직접 호출하는 `select`/`observe`는 공용 `_observer`가 `ValueError`로 거절한다. 생략한 요청의 형태와 기본 Luna는 그대로다.

검증: 새 회귀 15건(크기 8가지 경우, 비문자열·미허용 값 7가지)을 추가했다. 크기 회귀는 기록 크기와 실제 저장 크기가 같은지도 확인한다. 수정 전 코드로 같은 입력을 재현해 이전 실패도 확인했다(`followup/before-fix-repro.txt`). 선별·영상·게시 관련 11개 파일 **1797 passed**(54.4초). 정상 실험 이미지는 축소되지 않았다(`downscaledToFit` false, 바이트 동일). `git diff --check` 통과. UI 변경이 없어 웹 검사는 다시 돌리지 않았다. 직전 전체 integration은 2406 passed/1 skipped였다.

실행 중 앱 반영: Uvicorn에 reload가 없어 수정 전 API가 떠 있었다. 진행 중 작업 0건(needs_review 25, succeeded 9)을 확인했다. `scripts/launch.py --dev`만 SIGTERM으로 종료하고 같은 환경(`SPRITE_OPEN_BROWSER=0`, 기존 `SPRITE_GEN_DIR`)으로 다시 시작했다. 새 로그는 `followup/app-restart.log`에 쌓인다. 이전 인스턴스가 종료하면서 이전 로그(`app-restart.log`)에 덧붙인 151바이트는 `followup/app-restart.log`로 옮겼다. 이전 로그는 재시작 직전 크기·해시로 되돌렸다(`followup/prior-log-*`). 그 전까지 앱이 실행 중이라 이전 로그에는 앱 요청 기록이 계속 쌓여 있었다. 다시 시작한 API에 비교 프로젝트로 `frameObserver` `[]`, `{}`, `["gpt-6-luna-medium"]`, `{"gpt-6-luna-medium":1}`, `1`을 보냈다. 모두 **422 `VIDEO_SETTING`**이었고 작업 수(10)와 revision(15)은 바뀌지 않았다. 관찰 호출도 없었다(`followup/api-boundary.json`).

## 남은 한계와 다음 단계

- 근거는 영상 2개, 모델별 호출 1회, Opus 5.5 시각 라벨(사람 정답 아님)이다. 실제 녹색 의상 캐릭터에 대한 오탐은 실영상으로 시험하지 않았다. 회귀 시험은 코드가 색으로 일괄 reject하지 않는다는 것까지만 보장하고 실제 비전 성능은 보장하지 않는다. Luna가 "더 정확하다"는 일반화는 하지 않는다. Luna는 F033·F034 부츠 오염을 놓쳤다. Sol은 사전 clean 프레임도 더 많이 지적했지만 그중 일부는 mild 경계라 확정 오탐이 아니다. 사람 정답 라벨이 없어 우열은 판단하지 않는다.
- 교체로 결함 슬롯 이웃의 표시 시간이 바뀐다(해적 F021 125→167ms). 현재 계약(원본 시각 경계)대로이며 별도 보정은 하지 않았다.
- 슬롯 2(해적 F020–F022)는 같은 창에 깨끗한 후보가 없어 review로 남았다. 선별로는 해결할 수 없고 재생성이나 직접 수정이 필요하다.
- Laya는 이웃 결함 텍스트 때문에 정상 프레임을 abstain/reject하는 경향을 보였다(해적 F026·F038, 성직자 F048). 이 경향은 이번 데이터에서만 확인했다. Laya를 바꾸지는 않았다.
- 관찰 입력은 토큰이 약 1.7배다(v1 약 21k, v2 약 36k). Luna 지연은 13초대로 v1과 비슷하다.
