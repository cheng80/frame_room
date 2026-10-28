# M1 구현·검증 기록

2026-10-22 KST · 구현 GPT 6.1 Sol xHigh · **독립 최종 검수 통과·M1 완료**

기준 `main` / `c48e46ec4c48eac1a1625aa47274dd6ee426897a`. Run `run_5dbba83351d2`, Task `task_55937e2c26b7`, Dispatch `ctx_d9e7057fe9a2`. commit/push/PR/merge/배포·실제 인증·유료 생성은 하지 않았다. 기존 PM 문서와 사용자 변경은 보존했다.

## 변경 범위와 기존 경계

- `video_provider.generate`의 worker 호출, 직접 회귀 호출, checkpoint 상태·재시도 API·공개 Job·JobCard를 함께 조사했다. 기존 `generate_video`·`http_json`·`http_download`, `videos.validate`, 원자 파일 쓰기와 결과 체크포인트를 재사용한다.
- adapter: POST 횟수를 전송 전에 영속화하고 새 POST를 차단한다. 동일 ID GET과 동일 결과 다운로드의 일시 오류를 각각 최대 4회, 1/2/4초 backoff로 재시도한다. 다운로드의 MP4 검사 실패는 자동 재시도하지 않는다. 재개별 600초 예산과 HTTP별 최대 60초를 적용한다. 401/403은 안전한 인증 안내 후 중단한다.
- 실제 transport: `xai.http_json`의 선택 deadline과 앱 전용 opener가 socket 수신마다 남은 시간을 적용한다. 느리게 분할된 header/body도 예산을 연장하지 않는다. `video.http_download`는 timeout/deadline·실제 전송 시도 callback을 받아 무인증/동일 credential 재요청이 같은 예산을 공유한다. 독립 CLI의 deadline 생략 경로는 기존 urlopen이다.
- 다운로드: 앱 MP4 검사·해시 계산을 통과한 바이트만 엔진의 독점 `mkstemp`·fd write/fsync·`replace` 원자 게시에 전달한다. 고정 `.part`와 최종 출력/부모 symlink를 통해 다른 원본을 덮지 않으며 실패 임시 파일을 정리한다. 완료 URL·다운로드·검사 실패는 완료로 게시하지 않는다. 로컬 원본이 있으면 인증/원격 요청보다 먼저 해시와 영상을 확인한다.
- 저장: 기존 `result.json`·`publicationHashes`와 `reuseResultAttemptId` 경로를 사용한다. DB 게시 후 폴더 flush 실패는 완료 결과를 보존하고 `interrupted`로 표시한다. 이미 게시한 결과는 같은 attemptId로 폴더/상태만 다시 저장하므로 후보·동작·출력이 중복 등록되지 않는다.
- 수명: 출력의 snapshot 검사·asset 존재/읽기·job/export 등록을 기존 SQLite writer transaction 하나로 묶는다. enqueue의 기존 transaction도 함께 강제 순서 회귀로 검사한다. 일반 asset 읽기 중 사라진 파일은 안전한 424로 변환한다.
- 계약: `VIDEO.md`, OpenAPI retry 설명, TypeScript Job 선택 필드·저장 재시도 라벨을 맞췄다. 새 생성 API·큐·provider fallback·전역 설정·의존성은 추가하지 않았다. `video_task.py`는 과거 ID의 공개 receipt 필터를 적용하고 기존 원본 등록을 유지한다. `task.py`의 완성 결과 재사용 경로는 직접 회귀로 확인하고 그대로 사용했다.

## 7개 인수 조건의 증거

