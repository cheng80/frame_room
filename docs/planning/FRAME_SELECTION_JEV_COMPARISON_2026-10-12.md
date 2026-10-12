> 보관 안내(2026-10-13): 이 문서는 2026-10-12~13 프레임 선별 실험·검수 당시의 기록이다. 여기 적힌 Laya·Jev·관찰 모델 비교 등의 선택지와 실행 방법은 현재 기본이 아니다. 현재 기본은 로컬 Codex catalog의 최신 Luna 관찰과 규칙 판정이며 [FRAME_SELECTION_RULES_CLEANUP_2026-10-13.md](FRAME_SELECTION_RULES_CLEANUP_2026-10-13.md)를 따른다. 시험 수, `output/`·`/tmp` 증거 경로와 작업 ID는 당시 작업 폴더 기준이며 이 저장소에 포함되지 않는다. 키 값과 비밀 파일 해시는 기록하지 않았다.

# 프레임 선별 Jev(TypeSafe) 실비교 (2026-10-12)

작성: 구현 담당 Claude Opus 5.5 · High (Orca `task_5b7d789c8662`, dispatch `ctx_174be28e743a`). 검수는 별도 GPT-6.1 Sol · Medium이 맡는다. commit·push·PR·배포는 하지 않았다. 준비 기록은 [Jev 준비](FRAME_SELECTION_JEV_PREPARATION_2026-10-12.md)에 있다. 원자료는 `output/frame-selection-jev/`에 있다.

## 결과 요약

- **실제 Jev 호출은 2회다(예산 2).** 영상마다 POST 1회에 질문 23개를 묶어 보냈다. 요청·실제 모델은 둘 다 `jev-1.13.0`이고 HTTP 200이다. 자동 재시도·fallback은 0회다. Luna 새 호출은 0회다(관찰 캐시 hit, `observationCacheOnly`). Laya 재추론, 새 영상 생성, 설치도 없었다.
- **해적 F024→F025 교체가 Jev 판정에서도 일어났다.** Jev는 F024를 reject(confidence 1.0), F025를 keep(1.0)으로 답했다. 새 프로젝트의 라이브러리에는 슬롯 3에 F025가 저장됐고, F024는 슬롯 없는 대체 후보(사용 0회)로 남았다. 적용 인덱스는 18,21,**25**,27,30,33,36,39다. GIF·WebP·strip 바이트는 기존 Luna+규칙, Luna+Laya 클립과 **완전히 같다**.
- **성직자는 49→50으로 Laya와 같고 규칙(49→48)과 다르다.** Jev가 F048을 keep 0.48로 답했고 confidence 0.22라 review가 됐다. 그래서 같은 창에서 F050이 선택됐다. 재생 바이트도 Luna+Laya 클립과 같다.
- Jev가 규칙과 다르게 본 프레임은 5개다(해적 F018·F040, 성직자 F033·F048·F056, 전부 Jev review이고 규칙은 keep). Jev review 수는 해적 2, 성직자 3이고 규칙 review는 0이다(`experiment/comparison-*.json`의 `counts`). 5개 중 4개는 후보 풀의 **처음·끝 프레임**이고 1개(F048)는 결함 이웃(F049) 옆 프레임이다. 처음·끝 프레임의 `_state`(Laya와 같은 상태)에는 이웃 결함이 `"unknown"`으로 들어간다. 이 값은 관찰 결과가 아니라 상태를 만드는 방식에서 생긴다는 점은 코드 사실이다. 이 값과 review가 함께 나타나는 관련은 관찰됐다. 하지만 원인을 분리하는 실험은 하지 않았다(아래 참고). 규칙이 reject한 7개는 Jev도 모두 reject(1.0)였다.
- 사람 정답 라벨이 없다. 그래서 Jev·Laya·규칙의 우열이나 "전부 clean"은 주장하지 않는다. Jev는 텍스트만 받는다. 따라서 Luna가 놓친 결함(해적 F033·F034 부츠)을 Jev가 직접 찾을 수는 없다. 이번 비교는 **같은 관찰 위에서 판정만 바꾼 결과**다.

