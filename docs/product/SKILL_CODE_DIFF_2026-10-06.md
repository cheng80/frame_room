# 프레임룸 ↔ sprite-gen v2.34.0 코드 비교

2026-10-06 KST. **최신 스킬은 영상 품질 판정·보간·프롬프트에 추가 보완이 있다. 프레임룸의 프로젝트 관리·저장/복구·검수·출력 계약은 별도 앱 구현이며, 스킬 업데이트만으로 바뀌지 않는다.** 권장 방식은 전용 엔진과 adapter에 필요한 변경을 선별 이식하는 것이다.

이 문서는 비교 결과다. 엔진/UI/API 구현, 사용자 프로젝트, 생성 설정을 변경하지 않았으며 생성 요청·서버 시작·커밋·push를 하지 않았다.

## 비교 기준과 원본 diff

| 대상 | 비교 시점의 실제 코드 |
| --- | --- |
| 프레임룸 | `engine/sprite-gen/`의 v2.12.1 기반 + v2.19 영상 선별 이식 + 로컬 패치, 앱은 `apps/web/`, `services/`, `adapters/`, `alignment/` |
| 설치 스킬 | `/Users/cheng80/.codex/skills/sprite-gen/`, v2.34.0 |
| 공식 배포 | [v2.34.0 릴리스](https://github.com/aldegad/sprite-gen/releases/tag/v2.34.0), 소스 `1fc35090fa9c359bc96d1287fbc32f733acaa7e4` |
| 재개 시 현재 상태 | `git status --short --branch`, `git log -8 --oneline --decorate`. 아래 manifest의 revision은 **비교 당시 기준**이며 ‘최신 커밋’ 고정이 아니다. |

- [실제 엔진 unified diff](comparisons/sprite-gen-v2.34.0/engine.diff): **프레임룸 → v2.34.0** 방향. `sprite_gen/` 아래 Python·curator JS의 모든 차이, 5,841줄. 바로 적용하라는 패치가 아니다.
- [파일별 해시·함수 차이 목록](comparisons/sprite-gen-v2.34.0/inventory.json): 전체 배포 파일의 SHA-256과 top-level Python 함수/class AST 변경 목록.
- [격리 비교 실행 결과](comparisons/sprite-gen-v2.34.0/probes.json): 같은 입력의 축소 결과, cyan 지원, 불량 보간 프레임 채택 정책.

설치 의존성·캐시·빌드 결과·사용자 데이터는 제외했다. 프레임룸은 Git 추적 엔진 파일, 스킬은 공식 release tree에 들어 있는 파일만 비교했다. 앱 파일은 스킬에 대응 파일이 없으므로 엔진 diff의 수에 섞지 않고 실제 호출 경로를 별도로 읽었다.

| 범위 | 동일 | 변경 | 최신 스킬에만 있음 | 프레임룸에만 있음 |
| --- | ---: | ---: | ---: | ---: |
| 전체 배포 파일 | 305 | 66 | 37 | 3 |
| `sprite_gen/` 런타임 전체 | 98 | 28 | 10 | 0 |
| 그중 Python | 62 | 24 | 10 | 0 |
| 테스트·fixture | 126 | 14 | 25 | 3 |

프레임룸 엔진 파일은 총 374개, 스킬은 408개다. ‘변경 파일 수’는 ‘기능 수’가 아니다. 예를 들어 curator JS 4개는 주석/리샘플링 안내 문구 변경이며, `effects/breathe.py`와 `compose/compose_atlas.py`에도 설명만 바뀐 부분이 있다.

## 이미 반영됐거나 동일한 부분

- 영상 5방향, 대각선 걷기의 pin 요청, 방향/무기 유지 문구, 기준 그림 준비, 수동 MP4 가져오기/재처리, RIFE 선택 보정, 기존 동작 길이 맞춤, GIF/WebP/strip/grid 출력은 프레임룸 UI에 연결돼 있다. 최신 CLI의 전체 자동 세트 처리와 동일하다는 뜻은 아니다.
- `video/auto_motion.py`, `video/repair.py`, `video/rife_install.py`, `util/gif_utils.py`, `qa/motion.py`, `gen/xai.py`, `gen/grok_provider.py`, `gen/openai_provider.py`는 **파일 바이트가 동일**하다. 최신 `repair.py` 파일 자체가 바뀌었다고 주장하면 잘못이다. 차이는 호출 순서와 그 하위 `rife.py`·판정 모듈에 있다.
- 프레임룸 `video/loop.py:635`의 `resize_cell()`과 최신 `util/resample.py:43`의 함수는 **AST가 동일**하다. `_support_bounds`, `_window_extrema`도 동일하다. 이미 `finishMode=rgba` 경로에 있는 Hamming 색상/Lanczos 알파 축소를 새 기능으로 다시 넣을 필요는 없다. 최신은 이를 공용 모듈로 옮겨 이미지 추출·curation 변형·scene에도 적용했다.
- 최신 `video.loop`도 `resize_cell`을 import하므로 현재 adapter의 `video.loop.resize_cell` 참조가 즉시 없어지는 것은 아니다. 다만 정식 공용 위치로 바꾸려면 recipe 버전과 기존 출력 회귀를 함께 확인해야 한다.

## 실제 기능 차이: 영상 품질

아래 `video/...`, `gen/...`, `frames/...`는 각 엔진의 `sprite_gen/` 기준이다. 줄 번호는 비교 시점이다. 세부 patch는 위 `engine.diff`에서 함수명으로 찾을 수 있다.

| 항목 | 프레임룸의 현재 동작 | v2.34.0 코드 차이 | 앱 반영 판단 |
| --- | --- | --- | --- |
| 키색 번짐·경계 보호 | 참조의 키색 재질 판정, clip 팔레트 재사용, 영상 가장자리 matte 재계산 | `decide_spill()`은 AST 동일. `video/frames.py:250` → `frames/decontam.py:312`의 `edge_band`로 보호 위치 이동 | **새 spill 해결책은 아님.** 목적은 같고 픽셀 동등성은 미확인. `cutout/extract/decontam` 묶음 이식 필요 |
| 크기 드리프트 | 첫 탐색 실패 시 선형 체고 추세 3% 이상만 보정 (`video_processing.py:408`) | `video/gait_fallback.py:119 cycle_drift()` + `video/loop.py:938`: 반복되는 유사 자세의 높이 비율로 1% 이상 추세를 첫 탐색 전에 보정 | **신규 미연결.** 포즈마다 같은 키로 맞추는 것이 아님. 기존 `motion-auto` 경로와 좌표/앵커를 함께 연결 |
| 확대 보정 시 테두리·잘림 | `gait_fallback.py:66 undo_scale()`의 premultiplied BICUBIC, 원래 캔버스 | `:160 undo_padding()`으로 여백 확보, `:184 undo_scale()`이 공용 `util/resample.py:73 transform_cell()` 사용 | **신규 미연결.** 캔버스 크기와 원본→처리 좌표가 달라짐 |
| RIFE 검은 번짐 | `video/rife.py:133 between()`이 검정 위 premultiplied RGB/알파를 따로 보간 | 최신 `:161 bleed()`가 몸 안쪽 색을 투명 영역까지 확장하고 `:177 between()`에서 사용 | **신규 미반영.** 로컬 RIFE 실행 파일/모델은 같고 입력 픽셀 처리만 변화. 다리 녹음까지 해결되는 것은 아님 |
| 불량 보간 프레임 | `video/align.py:46 resample()`은 중간 결과를 모두 사용 | 최신 `:179 resample(..., between='auto')`, `rife.py:210 smear()`. dark excess >0.001 또는 outline loss >0.05일 때 근접 원본 선택 | **신규 미반영.** 검은 얼룩/윤곽 소실 대신 프레임 반복이 생길 수 있음. `partial_excess`는 측정만 함 |
| 2·3주기 혼입 | 거리·주기 강도·이음새 기반 선택, 앱의 제한적 재탐색 | `video/period.py:137 screen()`, `align.py:631`의 `CycleSuspects`와 명시적 `cycles` 입력 | **신규 미연결.** 실제 걸음 수를 확정하는 검출기가 아니라 의심을 알리고 사용자 확인을 받는 기능 |
| 같은 발로 시작 | `align.py:69 foot_strike_start()`가 몸의 상단이 가장 낮은 순간 사용; 앱은 새 동작만 회전 | 최신 `:314 foot_strike()`가 시점별 보폭/발 깊이/명암을 사용하고 `start_foot=None`, 후보/사유, 수동 `given` 지원 | **신규 미연결.** v2.34의 측면 명암 차이 기준은 0.025. 두 번째 착지는 첫 착지의 반 주기 뒤로 가정하므로 비대칭/사족의 한계 있음 |
| 실제 그림 갱신 빈도 | 영상 프레임 수·시간은 보존하나 그림이 2·3프레임씩 유지되는지 전용 판정 없음 | `video/held.py:81 measure()`, `:116 measure_cycle()`, `align.py:145 retake()`: 13 drawings/s 미만 + 만들지 못한 중간 프레임이 있으면 `held-drawings` 안내 | **신규 미연결.** 경고이며 코드가 자동 재생성하거나 실패시키지는 않음 |
| 후속 흔들림 | 대응 앱 도구 없음 | 신규 `video/follow.py:90 follow_offsets()`, `:163 follow_loop()`가 사용자가 지정한 타원 영역에 감쇠 움직임 추가 | **선택 기능.** 원래 움직임 복구가 아니라 새 픽셀 변형. 원본·변형 출처, 영역 UI, 경계 검수가 필요 |
| 커버/오디오 포함 MP4 | 앱 validation/timing은 `v:0`, 일반 decode는 엔진 기본 선택 | 최신 `video/frames.py:83 probe()`가 cover가 아닌 영상 스트림을 선택하고 `:114 extract()`에 index 전달 | **일부 유틸 이식만으로 부족.** 앱 validation·CFR/VFR decode·timestamp 처리를 같은 stream으로 맞춰야 함 |

`period.verdict()`는 현재 반복 강도로 의심을 판단하고 `pose/steps/follow` 수치는 기록용이다. 정상 대칭 동작도 의심으로 분류될 수 있으므로 ‘자동으로 정확한 한 걸음 확정’으로 소개하지 않는다. `repair_jumps()`는 양쪽 동일하며 최신 `smear()`를 직접 부르지 않는다. 따라서 `between=auto`의 불량 교체 정책은 주기 resample에 적용되는 것이지 모든 보정에 일괄 적용되는 정책이 아니다.

## 실제 기능 차이: 생성·입력·도구

| 항목 | 현재 프레임룸/기반 엔진 | 최신 코드 | 앱 반영 판단 |
| --- | --- | --- | --- |
| 장비가 어느 손/측면에 있는지 | 프리셋과 영상 prompt의 일반적인 ‘좌우 유지’ 문장 | 신규 `gen/handedness.py:101 placement()`, `:204 text()`, `gen/__init__.py:555 _check_view()`: 캐릭터 자신의 좌우를 시점에 맞춰 해석하고 미러링 거절 | **구조화된 `handed` 미반영.** 기준 그림·영상 prompt·검수 입력을 함께 전달해야 함 |
| 장비 위치 검수 | 수동 검수·픽셀 편집 | 신규 `qa/handed.py:220 check()`, `:305 board()`로 색 표시된 장비 위치를 프레임별 검사 | **미반영.** 모든 무기를 의미적으로 식별하는 기능은 아님; marker/region 설정 필요 |
| 사족/무족·복수 개체 | 사람의 팔·골반·양발을 기준으로 한 앱 prompt | 신규 `video/body_plan.py:72 parse_all()`, `gen/prepare.py:827 row_prompt()`, batch prompt의 `biped/quadruped/legless` 전달 | **미반영.** 프롬프트 지원이며 실제 모델 순응/사족 위상 정확성은 별도 검증 |
| 정지 이미지 방향/좌우별 원본 | 앱은 `VideoBasePreset`으로 설명 준비 후 사용자가 생성·선택 | `gen/__init__.py:574 still_prompt()`, `video/batch.py:752 resolve_bases()`: 구조화된 direction·`side@left/right` 원본 | **일부 UI 기능은 이미 있음.** 최신의 구조화 전달·양방향 세트 구성은 미연결. 앱 대각선 prompt는 이미 선택 facing 반영 |
| 정면/후면 보행용 시작 그림 | 앱은 명시적인 1장 생성 버튼으로 준비 | 양쪽 batch runner에 mid-step 재생성이 이미 있음. 최신은 handed/body_plan 추가 | **새 생성 단계 자체는 기존 엔진 기능.** 연결하더라도 추가 이미지 비용을 숨겨서 발생시키지 않아야 함 |
| 프롬프트 조립·충돌 | `video_processing.py:221 build_motion_prompt()`와 프리셋 문자열 append | 신규 `gen/prompt_parts.py:107 Prompt.add()`, `:133 note()`: 일부 handed/키 배경 중복 제거, 영어 방향/상충 지시 경고 | **미연결.** 모든 중복 제거·한국어 충돌 자동 수정 기능으로 보면 안 됨 |
| 단일 이미지 layout guide | 텍스트 여백 지시, identity/style/pose 원본 첨부 | `gen/__init__.py:427`: 안내 이미지로 안전 영역·정수리·바닥선 추가 | **미반영.** 기존 참조 순서·출처/요청 스냅샷을 확장해야 함 |
| 참조 이미지가 있는 투명 생성 | 앱이 투명 PNG를 prompt로 요청하고 원본 그대로 보존; 엔진에는 `transparent=False` | `gen/chroma.py classify_raw_alpha()` + `gen/__init__.py:463`: 실제 반환 alpha가 있으면 자동 chroma 제거를 생략 | **엔진 새 전략이지만 앱 경로는 우회.** 파일 복사만으로 반영되지 않음 |
| 외부 영상 MCP | Grok 로그인 생성 또는 사용자가 MP4 가져오기 | 신규 `video/clip_prompt.py:35 plan_prompt()`가 외부 도구용 prompt/끝 프레임 필요 여부/절차 제공 | **미연결.** 스킬 자체가 MCP를 호출하는 것은 아님; 기존 MP4 가져오기로 결과 수용은 가능 |
| first/last/reference·extend/edit·모델 범위 | 일부 pin은 UI 내부 연결. 별도 끝 이미지/다중 reference/extend/edit는 UI 없음. 앱은 2–6초·480/720p | `VideoRequest`, validation/body, extend/edit는 양쪽 AST 동일. 엔진은 더 넓은 명령/모델별 범위 제공 | **대부분 기존부터 엔진에만 있던 기능.** 최신 버전 추가로 계산하지 않음 |
| 이미지 provider·팔레트·레이어·씬·호흡 | 프레임룸 이미지는 Codex 활성화, Grok/OpenAI 이미지는 비활성화. 나머지는 기존 엔진 유틸과 앱 노출을 구분 | provider/workflow 대부분 동일. 팔레트/레이어/씬/호흡도 이번 신규 기능이 아님 | 필요하면 별도 UI 연동 과제. 다른 provider가 엔진에 존재한다고 자동 과금 경로를 열지 않음 |

## 앱이 실제로 쓰는 경로

```text
VideoStep / VideoBasePreset / VideoBatchPlan
  → videoWorkflow.ts
  → services/api/main.py의 작업 검증·접수
  → services/worker/video_task.py
      → video_provider.py: 로그인·단일 제출·접수 ID/MP4 보존
      → video_processing.py: 앱 전용 추출/구간 선택/보정/길이 맞춤
      → video_normalization.py: 공통 영역·체고 축소
      → video_finish.py: GIF 재현 또는 RGBA 유지
      → 새 asset/frame/clip 저장, 수동 검수 대기
  → alignment/pipeline.py의 확정 bake
  → animation_exports.py + verify_artifacts.py
```

`alignment/pipeline.py:43`과 `adapters/spritegen/video_processing.py:44`는 전용 엔진 경로를 강제한다. 시스템 스킬을 업그레이드해도 프레임룸은 그 코드를 읽지 않는다.

특히 앱은 최신의 `video.run_loop()`·`align_set()`·`video-set` CLI 전체를 호출하지 않는다. `video_processing.py`의 `_select`, `_gait_fallback`, `_repair_selection`, `_align_selected_cycle`이 일부 함수를 직접 연결한다. 따라서 새 모듈 파일을 복사해도 상위 orchestration에만 있는 검사·기본값·보고서가 자동 적용되지 않는다.

## 프레임룸이 별도로 유지해야 할 기능

| 프레임룸 기능 | 실제 소유 코드 | 비교 판단 |
| --- | --- | --- |
| 프로젝트 하나의 폴더/SQLite·전체 이력·리소스 이동 | `services/api/project_folders.py:186`, `:395` | 최신 스킬의 request/curation 파일 기반 run 디렉터리와 다른 저장 계약. 교체 대상 아님 |
| 목록 제거/없는 폴더 정리·저장 보류 복구 | `project_folders.py:238`, `:365`, `:381`, `store.py` | 프레임룸의 프로젝트 인덱스와 outbox 기능 유지 |
| 브라우저 초안·revision 충돌·occurrence별 시간/픽셀 편집 | `apps/web/src/useStudio.ts`, `services/api/edits.py`, `alignment/pipeline.py:435` | 스킬 CLI 기능 유무와 따로 평가해야 함 |
| 확정 bake·최종 PNG/atlas/시간 일치·수동 승인 gate | `alignment/pipeline.py:319`, `alignment/verify_artifacts.py:342` | 최신 스킬에도 출력 도구는 있지만 프레임룸 동일 schema/QA 계약의 대체물이 아님 |
| 채택한 GIF와 동일한 색/알파를 PNG에 저장 | `adapters/spritegen/video_finish.py:15`, `services/worker/video_task.py:102` | 로컬 요구에 따른 마무리. upstream 크기/보간 변경과 독립적으로 보존 |
| cyan 키 제거 | `engine/sprite-gen/sprite_gen/frames/cutout.py:51`, `tests/frames/test_cutout_cyan.py` | 최신 `cutout`에는 없음. 통째 교체 시 회귀 |
| 정합 후 공통 캔버스 초과 방지 | `engine/sprite-gen/sprite_gen/frames/extract.py:2284`, `tests/frames/test_registered_row_cap.py` | 최신에는 `conform_registered_row()` 없음. 엔진 CLI의 로컬 패치이며 앱 raw-crop 경로와 구분해 유지 |
| 생성 원본·영수증·출처 보존, 중복 유료 요청 차단 | `adapters/spritegen/provider.py`, `video_provider.py`, `services/worker/` | upstream 생성 편의 기능으로 덮어쓰지 않음 |

현재 앱 편집/bake는 `alignment/pipeline.py:296`, `:397`의 **nearest** 샘플링 계약이다. 최신 curator의 `transform_cell()`을 적용한다는 이유로 앱 편집 픽셀을 일괄 부드럽게 바꾸면 기존 미리보기/출력 의미가 바뀐다. 필요한 경우 새 선택 모드로 설계해야 한다.

## 직접 확인한 동작 차이

각 엔진을 자기 venv·별도 프로세스에서 import했다. 임시 합성 픽셀을 사용했으며 실제 AI 이미지·영상으로 표시하지 않았다. 생성 호출, RIFE 실행, 사용자 프로젝트 파일 수정은 없다.

| 확인 | 프레임룸 전용 엔진 | 최신 스킬 | 결론 |
| --- | --- | --- | --- |
| 같은 RGBA 32×24 → 13×11 축소 | SHA-256 `c4ce07a2…45ae6` | 같은 해시 | 현재 RGBA 축소 핵심은 이미 동일 |
| `cutout(..., key='cyan')` | `extract:cyan` 성공 | `unknown key 'cyan'` 거절 | 최신 덮어쓰기는 지원 축소를 일으킴 |
| 4→8프레임에서 의도적으로 검은 불량 보간 함수를 주입 | 중간 4장을 모두 채택 | 기본 `between=auto`가 `smear` 4장을 거절하고 원본 근접 프레임 사용 | 최신의 채택 검사 차이를 실행 확인. **실제 RIFE 품질/걷기 개선 실측은 아님** |

## 그대로 이식하면 깨지거나 빠지는 연결

1. **보간 출처가 잘못 기록될 수 있다.** 최신 `align.resample()`은 `made_at`과 `nearest_at`을 나눈다(`video/align.py:179`). 앱 `_align_selected_cycle()`은 `fraction != 0`이면 무조건 `rife-cycle-align`으로 기록한다(`video_processing.py:648–677`). 새 auto fallback이 원본을 고른 경우 실제 선택한 원본 index·시간·`interpolated`·부모 출처를 다시 계산해야 한다. 함수 교체만 하면 픽셀과 출처가 어긋난다.
2. **방향별 같은 발 맞춤이 자동 연결되지 않는다.** 앱은 `align.foot_strike_start(aligned)`만 호출하며 view/발 입력이 없다(`video_processing.py:637`). 최신 `foot_strike()`는 `view`, `foot`, `given`과 판정 불확실성을 사용한다(`video/align.py:314`). 기존 기준 동작 자체의 위상을 유지할지, 사용자 승인 아래 세트 전체를 맞출지도 별도 결정이 필요하다.
3. **걸음 수/정지 프레임 판정이 빠질 수 있다.** 최신 `align_set()`의 cycle screen·held drawings·retake 보고서는 앱의 직접 `resample()` 호출을 우회한다. 새 진단을 오류/검수 대기/안내 중 무엇으로 다룰지 API·UI·작업 결과에 연결해야 한다. `retake`는 자동 유료 재생성 승인으로 해석하지 않는다.
4. **동작 크기 보정의 메타데이터를 같이 바꿔야 한다.** 앱 fallback은 전체 구간의 height/foot affine과 `premultiplied-bicubic`을 기록한다(`video_processing.py:408`). 최신은 대응 포즈의 cycle drift, padding, 분리 resampler를 사용한다. 픽셀 경로와 좌표 변환·앵커·계보를 한꺼번에 갱신해야 한다.
5. **MP4 스트림 선택은 앱의 probe도 맞춰야 한다.** 최신 `video.frames.probe/extract`는 표지 이미지 스트림을 건너뛰고 실제 stream index를 전달한다(`:83`, `:114`). 앱의 `services/api/videos.py:11`, `video_processing.py:290`은 `v:0`, VFR 추출은 `-map 0:v:0`를 사용한다. 엔진만 갱신하면 validation·시간 읽기·decode가 다른 스트림을 볼 수 있다.
6. **컬러 보정 모듈은 묶어서 이식해야 한다.** 최신 `video.frames.key_frames()`는 `cutout(..., decontam_edge_band=4)`를 호출한다. 이 인자가 없는 기존 `frames.cutout/extract/decontam`과 혼합하면 실행되지 않는다. 프레임룸의 cyan 확장과 기존 edge-band 회귀도 유지해야 한다.
7. **단일 생성 호출 계약을 보존해야 한다.** 현재 `gen/__init__.py:314`는 한 번만 호출하지만 최신 `:444`는 `GenTimeoutError` 때 한 번 더 생성한다. 양쪽 batch runner의 429 재시도도 앱의 단일 POST/접수 불명 금지와 다르다. `tests/integration/test_provider.py:151`의 재시도 금지 회귀를 유지한다.
8. **Codex 로그인 경로·실행 증거를 보존해야 한다.** 현재 `gen/codex_provider.py:326`의 사용자 설정 무시, ChatGPT 로그인 강제, API 관련 환경변수 제거, transport prompt/rollout/stdout/stderr 보존은 upstream 실행부에 없는 로컬 패치다. 앱이 계속 `chatgpt-subscription` 영수증을 기록하므로 실행 경로와 기록이 어긋나지 않게 보존한다. `engine-lock.json`과 adapter/pipeline/doctor의 engine pin도 함께 관리한다.

## 권장 적용 순서와 검증 경계

1. **로컬 품질 처리 우선:** RIFE `bleed/smear`, 자동 보간 거절과 정확한 provenance, 대응 포즈 기반 scale drift/여백 보존, 구간/걸음 수 판정. 기존 MP4 복사본으로 재처리해 확인할 수 있다.
2. **방향별 주기 품질:** 좌우 발 판정·불확실 시 수동 지정, 두 주기 혼입 차단, held-drawings 진단을 UI/계약으로 연결한다. 기존 기준 동작과 사용자 타임라인을 몰래 회전하지 않는다.
3. **생성 전 명세:** 장비 좌우/체형/prompt 조립을 승인된 기준·방향별 스틸·영상 요청에 같은 값으로 전달한다. 실제 생성 품질 검증이 필요할 때만 최소 호출한다.
4. **선택 확장:** follow-through, MCP 생성 도구 연결, 영상 extend/edit, 레이어·씬 등의 별도 작업 흐름은 사용자 요구에 맞춰 분리한다.

기존 실제 걷기의 채택 GIF와 28프레임 PNG, 64×128 셀, 전체 1,167ms, 사용자 앵커/수동 승인 상태를 비교 기준으로 유지한다. 새로운 처리가 더 낫다는 판단은 원본/기존 결과/새 결과를 나란히 확인한 뒤 한다. 기본 GIF 모드의 팔레트 처리로 새 차이가 가려질 수 있으므로 마무리 전 RGBA도 비교한다.

이식 후 필요한 회귀는 기존 통합/웹 검증 외에 cyan·정합 캔버스·단일 제출·출처 계보·폴더 저장/복구·같은 bake 출력이다. 새 upstream 테스트만 통과했다고 프레임룸 연결까지 검증됐다고 말하지 않는다. 이번 작업에서는 두 버전의 전체 수용 테스트나 실제 생성 품질 비교를 반복하지 않았다.