| 조건 | 검증 근거 |
| --- | --- |
| POST 최대 1회 | localhost 서버의 429/403/503·연결 끊김·잘린 body·비JSON·read timeout에서 최초+수동 재시도 합계 POST 1회. 유효 ID 누락·숫자·경로/URL 문자열은 접수 불명으로 보존하며 재전송하지 않음 |
| 동일 ID GET·인증·예산 | 429/500/503·연결·잘린 body·비JSON·read timeout 뒤 같은 `/videos/same-id`만 조회. GET/다운로드 4회 소진·다운로드 503→정상·전체 timeout·느린 header/body·다운로드 인증 두 호출의 합산 예산 검사. 401/403은 1회 조회 후 중단·수동 동일 ID 재개 |
| 불완전 결과 차단 | URL 누락·503 다운로드·잘린 body·read timeout·ftyp만 있는 가짜 MP4가 `original.mp4`/`.part` 완료 파일을 만들지 않음. 다음 수동 재개에서 같은 ID 회수 성공 |
| 원본/완성 결과 재사용 | 원자 게시 후 receipt 없는 checkpoint를 만들어 인증·조회·다운로드 없이 로컬 원본 재사용. 완성 결과 저장 재시도는 `execute`/`generate`를 실패시켜도 성공 |
| 별도 출력·라이브러리·폴더 저장 | 저장 transaction 전 실패와 DB 게시 후 flush 실패 모두에서 원본 result 보존, 출력 존재·해시 검증, 동작/프레임/개별 시간 일치·중복 0. 폴더 `project.json` marker와 `project.sqlite3` snapshot 재조회 일치 |
| 삭제/등록 강제 경합 | export의 `resource_path`가 존재를 확인한 직후 읽기 전 정지, enqueue snapshot을 읽은 직후 정지. 이때 삭제가 진입해도 등록 완료까지 기다리고 이후 `PROJECT_BUSY`; job/export 행 보존. M0 최초 실패가 이 원인이었다고 확정하지 않음 |
| 안전한 공개 정보·보존 | `recovery`는 ID·POST/GET/download 횟수·안전한 중단 코드만 제공. request_id는 제한 ASCII·현재 credential token 미포함을 신규 응답 수용 시 검증한다. 검증 표식 없는 과거 ID는 내부 원본을 보존하며 공개 recovery/재사용 receipt에서 생략한다. 재사용 receipt 전체를 필드 allowlist·model/hash/시간/횟수 타입·고정 중단 코드로 정규화하고 legacy receipt 원문은 checkpoint에 보존한다. model은 요청 허용 목록 또는 unknown만 공개. 합성 token·서명 URL·인증 경로가 receipt에 없음. 실제 인증 파일을 읽지 않음 |

`test_video_recovery_transport.py`는 실제 앱 urllib transport를 localhost HTTP 서버에 연결한다. HTTP 함수 monkeypatch만으로 통과시키지 않는다. MP4는 ffmpeg로 만든 합성 fixture이며 실제 GPT 생성 결과로 소개하지 않는다. 기존 처리 시험의 fake transport는 timeout/deadline 인자와 GET 재시도 횟수에 맞춰 수정했다.

## 엔진 및 M0 증거

기반 pin과 `qualityVersion=2.34.0`은 유지한다. 엔진 변경은 `gen/video.py`·`gen/xai.py` 두 파일이며 고정 MP4 `.part`의 symlink 및 최종 `out.resolve()`가 원본을 덮는 독립 검수 재현을 수정했다. 독점 임시 파일·fsync·replace와 출력 경로/부모 symlink 차단으로 보존하며 failure cleanup을 검사한다. 현재 SHA-256은 `engine-lock.json.patches`·`localAdaptations[M1]`에 기록했다. 같은 항목의 `beforeSha256`은 M0 당시 파일 해시와 대조한다. v2.45.3 전체 이식으로 표시하지 않는다.

M0 JSON·baseline은 다시 쓰지 않았다. `port-plan --verify`가 현재 엔진과 다른 두 파일·lock을 표시하는 것은 역사적 기준과 현재 구현의 명시적 차이다. 회귀는 이 차이만 허용하고 전후 해시를 검사한다. 함수 호출 줄 번호는 M0 기준 commit의 source에서 재검사한다. 현재 source로 M0 조사 결과를 덮어쓰지 않는다.

## 실행 기록

모든 Python 검사는 shell에서 `SPRITE_DATA_DIR`을 scratch로 지정한 뒤 import/시험 수집을 시작했다. 사용자 자료를 제품 import 전에 순수 파일 읽기로 해시했다. `.data`·`output` 총 1,029파일의 사전/사후 SHA-256 일치, 누락/변경/추가 0을 확인했다. 인증·전역 설정·공용 sprite-gen 스킬은 수정하지 않았다.