## 이번 task의 코드 변경 (`followup/followup.diff`, 동결 `freeze-code.sha256`)

1. **P1 (검수 지적): 키 형식 검증과 헤더 오류 숨김.** `typesafe_judge._key_ok`는 ASCII 출력 문자만 허용한다. 공백·CR/LF·탭·NUL·DEL·비ASCII는 거절한다. 거절되면 다음과 같이 처리한다.
   - capability: unavailable, 사유에 키 값을 넣지 않는다.
   - `evaluate`: `JEV_KEY_INVALID`, POST하지 않는다.
   - `select`: 관찰 전에 `VIDEO_FRAME_JUDGE_UNAVAILABLE`.
   - 전송 중 `ValueError`(예: `http.client`가 헤더 값을 인용한 메시지): 고정 코드 `JEV_REQUEST_REJECTED`로 바꾼다. 이 오류는 예외 처리 블록 밖에서 다시 던진다. 그래서 `__cause__`와 `__context__`가 없고, str·repr·traceback 어디에도 키가 남지 않는다.

   회귀 8건을 추가했다. 잘못된 키 7종과, 실제 `http.client` 경로의 CR/LF 거절을 확인하는 1건이다. 이 1건은 socket 연결이 일어나면 테스트가 실패하도록 막아 두었다. Jev 파일 44 passed, `test_frame_selection`+Jev+`test_video_jobs` **106 passed**(`followup/related-tests.txt`). 기존에 고친 빈 프로세스 값 우선, 합 공차 1e-3, 큰 정수 처리, vision guard는 그대로다.
2. **실행 전 러너 수정(제품 코드 아님).** `run_jev_comparison.py --live`가 `/v1/providers` 응답을 리스트로 다뤘다. 실제 응답은 `{"providers":[...]}`이므로 프로젝트·POST 전에 `AttributeError`가 났다. 한 줄만 고쳤고 PM에 보고했다(`msg_248e585c1116`). 이 시점의 호출은 0회였다.

## 앱 재시작

- 진행 중인 작업이 0건임을 확인했다(needs_review 25, succeeded 9). 내가 알던 인스턴스 `scripts/launch.py --dev`(pid 76186, 22:25:50 시작)만 SIGTERM으로 종료했다. 같은 환경(`SPRITE_GEN_DIR=~/.codex/skills/sprite-gen`, `SPRITE_OPEN_BROWSER=0`)으로 다시 시작했다. 사용자 창은 열지 않았다. 키를 환경 변수로 넘기지 않았다. worker는 판정 직전에 루트 `.env`만 읽는다.
- 새 stdout은 `output/frame-selection-jev/live/app-restart.log`에 쌓인다. 이전 로그 `output/frame-selection-observer-comparison/followup/app-restart.log`에는 종료 로그 151B(428,383→428,534B)가 덧붙었다. 지시대로 지우지 않았다(`live/prior-log-*.txt`). 재시작 뒤 API는 judges `auto/rules/laya/jev`를 제공했고 jev는 available이었다.

## 실험 (`run_jev_comparison.py --live`, 2026-10-13 00:00:02–00:00:33 KST)

작업은 2026-10-12에 시작했다. 문서 이름과 프로젝트·idempotency 이름의 날짜는 그대로 둔다. 실제 실험은 자정을 넘긴 2026-10-13 KST에 실행됐다.

