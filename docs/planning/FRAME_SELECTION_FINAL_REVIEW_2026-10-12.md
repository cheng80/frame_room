> 보관 안내(2026-10-13): 이 문서는 2026-10-12~13 프레임 선별 실험·검수 당시의 기록이다. 여기 적힌 Laya·Jev·관찰 모델 비교 등의 선택지와 실행 방법은 현재 기본이 아니다. 현재 기본은 로컬 Codex catalog의 최신 Luna 관찰과 규칙 판정이며 [FRAME_SELECTION_RULES_CLEANUP_2026-10-13.md](FRAME_SELECTION_RULES_CLEANUP_2026-10-13.md)를 따른다. 시험 수, `output/`·`/tmp` 증거 경로와 작업 ID는 당시 작업 폴더 기준이며 이 저장소에 포함되지 않는다. 키 값과 비밀 파일 해시는 기록하지 않았다.

# FrameRoom 프레임 선별 최종 검수 — GPT 6.1 Sol / medium

검수 시각: 2026-10-12. Task `task_c3ebce56b495`, Dispatch `ctx_290d0fe25633`.
상태: **최종 재검수 완료 — no blocking findings.** 초기 P1/P2 3건은 구현 담당의 최소 수정과 회귀 시험으로 해소됐고 기존 MLX 설치의 sync 보존도 확인했다. 프로젝트 코드·설정·문서 편집, Git publication, 외부 Luna 호출, 모델 설치, 새 실제 영상 생성은 수행하지 않았다.

## 초기 findings 기록 — 모두 수정 재검수 완료

1. **P1 — 모델 초기화 실패 계약 불일치**. `adapters/spritegen/frame_selection.py:493` 부근은 명시 `laya` 예외를 `not decisions`일 때만 실패시킨다. 첫 후보가 code-policy로 review 처리된 뒤 `_laya()`가 MemoryError로 실패하는 경우 명시 laya도 정상 반환하고 backend=laya-mlx/모두 review가 된다. auto도 rules fallback/fallbackReason이 없다. 같은 mock 조건으로 독립 재현했다. 모델 초기화 불가와 프레임별 predict 오류를 나눠 명시 laya 실패, auto rules fallback을 적용해야 한다.
2. **P2 — unknown+defect가 review 정책 우회**. 같은 파일 `policy`의 `if unknown and not defects`에서 unknown과 blur_or_smear=yes가 함께 있으면 `(None, [])`, `rules`는 reject를 반환한다. `VIDEO.md:66` 및 검수 계약의 unknown→review와 다르다. 결함 동반 여부와 무관한 unknown 정책과 회귀 검사가 필요하다.
3. **P2 — 시퀀스 롤백의 슬롯 기록 불일치**. 같은 파일 `select`의 sequence rollback은 chosen/changed만 되돌린다. uniform0=reject→neighbor1=keep→LOOP_SEAM_WORSE 모의 입력에서 최종 chosen0/changedFalse/전체review인데 슬롯0.status=keep/reasons=[]다. 실제 선택 프레임은 reject이고 `video_processing`은 slotStatus=keep로 저장해 UI의 확인 필요 설명을 누락한다. 최종 균등 판정 기준으로 슬롯 상태·이유를 다시 계산하고 sequence 이유를 기록해야 한다.
4. **설치 지속성 한계**. 정상 `scripts/start.sh`는 core import 검사 성공 시 sync하지 않으므로 매번 재시작하면 제거된다는 설명은 틀리다. 하지만 `scripts/setup.sh:9`의 무조건 sync 및 start의 의존성 복구 sync는 optional MLX 패키지를 제거한다. PM이 승인한 최소 opt-in 보존 보완도 재검수 대상이다.

## 최종 수정 재검수

대조 자료: `output/frame-selection-laya/review-fixes.diff`, `review-fixes.md`, `review-fixes-before/sha256-after.txt`, 최신 코드. 첫 `implementation.diff`와 이 후속 diff를 함께 읽어 최종 구현을 검토했다.

