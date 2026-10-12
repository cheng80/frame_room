> 보관 안내(2026-10-13 게시 준비): 이 문서는 원본 작업 폴더의 미커밋 전체 상태에서 진행한 구현·검수 기록을 그대로 옮긴 지침 문서다. 문서의 시험 수, 실행 앱 재시작, `output/`·`/tmp` 증거 경로, 다른 계획 문서 참조는 그 작업 폴더 기준이며 이 저장소에 포함되지 않는다. 이 커밋 범위만 분리해 실행한 검증은 [FRAME_SELECTION_PUBLISH_2026-10-13.md](FRAME_SELECTION_PUBLISH_2026-10-13.md)에 따로 기록한다.

# 검수 보관 안내

검수자: GPT-6.1 Sol · Medium. Orca run `run_2b3f47ce182e`, task `task_10cc91fb2260`. 원문과 시험 근거를 `output/frame-selection-rules-cleanup/review/`에 보관했다. PM은 아래 보관본에서 `matchClipId 생략 요청` 오기를 `matchClipId가 있는 요청`으로 바로잡고 파일 참조를 보관 경로로 옮겼다. 원문은 `frame-selection-rules-review-final.md`로 보존한다. 제품 코드와 동결 대상은 수정하지 않았다.

# Luna+규칙 기본화·Laya/Jev 제거 독립 검수

결론: 검수 완료, 미해결 blocking finding 없음. task_10cc91fb2260 / ctx_fb588daf078f의 읽기 전용 검수이며 프로젝트 코드·문서·.data·output·.env를 수정하지 않았다. 검수 산출물은 `/tmp/frame-selection-rules-review*`에만 기록했다.

## 최종 기준과 범위

PM의 NEW FINAL FREEZE(task_c7a775fcd018 / ctx_0d9e1a78497d) 이후 `output/frame-selection-rules-cleanup/final-boundary/freeze-code.sha256` 22개가 현재 파일과 모두 일치한다. 삭제 대상 4개(typesafe_judge.py, requirements-laya-mlx.txt, Jev 전용 .env.example, Jev 테스트)는 별도로 부재를 확인했다.

기준은 dirty HEAD가 아니라 최초 `baseline/worktree-snapshot/`, `git-status.txt`, `worktree.diff`다. snapshot의 기존 파일 변경·삭제와 시작 시 clean이던 video 관련 테스트 3개의 HEAD 대비 변경, 신규 구현 보고서를 대조했다. 작업 시작 대비 변경 22개가 기능 코드·UI·bootstrap·계약·테스트·보고서 범위다. 사용자 AGENTS, 기존 구현의 다른 변경, 과거 비교 문서는 보존됐다. 후속 내부 강화는 frame_selection.py·관련 테스트·VIDEO.md·구현 보고서에 한정된다.

## 요구사항 확인

- 활성 Laya MLX/Jev import·checkpoint 감지/로드·HTTP transport·키 로더·capability·UI 옵션·선택 설치 bootstrap이 제거됐다. 남은 Laya/Jev 문자열은 명시 입력 거부 안내, 과거 기록 표시, 오래된 키가 observer subprocess로 전달되지 않도록 하는 삭제 처리다. secret 값을 읽지 않는다. engine 기본 lock과 doctor에 Laya/Jev/MLX 의존성이 없다. 설치된 패키지·checkpoint·과거 캐시를 임의 삭제하지 않는다.
- 새 웹 설정은 vision, serializer는 vision+rules 또는 명시 uniform을 보낸다. 신규 generate_video/process_video POST는 생략 selection을 vision+rules로 해시 전에 구체화한다. matchClipId가 있는 요청은 uniform을 유지한다. batch 항목도 같은 enqueue 경로다.
- 저장 작업 재검증·retry/resume·직접 legacy process_clip 생략은 uniform이다. saved request를 다시 쓰지 않는다. 기존 같은 제출 키 재전송은 raw/defaulted hash를 비교해 같은 작업을 반환하고 내용 변경은 409다.
- missing/auto judge는 실제 처리에서 rules이다. laya/jev는 API/worker 또는 직접 처리 검증에서 관찰 전에 거절한다. API·process_clip의 explicit observer는 기존 고정 비교 허용 목록을 유지한다.
- 자동 observer는 요청마다 CLI 존재와 로컬 models_cache.json을 확인한다. 정확한 list visibility, 배열형 image modalities, 배열형 medium reasoning 조건을 만족하는 Luna를 숫자 버전 순서로 고른다. hidden/잘못된 타입·과도한 숫자 버전은 제외한다. CLI/적합한 catalog Luna가 없으면 calls=0, 빈 프레임 reject·나머지 review, verified keep이 없어 uniform이다. 다른 family/model 재시도·fallback은 없다.
- 내부 dynamic observer는 실제 latest_luna 결과일 때만 허용한다. 기존 gpt-6-luna-medium / gpt-6.1-sol-medium의 명시 비교 경로는 별도 고정 registry로 유지된다. 이것은 자동 fallback 경로가 아니다. 공개 process_clip 우회 가능성에 관한 예비 추론은 실제 caller의 고정 허용 목록 검증을 확인해 철회했으며, 후속 변경은 내부 강화로 기록한다.
- 모델/medium/id가 cache identity와 receipt에 포함된다. 프롬프트·스키마·selection 버전과 기존 gpt-6-luna cache key는 유지한다. actualModel 불일치는 실패 처리한다. actualModel이 없는 receipt를 실제 실행 모델 검증으로 간주하지 않는다. 새 실제 추론은 실행하지 않았다.

## 직접 실행한 검증