| 실제 명령 | 결과 |
| --- | --- |
| `python -m pytest tests/integration/test_video_recovery_transport.py tests/integration/test_video_jobs.py -q` (초안) | 43 passed, 3 failed: 새 저장 fixture가 project.json marker를 snapshot으로 오해한 2건, 기존 fake transport의 timeout 인자 미지원 1건. 수정함 |
| 영향 회귀 6파일 실행 (중간) | 283 passed, 4 failed: 기존 approved fixture job 수 미반영 2건, M0와 현재 변경의 정확 일치 기대 2건. 강제 경합은 통과했으며 시험/역사적 근거 검사를 수정함 |
| `python -m pytest tests/integration/test_video_recovery_transport.py tests/integration/test_video_jobs.py tests/integration/test_api.py::test_delete_waits_between_resource_check_and_registration tests/integration/test_absorption_m0.py tests/integration/test_engine_guard.py -q` | 106 passed |
| 엔진 `test_video.py` + 잘못 지정한 `test_xai.py` (초회) | 존재하지 않는 경로로 수집 실패·시험 미실행. 실제 파일 확인 후 다음 명령으로 수정 |
| `python -m pytest engine/sprite-gen/tests/gen/test_video.py engine/sprite-gen/tests/gen/test_video_modes.py -q` | 113 passed |
| `npm --prefix apps/web test` (초회) | 540 passed, 1 failed: 새 한국어 라벨의 한자 오타. 수정함 |
| `npm --prefix apps/web test` (수정 후) | 541 passed, 28파일 |
| `npm --prefix apps/web run build` (수정 후) | tsc·Vite build 통과 |
| `python scripts/doctor.py` | 엔진 원본/승인 패치 407파일 무결성 통과 |
| `python -m pytest tests/integration -q` (첫 전체) | 2,559 passed, 1 skipped, 165.59초. 이후 인증 body·token 반사/과거 ID 필터 회귀를 보완함 |
| `python -m pytest tests/integration/test_video_recovery_transport.py tests/integration/test_absorption_m0.py -q` | 인증 body 보완 후 81 passed |
| `python -m pytest tests/integration/test_video_recovery_transport.py tests/integration/test_video_jobs.py tests/integration/test_absorption_m0.py tests/integration/test_engine_guard.py -q` | token 반사/과거 ID 보완 후 108 passed |
| `python -m pytest tests/integration -q` (두 번째 전체) | 2,564 passed, 1 skipped, 173.57초. 이후 독립 검수 지시로 일시 다운로드 제한 재시도 추가 |
| `python -m pytest tests/integration/test_video_recovery_transport.py tests/integration/test_video_jobs.py tests/integration/test_absorption_m0.py tests/integration/test_engine_guard.py -q` (다운로드 재시도 반영 후) | 116 passed, 38.17초 |
| `python -m pytest tests/integration -q` (최종, 다운로드 재시도 반영 후) | **2,571 passed, 1 skipped**, 174.87초. skip은 Git에 포함하지 않은 로컬 연구 원본 |
| symlink 수정 1차 영향·엔진 | 231 passed, 1 failed: 실행 도중 부모 경계 수정으로 engine hash가 바뀐 상태를 M0 해시 회귀가 정확히 탐지. 변경을 고정하고 다음 실행으로 확인 |
| symlink 수정 후 영향·엔진 재실행 | 234 passed, 41.10초 |
| `python -m pytest tests/integration/test_video_recovery_transport.py tests/integration/test_video_jobs.py tests/integration/test_absorption_m0.py tests/integration/test_engine_guard.py engine/sprite-gen/tests/gen/test_video.py engine/sprite-gen/tests/gen/test_video_modes.py -q` (symlink·legacy 최종) | **235 passed**, 41.25초 |
| `python -m pytest tests/integration -q` (symlink·legacy 최종) | **2,577 passed, 1 skipped**, 179.37초. `test_pipeline.py::test_real_gunner_prefit_height_and_manual_anchor`: Git에 없는 로컬 연구 원본 경로 부재 |
| `git diff --check` | 최종 통과 |