- P1 해소: `frame_selection.py:461`부터 모델 초기화가 관찰 전에 이루어지고, 실패 시 명시 laya는 실패하며 관찰0회, auto는 rules/fallback/fallbackReason으로 간다. 최초 후보가 unknown인 경우도 회귀 검사로 통과했다. 프레임별 predict 예외는 계속 review다.
- unknown P2 해소: `frame_selection.py:358`은 known defect가 함께 있어도 unknown을 review로 보낸다. unknown과 observed defect 사유를 모두 남긴다.
- 롤백 P2 해소: `frame_selection.py:522`은 실제 되돌린 슬롯을 최종 균등 판정으로 다시 표시하고 sequence 이유를 기록한다. `video_processing.py:887`의 slotReasons를 통해 게시된 Frame.selectionDecision까지 전달되는 회귀 검사가 통과했다. UI에는 기존 review 설명이 표시되며 세부 slotReasons 문자열은 아직 화면에 따로 표시하지 않는다(비차단 한계).
- 설치 보존 해소: setup/start 복구 sync에 이미 설치된 laya_mlx 감지가 있을 때만 optional pin 파일을 추가한다. 실제 worker venv에서 검수자가 `uv pip sync --dry-run --offline --python engine/sprite-gen/.venv/bin/python engine/requirements.lock.txt engine/requirements-laya-mlx.txt`를 독립 실행해 **Would make no changes**를 확인했다. `bash -n`도 통과했고 builder의 installed=yes/no 네 가지 stub 실행 기록을 검토했다. 실제 setup/sync로 환경을 변경하지 않았다. 새 환경 설치는 기존 opt-in 명령과 checkpoint 준비가 필요하다.
- 최종 수정 Python suite: **22 passed, 1 deselected**, 7.32s. 실제 checkpoint smoke를 제외하고 capability를 offline로 고정해 검수 중 외부 관찰·새 실제 추론을 피했다. 4개 새 회귀 검사와 기존 기본/캐시/시간/보간/라이브러리 검사를 모두 포함한다.
- 정상 uniform을 confidence noise만으로 바꾸지 않는 guard를 별도 mock assert로 직접 통과 확인했다.
- 최종 code SHA 6개는 freeze manifest와 동일하며 원본 데이터10,866개 재대조에서도 app.sqlite3 이외 누락/변경은 없다. Git publication은 없다.

## 독립 확인한 범위

- `AGENTS.md`, 구현 기록과 Laya MLX 검토 문서, VIDEO 계약, 기존 `baseline/worktree.diff`와 이번 `implementation.diff`를 대조했다. 첨부 handoff는 참고로만 읽었으며 이전 Grok 검수는 이번 medium 독립 검수의 대체가 아니다.
- 기본 uniform 및 저장 요청의 생략 호환, frameSelection/frameJudge 옵션의 API 검증·UI 요청·generation/batch/process 공유 호출자, 별도 자동 recommendation UI를 검토했다.
- 주변 disjoint window, 최대32 후보, 관찰 단계 keyed-after-size-hold-and-repair, targetFrameCount 관찰 생략, 타임스탬프 경계와 첫 프레임 이동 시 loop/단발 총시간 보존, phase 회전 시 duration 동반, 선택 인덱스의 보간 계보를 확인했다.
- 관찰 모델은 현재 상수 gpt-6-luna이고 Codex ChatGPT subscription 명령, schema, 외부 API-key/baseURL 및 부모 thread 환경 제거를 확인했다. 관찰 캐시는 시트 실제 bytes·reference bytes·ID 순서·모델·schema·prompt version·effort에 기반하며 judge 변경은 재관찰하지 않는다. 다른 모델 fallback이나 FrameRoom 수준 retry 루프는 없다.
- Laya는 validated observation에서 만든 영어 텍스트만 받는다. pixels는 전달하지 않는다. truncation/options collision/abstention/unknown choice/규칙 keep-reject conflict 및 프레임별 inference 오류는 review로 기록한다. 정상 균등 프레임을 Laya 신뢰도 노이즈만으로 교체하지 않는 guard를 확인했다.
- `selectionDecision`은 review/reviewReason/hidden에 쓰지 않는다. 교체된 균등 프레임은 unused candidate로 등록한다. 일반 result.json 완료 후 publication 재시도는 reuseResultAttemptId로 execute를 건너뛰고 저장만 재시도한다.
- 실제 worker interpreter에서 detection-only capability를 직접 실행: native Darwin arm64 Python3.12.13, Metal available, mlx0.32.3/laya0.4.0, pinned weights SHA 검증 성공. 설치 메타데이터 direct_url의 commit도 9f00d592fcf843753e6d3edd2eab63ec2b44f3c9로 확인했다. FP16 실제 추론은 builder의 앱 작업별 laya 결과·judgeSeconds·checkpoint 기록을 검토했으며 검수에서 새 실제 추론을 요구하지 않았다.

## 데이터·저장 독립 검증