- 이전 동결에서 독립 8개와 관련 selection 56개: **64 passed**. `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-rules-cleanup/review/frame-selection-rules-review-final-tests.txt`.
- 최종 내부 resolver 변경 뒤 필요한 독립 경계만 재실행: **11 passed**. 숫자 순서·매 요청 재읽기, malformed modalities/levels·hidden 거부, old omitted idempotency replay, CLI 부재 zero-call, dynamic observer의 catalog 근거, 5000자리 잘못된 버전, 고정 비교 경로를 확인했다. `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-rules-cleanup/review/frame-selection-rules-review-final-boundary.txt`.
- `git diff --check` 성공. 전체 integration·웹 전체 시험·빌드는 검수자가 반복하지 않았다. 구현자 최종 selection 65, 경계 묶음 347, 관련 3개와 이전 affected 1771·웹 503·tsc/build 로그는 읽어 대조했다. 모든 mock/합성 시험은 실제 추론 품질 증명이 아니다.
- 예비 시험은 malformed catalog 2건, old replay 1건 및 CLI 부재 진입을 재현해 PM에 전달했으며 수정 후 통과했다. 이는 반편집 상태를 최종 결함으로 평가한 결과가 아니다.

## 저장된 실제 캐시 사례

최종 코드로 과거 실제 Grok 영상의 keyed 원본·reference·Luna 관찰 캐시를 읽었다. 캐시는 `/tmp`로 복사하고 관찰 함수·subprocess·네트워크를 차단했으며 cache-only로 선택만 재계산했다. 새 프로젝트나 라이브러리 동작을 생성·저장하지 않았다.

- 해적 job 201a3ca5-3992-4deb-b1d8-1a90602e5043: 18,21,24,27,30,33,36,39 → 18,21,25,27,30,33,36,39. F024→F025 유지, cacheHit=true·calls=0·기존 cache key 동일, 8슬롯·1000ms·루프/시퀀스 검사 통과.
- 성직자 규칙 job b17906a4-8fc4-4d0f-8ef2-56da63e2d24a: 33,36,39,42,46,49,52,55 → 33,36,39,42,46,48,52,55. 기존 rules 결과와 일치, cacheHit=true·calls=0, 8슬롯·1083ms·시퀀스 검사 통과. Laya/Jev의 F050 결과와 혼동하지 않는다.
- 관련 selection 회귀는 no-keep uniform, unknown review, 순서·수·시간·loop, sequence rollback, alternate lineage와 사용자 review 보존을 포함한다.
- 실제 관찰 비교 라이브러리 v15: 10클립·94프레임·14 unused uniform alternatives. Jev 비교 v7: 2클립·18프레임·2 unused alternatives. 모두 8슬롯·loop를 유지하며 사용자 review/hidden와 기존 기록이 남아 있다.
- 최초 realcase harness는 개별 진단 duration 반올림 합을 저장 duration과 비교해 실패했다. 제품의 누적 경계와 totalMs로 검사식을 바로잡은 뒤 두 사례가 통과했다. 제품 오류로 계산하지 않았다.

실제 사례 증거: `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-rules-cleanup/review/frame-selection-rules-review-realcase.json`, `.txt`, 저장 라이브러리 `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-rules-cleanup/review/frame-selection-rules-review-saved-library.json`.

## 원본·runtime·UI 보존

- 최초 data/output manifest **16,493개, missing 0**, 내용 차이는 `.data/app.sqlite3` 하나다. 모든 원본 프로젝트 DB·영상·이미지·과거 출력·Jev 캐시·이전 실험 자료는 그대로다.
- 공용 DB의 projects/jobs 최신 updated와 표 행 수는 구현자의 전후 읽기 전용 기록과 같다. 프로젝트 7개, jobs36(needs_review27/succeeded9), revisions57, assets1127, events292, artifacts314, videos25, project_resources1152다. 재시작의 heartbeat/session token 변경 설명과 일치한다.
- 바이트 보존된 프로젝트 DB와 현재 공용 DB의 프로젝트 snapshot7개 및 그 DB들에 저장된 job body29개를 독립 대조해 mismatch0을 확인했다. 나머지 공용 DB 전체 byte delta를 분해한 검증은 하지 않았다.
- `.env`는 Git ignored·600이며 최초 preflight와 mtime가 같다. 내용·secret hash는 읽거나 기록하지 않았다.
- guide26개는 before-build/after-build/current hash가 모두 같다. UI/dist는 추가 내부 수정 전후 바뀌지 않았다. 최종 freeze22개에는 dist 빌드 파일4개도 포함되며 모두 일치한다.
- 구현자가 소유 launcher를 2368→59932→93268로 재시작했고, 마지막 backend는 코드 수정 후 실행됐다는 저장 process/log 기록을 확인했다. 마지막 read-only API evidence가 앞 단계와 동일하며 api/worker ready, vision/rules, gpt-6-luna·medium, 7프로젝트 수와 과거 Laya/Jev source가 보존된다. 검수자는 앱을 조작·재시작하거나 실제 HTTP 요청을 보내지 않았다.
- ego TaskSpace23에서 저장한 `followup/ui-video-frame-selection.png`를 직접 봤다. 저장됨 v15, Luna 관찰+규칙 기본과 gpt-6-luna·medium 문구가 보이며 활성 judge 선택은 없다. 브라우저를 새로 열거나 사용자 작업 창을 가로채지 않았다.

## 한계

현재 catalog metadata는 fetched_at=2000-01-01/client_version=0.0.0이다. “최신”은 이 시스템의 로컬 지원 목록 기준이며 온라인 최신 보장이 아니다. 새 Luna 추론·유료 API·모델 설치·새 AI 영상 생성·Git 게시·배포·직접 브라우저/HTTP 검증과 전체 시험 반복은 하지 않았다. 실제 품질 개선 일반화나 더 새 모델의 실제 account 지원은 이 검수로 입증되지 않는다.