로그는 구현 세션의 `/tmp/frame-room-m1-*.log`에 보존한다. 시험 중 반복은 새 변경/실패 수정으로 필요한 범위만 수행했다.

## 한계

Postman CLI 1.69.0은 1.70+ simulation을 지원하지 않는 것을 PM이 확인했다. 기존 OpenAPI를 재사용하고 재현 가능한 localhost transport fixture로 대체했으며 CLI 갱신·인증·workspace 생성·게시를 하지 않았다. 실제 provider 장애/인증·유료 생성·RIFE 성능·브라우저/ego UI 조작은 검증하지 않았다. 공개 receipt는 기계 위치·서명 URL을 제공하지 않으며 원본/프레임/시간/ID의 기존 저장 계약을 유지한다.

이전 후보(독립 검수 추가 수정 전): 제품·계약·시험 diff를 검토했고 사용자 `.data`·`output` 1,029파일의 SHA-256 동일·새 파일 0을 다시 확인했다. 최종 전체 소스에서 2,571 passed·1 skipped, 영향 116 passed, 엔진 영상 113 passed, 웹 541 passed·build, doctor 407파일·diff check가 통과했다. 독립 검수 완료 전에는 Task를 종료하지 않는다.

## 최종 실행 근거

격리 환경의 실제 shell 값은 `SPRITE_DATA_DIR=/var/folders/yk/7gcx2d_d3g36kr1klhhz4q700000gn/T/frame-room-m1-6hhtvo0t/data`, 제품이 해석한 경로는 `/private/var/folders/yk/7gcx2d_d3g36kr1klhhz4q700000gn/T/frame-room-m1-6hhtvo0t/data`다. 사전 manifest `/var/folders/yk/7gcx2d_d3g36kr1klhhz4q700000gn/T/frame-room-m1-6hhtvo0t/preservation-before.json`, 최종 사후 manifest `/var/folders/yk/7gcx2d_d3g36kr1klhhz4q700000gn/T/frame-room-m1-6hhtvo0t/preservation-after-manifest.json`, 비교 결과 `/var/folders/yk/7gcx2d_d3g36kr1klhhz4q700000gn/T/frame-room-m1-6hhtvo0t/preservation-after.json`에 보존했다. 사전/사후 1,029파일, 변경/누락/추가 0이다. 모두 저장소 밖 scratch이며 사용자 자료를 복사·수정하지 않았다.

마지막 전체 명령은 위 격리 환경을 먼저 지정한 `engine/sprite-gen/.venv/bin/python -m pytest tests/integration -q > /tmp/frame-room-m1-integration-final-reviewed.log 2>&1`다. 마지막 영향·엔진 로그는 `/tmp/frame-room-m1-review-final.log`(235 passed), 웹 시험 `/tmp/frame-room-m1-web-test-final.log`(541 passed), 빌드 `/tmp/frame-room-m1-web-build-final.log`다.

최종 수정 후보: **2,577 passed·1 skipped**(`/tmp/frame-room-m1-integration-final-reviewed.log`), 영향·엔진 **235 passed**, 웹 **541 passed·build**, doctor **407파일**, diff check 통과. 전체 실행 종료 후 사용자 `.data`·`output` 1,029파일 사후 manifest를 다시 계산해 변경/누락/추가 0을 확인했다. 작업 pytest/worker/시험 harness 프로세스 0이며 확인 결과는 `/var/folders/yk/7gcx2d_d3g36kr1klhhz4q700000gn/T/frame-room-m1-6hhtvo0t/remaining-task-processes.json`에 남겼다. 독립 검수 최종 결과는 PM의 완료 통보로 확인했다.

최종 완료 통보: PM 메시지 `msg_14892e111fe4`가 독립 검수 `worker_done` `msg_c66893f59146`의 outcome succeeded·미해결 0과 PM의 마지막 전체 로그/1,029파일/diff 확인을 전달했다. 제품 소스 추가 변경이나 추가 검사는 하지 않았으며 완료 기록 후 구현 Task를 종료한다. commit/push/PR/merge/배포·유료 생성은 하지 않았다.