- 사용자 변경 96개 SHA baseline `/tmp/frame-room-frame-selection-user-changes-before.json` 대조: 현재 변경은 승인된 AGENTS.md 역할 수정과 이번 접점에 한정된다. 이전 사용자 코드/문서에 무관한 누락은 발견하지 못했다.
- 원본 `.data`/`output` SHA manifest **10,866개 전부 직접 검사**, missing=0, changed=`.data/app.sqlite3`만. 기존 프로젝트·원본 MP4·기존 클립 파일 hash 변경은 없다.
- 새 비교 프로젝트 `5f83bfb7-a661-4fdc-a495-8a05c6df8dcc` 폴더의 project.sqlite3를 read-only로 다시 열었다. revision15, 10clips/80frames/80occurrences, state=walk, 8슬롯, loop=true, sourceFrameIndex 순서, 모든 imageAsset 파일 및 duration 합(성직자1083ms, 해적1000ms)을 확인했다.
- 폴더 최종 GIF/WebP 20개 실제 full SHA가 artifacts table 및 playback-comparison 기록과 일치한다. 모든 자동추천 프레임 사용자 필드는 pending/hiddenFalse/reviewReason 없음이다.

## 실제 실험·눈 검토

- `experiment/state.json`, job10건, playback-comparison/library-verification, actual project의 성직자·해적 reference/candidate sheet/final-preview와 finished frame, 두 final strip, ego UI screenshots를 직접 확인했다.
- Luna receipts와 해당 실제 session rollout의 turn_context를 독립 대조했다. 총5회(초기5.6 smoke1, 최종6 기준4), 각 answer23frames/schema 존재, error/turn.failed event0이며 실제 model이 각각 일치한다. 초기 smoke는 보존돼 있으며 최종6 결과로 섞어 주장하지 않는다.
- 224px에서 두 영상 모두23keep. 해적448px는 rules18keep/5reject, Laya18keep/4reject/1review로 기록된다. 해적 부츠 녹색 잔여가 눈으로 보이고 F024에 keep false accept가 남아 있다. 정식 사람 라벨·정확도율은 없다. 성직자의23keep도 전면 정확도 인증이 아니다.
- 실제 교체는0건이다. uniform/rules/Laya의 원본 인덱스·슬롯 시간·finished cells·GIF/WebP 해시가 같으므로 **새 재생 품질 개선, 동작 단계 개선 또는 Laya 우월성을 증명하지 못했다**. 검출 정보가 늘어났다는 주장까지만 근거가 있다. 대체 이웃이 불확실할 때 균등 프레임을 유지한 것은 안전 계약에 맞다.
- 관찰은448px keyed/보정 단계이고 결과는64x128 근처의 normalization/finish 단계다. 눈으로 본 최종 프레임은 원본보다 작고 양자화된 결과이며, 관찰 단계만으로 최종 잘림·색/알파를 보증할 수 없다. 실제 이번 결과에서는 새 단계 누락은 없고 결함이 그대로 남는다.
- 출력 container 타이밍도 직접 읽었다. cleric GIF=1080ms(10ms tick 반올림), WebP=1083ms; pirate GIF/WebP=1000ms. uniform과선별이 동일하므로 이3ms 차이는 기존 GIF 표현의 한계이며 선별 회귀가 아니다.
- 합성 fixture는 교체/시간/보간/보존 계약 검증이며 실제 개선 증거로 소개하지 않는다.

## 실제 검수 실행

- Python 선별 suite: 수정 전 **18 passed, 1 deselected**, 수정 후 **22 passed, 1 deselected**(7.32s). 외부 관찰은 fixtures, capability를 offline unavailable로 고정하고 real checkpoint smoke를 제외했다.
- UI 계약 `vitest` videoWorkflow + candidateHistory: **91 passed**, 2files.
- TypeScript `npx tsc --noEmit -p .`: exit0.
- 기존 completed-result publication recovery: **4 passed, 54 deselected**, 5.06s. 실제 실행 경로가 저장 재시도 때 task/provider 실행을 건너뛰는 회귀 검사다.
- `git diff --check`: exit0.
- Builder 기록은 integration2399passed/1skipped, 후속192passed, frontend503passed/build통과라고 보고한다. 검수에서는 이를 독립 재실행한 숫자로 주장하지 않는다. 실제 ego UI screenshot은 저장v15/자동추천과사용자기록분리/선별옵션을 보여 준다. 새 browser는 열지 않았고 다른 TaskSpace/사용자창은 조작하지 않았다.

## 남은 한계

모든 상황의 개선·false accept/reject 비율·Laya 규칙 대비 우월성은 미검증이다. 새 환경의 Laya는 자동 설치하지 않으며 opt-in 설치·checkpoint 준비가 필요하다. 실제 교체가 있는 real-data 사례, 최종 단계 자동 재관찰, 사람 라벨 benchmark, FP32 대비 경계 수치 비교는 없다. maxFrames32 같은 설정은 이웃 후보 여유가 없어 uniform을 유지한다. 관찰 캐시는 프로젝트 외부 공용이므로 폴더 복사에 동반되지 않는다. 새 외부 호출·설치·영상 생성·전체 build·동적 브라우저 재생은 검수에서 실행하지 않았다.