- 새 프로젝트 `28dbc952-3849-428a-bef4-b566d0f9ffb2` “비교 · Luna 관찰 + Jev 판정 (2026-10-12)”을 만들었다. 이전 비교 프로젝트 `c314768d…`의 영상·기준 그림을 읽기만 했고 그 bytes를 올렸다. 해적 `90828bce…`/`3990e5a2…`, 성직자 `9a1945d7…`/`a9dda944…`이며 원 프로젝트 `5f83bfb7…`과 같은 SHA다.
- 영상마다 `process_video` 1건을 실행했다(`frameJudge:"jev"`, `frameObserver:"gpt-6-luna-medium"`, `observationCacheOnly:true`, idempotency `jev-comparison-2026-10-12-{pirate,cleric}-luna-jev`). 둘 다 `needs_review`다. 작업 시간은 14.1s/16.1s다.
- **같은 관찰 증명:** 관찰 캐시 키는 해적 `52ffc6259d4c…`, 성직자 `0d94d02fc1f2…`로 Luna+규칙·Laya 작업과 같다. 두 작업 모두 `cacheHit: true`, `calls: 0`이다. 보낸 관찰 이미지 9장의 SHA 목록도 같다. Jev state·questions SHA는 dry-run 미리보기와 같다(해적 `27e578b4…`/`131e5af5…`, 성직자 `749ef7a1…`/`6e0f1f2b…`).

### Jev 호출 기록 (`live/model-calls.json`, 원 응답 `evidence/*-jev-cache-*.json`)

| 영상 | 요청→실제 모델 | HTTP | 질문 | input/output tokens | 지연 | 판정 단계 시간 (Laya 비교) |
| --- | --- | --- | --- | --- | --- | --- |
| 해적 | jev-1.13.0 → jev-1.13.0 | 200 | 23 | 4,502 / 877 | 0.250s | 0.252s (Laya 0.988s, 규칙 0.0s) |
| 성직자 | jev-1.13.0 → jev-1.13.0 | 200 | 23 | 4,382 / 877 | 0.224s | 0.225s (Laya 1.138s) |

예상하지 못한 답변 id는 0, 형식 오류도 0이다. 비용은 [공식 모델 문서](https://docs.typesafe.ai/models)의 단가($0.042/Mtok input)로 계산하면 약 $0.00037다(추정, 청구서로 확인하지 않음). 원 응답 캐시 파일에는 답변·사용량·요청 재료만 있고 키·헤더는 없다(`TYPESAFE`/`Bearer`/`Authorization` 문자열 0건).

### 판정 비교 (같은 Luna 관찰, 코드 정책 결정 0건, 23후보 모두 Jev 질문)

| 영상 | 규칙 keep/reject/review | Laya | Jev | 적용 인덱스 (규칙 / Laya / Jev) | review 슬롯 (Jev) |
| --- | --- | --- | --- | --- | --- |
| 해적 | 17/6/0 | 16/6/1 | 15/6/2 | 18,21,25,… 셋 다 같음 | 1 (F018), 2 (F021 reject, keep 대체 없음) |
| 성직자 | 22/1/0 | 21/1/1 | 19/1/3 | …,46,**48**,… / …,46,**50**,… / …,46,**50**,… | 1 (F033) |

규칙과 Jev가 다른 프레임(전부 Jev review, 규칙 keep)은 다음과 같다. Laya 값은 `answer_confidence`, Jev 값은 TypeSafe Choice `confidence`다. 둘은 서로 다른 척도이며 확률이 아니다.

| 프레임 | Jev choice · confidence · 확률(keep/reject/review) | Jev 이유 | Laya | 상태 특징 |
| --- | --- | --- | --- | --- |
| 해적 F018 | keep · 0.56 · .71/.01/.28 | `JEV_LOW_CONFIDENCE` | review 0.39 | 풀 첫 프레임: `previous_frame_defects: "unknown"`, 다음 F019 결함 |
| 해적 F040 | review · 0.45 · .36/.01/.63 | `JEV_LOW_CONFIDENCE` | keep 0.87 | 풀 끝 프레임: `next_frame_defects: "unknown"` |
| 성직자 F033 | review · 0.38 · .41/.00/.59 | `JEV_LOW_CONFIDENCE` | keep 0.87 | 풀 첫 프레임 |
| 성직자 F056 | review · 0.64 · .23/.01/.76 | `JEV_CHOICE` | keep 0.87 | 풀 끝 프레임 |
| 성직자 F048 | keep · 0.22 · .48/.30/.22 | `JEV_LOW_CONFIDENCE` | review 0.58 | 다음 F049 결함 |

- 규칙 reject 7개(해적 F019–F024, 성직자 F049)는 Jev도 모두 reject(1.0, 확률 1.0)였다. 나머지 keep은 대부분 confidence 0.95–1.0이다. 해적 F039는 0.95, 성직자 F035는 0.98, F050은 0.69(keep .79/reject .19)다.
- **풀 경계 상태(코드 사실)와 review 집중(관찰된 관련, 원인 미분리):** `_state`는 이웃이 없으면 이웃 결함을 `"unknown"`으로 적는다. 이것은 코드 사실이다. 관찰된 것은 결함이 없는 경계 프레임 4개가 모두 Jev review였다는 점이다. 경계 상태와 review 집중 사이에 관련이 보인다. criteria의 "some checks are unknown → review" 문구가 영향을 줬을 수 있다는 것은 추론이다. 경계 상태만 바꾼 분리 실험은 하지 않았으므로 원인은 확정하지 않는다. 이 상태는 Laya와 공유하는 고정 계약이라 이번에는 바꾸지 않았다. 다음 개선 후보(가설 검증용)는 `"unknown"` 대신 `"no neighbouring frame"`을 쓰는 것이다. 질문 버전을 올려야 하며 캐시·비교가 새로 시작된다. 이번 결과에서 실제로 영향을 받은 슬롯은 각 영상의 슬롯 1(균등 프레임 유지, review)뿐이다. 그 프레임은 바뀌지 않았다.
- 이웃 결함 텍스트에 따른 흔들림(성직자 F048)은 Laya와 같은 방향이다. 두 판정 모두 F049 결함 이웃인 F048을 피해 F050을 골랐다. F048과 F050은 이전 검수에서 mild 경계다. 어느 쪽이 더 깨끗한지는 정해지지 않았다.

## F024→F025 교체 증명 (해적, 새 라이브러리)

- `library-verification.json`(`scripts/verify_live.py`, `project.sqlite3` 읽기 전용): revision 7, 클립 2개, 각 8슬롯, `walk`, `loop: true`, 원본 인덱스 증가, 이미지 파일 모두 존재, 문제 0건.
  - 해적 `18,21,25,27,30,33,36,39`, 표시 `125,167,83,125,125,125,125,125ms` = 1000ms.
  - 성직자 `33,36,39,42,46,50,52,55`, `125,125,125,167,166,84,125,166ms` = 1083ms.
  - 슬롯 결정 출처는 `jev`다. 사용자 필드는 `pending`/숨김 아님/사유 없음 그대로다.
- 대체 후보: 해적 F024(slot 2, label reject, `uniform-alternative`, source jev, 이미지 있음, 사용 0회), 성직자 F049(slot 5, 같은 조건).
- 재생: GIF·WebP 8프레임, loop 0(무한), 합 1000ms. 성직자 WebP는 1083ms, GIF는 10ms 단위 반올림으로 1080ms다. artifact 표 SHA와 일치한다. 파일 사본은 `playback/`에 있다. 해적 Jev = Luna+규칙 = Luna+Laya이고, 성직자 Jev = Luna+Laya다. 두 경우 모두 GIF·WebP·strip 바이트가 같다. 균등 클립과는 다르다.
- 시각 증거: `replacement/pirate-F024-F025-raw-keyed-final-jev.png`. 새 프로젝트의 raw·키잉 후보·최종 64×128 셀(×4)이다. F024 오른쪽 부츠 정강이의 올리브색 얼룩이 raw부터 남아 있다. F025는 두 부츠가 갈색이다. 이전 검수의 확대 판단(F024 defect, F025 clean, 모델 시각 판단이며 사람 정답 아님)과 같은 이미지다. F023은 이 클립이 가져오지 않는 프레임이라(균등도 선택도 아님) 시트에 없다.

## UI 확인 (ego-browser)

- 새 TaskSpace 21을 만들어 `http://127.0.0.1:5173`에서 새 프로젝트를 열었다. 확인 뒤 `finish`를 1회 호출했다. 사용자 창·마우스·Chrome은 쓰지 않았다. TaskSpace 9(사용자)와 19(이전 작업)는 건드리지 않았다.
- 동작 만들기 → 영상으로 만들기 → 기존 영상 처리: "선별 판정" 목록에 `Jev(TypeSafe) 필수 · 유료 API 1회 · 불가하면 중단`이 활성으로 보였다. 목록을 드러내려고 로컬 폼 값만 vision으로 바꿨다가 uniform으로 되돌렸다. 제출은 하지 않았다.
- 프레임 편집(해적 클립):
  - 슬롯 3: “슬롯 3 · 균등 위치 24번 대신 선택 · 판정 Jev(TypeSafe)”, 이유 “Jev 판정”, 83ms.
  - 슬롯 1: “확실한 대체 후보가 없어 확인 필요 · 판정 Jev(TypeSafe)”, “Jev 신뢰도 부족”.
  - 후보 라이브러리: 후보 9(영상편집-24)와 후보 18(영상편집-49)이 “0회 사용 · 영상 선별 · 교체된 균등 프레임”으로 표시됐다.
- 확인 뒤 저장 상태는 v7 그대로이며 편집하지 않았다. 증거: `ui/`(스크린샷 3장, `ui-check.json`, `video-step-jev-option.json`).

## 데이터 보존 (`live/preservation-check.json`, 준비 baseline 기준 1회 검사)

- `.data`/`output` 기존 15,981개 중 누락은 0이다. 바뀐 파일은 둘이다.
  - `.data/app.sqlite3`: 앱 인덱스. 새 프로젝트와 작업 2건이 등록됐다.
  - 이전 앱 로그: 위 재시작 설명 참고. 이전 인스턴스가 실행 중일 때 쌓인 브라우저 폴링 기록과 종료 로그 151B다.
- 추가 456개:
  - 새 프로젝트 폴더
  - Jev 캐시 2개(`.data/cache/frame-selection/jev/`)
  - 관찰 캐시: 9개 그대로, 새 Luna 관찰 없음
- 원본 MP4·기준 그림, 이전 프로젝트 `c314768d…`·`5f83bfb7…`, 이전 실험·라벨·출력은 바뀌지 않았다. worktree 108개 중 누락은 0이다. 바뀐 9개는 준비 task에서 수정한 파일 그대로다.
- `.env`는 mode 600이고 파일을 바꾸지 않았다. 키 값은 읽어 출력하거나 해시하거나 baseline·산출물에 넣지 않았다.

## 실행 명령

```
PYTHONPATH=. engine/sprite-gen/.venv/bin/python -m pytest -q tests/integration/test_frame_selection.py tests/integration/test_frame_selection_jev.py tests/integration/test_video_jobs.py -p no:cacheprovider -W ignore
engine/sprite-gen/.venv/bin/python output/frame-selection-jev/scripts/run_jev_comparison.py --dry-run
engine/sprite-gen/.venv/bin/python output/frame-selection-jev/scripts/run_jev_comparison.py --live
engine/sprite-gen/.venv/bin/python output/frame-selection-jev/scripts/verify_live.py
engine/sprite-gen/.venv/bin/python output/frame-selection-jev/scripts/preservation_check.py
```

준비 단계의 전체 integration(2457 passed/1 skipped)과 web 검사(vitest 503, tsc, build, guide)는 다시 돌리지 않았다. 이번 수정은 Jev 전송·키 검증과 출력 러너에 한정된다.

## 남은 한계

- 영상 2개, 영상당 호출 1회, 사람 정답 라벨 없음. Jev 반복성·일반 정확도는 확인하지 않았다. 0.6 게이트는 미보정 값이다.
- 풀 경계의 `"unknown"` 이웃 상태와 Jev review 집중 사이에 관련이 관찰됐다. 원인은 분리하지 않았다. 원인을 확인하거나 개선하려면 Laya와 공유하는 상태 계약을 바꿔야 하므로 사용자 결정이 필요하다.
- Jev는 Luna가 텍스트로 넘긴 결함만 판단한다. Luna가 놓친 해적 F033·F034 부츠 오염은 세 판정 모두 keep이다.
