# M2 구현·실행 기록

2026-10-22 KST · 구현 GPT 6.1 Sol xHigh · **독립 최종 검수 합격·PM 수용·M2 구현 완료**

Run `run_70d73cc5d001`, Task `task_292e4f98827a`, Dispatch `ctx_7b611eb73981`. 기준 main/HEAD `c48e46ec4c48eac1a1625aa47274dd6ee426897a`. M1 미커밋 원문은 PM의 `source-before` 사본과 대조했다. commit/push/PR/merge/배포·provider/관찰모델 호출·인증/전역 설정·공용 sprite-gen 변경은 하지 않았다.

## 범위와 호출 경로

기존 `enqueue → execute_video → process_clip → _select → _gait_fallback → _repair_selection → _align_selected_cycle → normalize_frames → finish_frames → render_occurrence → write_animation_formats → publish`를 유지한다. 추가 파이프라인이나 생성 API는 없다.

- 새 `video-processing-v5-sprite-gen-2.45.3-m2`의 정책 identity는 실제 엔진·adapter·alignment·worker 영상 소스 digest, 로컬 RIFE binary/model/host identity digest, 색/알파·보간 정책을 포함한다. 새 job과 extraction key·처리 결과에 저장하며 API retry와 worker 직접 진입에서 누락/구/미래 VERSION·다른 digest·unknown 설정을 거절한다. 완성 결과의 저장만 재시도는 M1의 기존 경로를 유지해 구 policy도 저장 가능하다.
- 고정 upstream `59b2738a2e76ed7043d9691a230396ed6374a336`의 모든 파일을 `fetch-upstream`으로 commit tree와 검증했다. 영상 loop/align/repair/rife/frames, crossings/interpolation_quality/gait/period/motion/evidence/source 및 필요한 공용 resample/lsq/GIF helper만 선별했다. source/nonloop/effect는 이 helper들의 import·영수증 의존이며 M3/M4 제품 기능을 완료했다는 뜻이 아니다. 기반 pin·`qualityVersion=2.34.0`·M1 video/xai 보호는 유지하고 영상 묶음은 `videoQualityVersion=2.45.3-m2`로 구분한다. 현재 해시는 engine-lock의 M2·patches에 기록한다.
- 선택은 원본 교차의 `two/refuted/uncertain`과 픽셀 선택을 구분한다. 확인된 두 걸음·source-range·교차 근거를 남기고 비이족/기준 구조 불명은 이족 확정하지 않는다. lead-in은 자동 검색에서만 제외한다. 명시 수동 범위·기본8/선택12/4–64·개별 시간은 보존하며 축소에는 보간을 추가하지 않는다.
- source ghost·장비 픽셀 주기·held/period·급가속/flow·몸통 보호·상대 outline gate를 연결한다. repair off는 진단만 하며 filmed-ghost는 재촬영 권고다. ghost 원본 대체/flow/easing/overlap은 실제 입력 index와 비율을 기록한다. 맞춤 resample의 실제 `cells_from`을 써서 ghost/nearest 대체 후 원본 부모·회전 시간도 맞춘다.
- 실제 최종 셀에서 seam/wrap과 `pass/review/not-loop`를 기록한다. 기존 renderer의 unbounded `supportBounds`·safe overflow를 재사용해 안전 여백 부족과 실제 canvas clipping을 구분한다. 원본 edge contact는 별도 측정 대상으로 남긴다. UI는 두 걸음 불확실·잔상·겹침 미적용·캐시·최종 셀 검사·여백/잘림을 구분해 표시한다.
- `rifeTta=off|on`(on=`-x -z`), `overlapWrap=off|auto`를 API/화면/계약에 연결했다. 둘 다 off 기본값이며 기존 저장 설정을 바꾸지 않는다. overlap은 명시 보정과 확인된 두 걸음, 닫히지 않는 source wrap에서만 검토한다. 기본 60초/2M픽셀 RIFE 예산은 캐시/flow/easing/overlap/각 binary pass의 취소·잔여 시간과 공유한다. 실패는 원본을 보존하고 성공으로 기록하지 않는다.
- 캐시는 서버가 정한 `<project>/.cache/rife-m2`다. RGBA·순서·비율·전처리 코드·binary/model/TTA/host identity 키와 PNG 픽셀 SHA 검증을 재사용한다. hit도 현재 quality gate를 수행한다. 손상/삭제는 재계산하고 쓰기 불능은 캐시 없이 결과를 유지한다. project/parent/leaf symlink를 검사하고 directory fd를 고정한 exclusive 임시 파일·원자 replace로 보간 도중 부모 교체의 외부 게시를 차단한다. 원본·채택 셀·계보는 outputs/library에 저장한다.

## M0 대장 M2 9항목 대응

| 항목 | 실제 연결·증거 |
| --- | --- |
| `cmd.video-canvas` | 기존 prepare_still/canvas 재사용, walk/run 강제 wide의 headroom 0만 선별 적응. attack·jump·기존 이미지/방향 회귀 보존 |
| `cmd.video-frames` | 실제 ffmpeg/key_frames, source edge·speck/residual/subject 구분과 보존 MP4 keyed/최종 셀 비교 |
| `cmd.video-loop` | 실제 앱 저장 경로 M1/M2 비교, 8셀/개별ms/PNG/GIF/WebP/폴더DB 일치 |
| `flag.video-loop-two-step` | crossings 근거·비이족 불확실·lead-in/장비 주기·manual/8/12 회귀 |
| `flag.video-loop-ghost` | source screen·filmed-ghost 권고·원본 대체/보간 계보·실제 align sample mapping |
| `flag.loop-repair-flow` | flow/eased retime/torso·outline·최종 rendered seam, overlap opt-in 및 실측 예산중단 |
| `flag.rife-tta-cache` | 프로젝트 cache 실제 Session·원자 게시·hit 현재 gate·symlink/동시/손상/중단 회귀·TTA off/on 실측 |
| `cmd.video-cycle-align` | 기존 matchClipId/target 수·시간 경로, resample 실제 source/nearest/ghost·repair 계보와 회전 시간 |
| `cmd.rife` | 기존 프로젝트 고정 설치 재사용, binary/model SHA·TTA/장치/크기·cold/warm/호출/RSS 실측 |

## 보존 MP4의 M1/M2 비교

scratch `/tmp/frame-room-m2-impl-DJu2hP`. PM 사본 `/var/folders/yk/7gcx2d_d3g36kr1klhhz4q700000gn/T/frame-room-m2-pm-1l9eqi0r/source-before`의 M1 코드와 엔진을 별도 PYTHONPATH로 실행했다. 사용자 프로젝트 SQLite는 파일로 scratch에 복사한 뒤 그 사본만 열어 참조 경로를 찾았다. MP4·참조도 먼저 scratch로 복사했다. 역사적 M0 JSON/baseline은 수정하지 않았다.

입력 MP4 SHA `9a1945d761bbbbc9e4d6a05f6a1258d4306a7e43c82e21a2163ec52fd247af31`은 기존 보존 Grok 영상의 사본이다. 새 provider 요청은 없다. `compare-input.json`, `m1-comparison.json`, `m2-comparison.json`, `comparison-summary.json`에 근거가 있다. 같은 구간33–59·64×128 셀8개·개별 `[125,125,125,167,125,125,125,166]ms`·총1083ms·최종 셀 SHA·strip/GIF/WebP 디코딩이 일치했다. `_verify_animation`으로 WebP 첫 프레임을 포함한8개 시간과 source index mapping도 별도로 일치 확인했다. 두 lane 모두 동작·프레임·시간을 별도 outputs와 library에 저장하고 폴더 SQLite의 snapshot을 재조회해 일치했다. 이 비교는 기존 원본/출력 보존과 동등성을 확인한 것이며 미술 품질 향상을 주장하지 않는다.

최종 고정 소스의 `m2-final-comparison.json`·`m2-final-exports/`도 별도로 생성·폴더DB 재조회했고 `comparison-final-summary.json`의8개 비교와 구간이 모두 같다. 임시 비교 프로젝트는 사용자에게 납품하는 새 동작으로 집계하지 않는다.

## 실제 RIFE 실측과 한계

장치 `Apple M4`, GPU10코어/Metal4, macOS arm64. 프로젝트 binary SHA `d11429c72f0cddfb170fd131ee9373dc5329a5729c4382c0acfd40092e5ed19a`; model `rife-v4.6`, `flownet.bin=f334ed2260149ce0188a6dcf049844e8b0cdd912e01cbcfb63553157d2508958`, `flownet.param=724569596bcd1e7b9fa50455c604777ebed99746d2ef40aa86e31b5725f1053c`. 로컬 실행만 했다.

| 입력 | TTA | cold / warm 초 | 완료 binary calls | child 최대 RSS bytes |
| --- | --- | --- | --- | --- |
| PIL 합성32×32 | off | 1.781 / 0.0148 | 2 / 추가0 | 389,627,904 |
| PIL 합성32×32 | on | 0.837 / 0.0149 | 2 / 추가0 | 356,122,624 |
| PIL 합성96×96 | off | 0.676 / 0.0165 | 2 / 추가0 | 384,122,880 |
| PIL 합성96×96 | on | 0.738 / 0.0135 | 2 / 추가0 | 385,204,224 |
| 실제 보존 영상 keyed544×544 | off | 0.762 / 0.0164 | 2 / 추가0 | 387,612,672 |
| 실제 보존 영상 keyed544×544 | on | 1.271 / 0.0182 | 2 / 추가0 | 367,624,192 |

`bench-*.json`·`.time`는 단일 시행/순서상 device warm-up을 포함한다. cold는 앱 캐시 miss이며 GPU/OS 초기화가 항상 차가웠다는 뜻이 아니다. TTA의 보편적 속도·품질 우위나 CPU 성능은 검증하지 않았다. warm은 cold와 같은 픽셀이며 current gate의 재실행은 별도 회귀에서 검사한다. 합성 도형을 GPT 결과로 소개하지 않는다.

독립 장비 주기의 합성 walker96×120에 실제 RIFE overlap을 실행했다. `overlap-real/measurement.json`의20초 예산은20.215초/완료68호출, `overlap-real-default-budget/measurement.json`의 실제 기본60초는60.249초/완료172호출 후 중단했다. 둘 다 `VIDEO_RIFE_FAILED`이고 완료 결과가 아니며 overlap 품질 성공으로 판정하지 않았다. 원본과 cache 밖 보존 파일은 유지한다. 실제 장비 영상 overlap의 성공·장치별 CPU 측정은 미검증이다.

## 검증 기록

모든 제품 import/pytest는 shell에서 `SPRITE_DATA_DIR`를 저장소 밖 scratch로 먼저 지정했다. 앱/엔진 pytest cwd를 분리했다. 시험의 외부 관찰 호출은 conftest 대역이 차단한다.

| 실행 | 실제 결과 |
| --- | --- |
| fetch-upstream | v2.12.1/v2.34.0/v2.45.3 전수 tree verified |
| 초기 앱 영향 |165 passed/4 failed: 새 periodicity·실제 parent 계보/fixture identity 수정 |
| M2 경계+선별 계보 최종 영향 |27 passed (`m2-final-safety.log`) |
| API/worker/cache/실제 저장·M1 복구 영향 |96 passed (`final-product-impact.log`) |
| M0/engine identity·M2 경계·선별 |64 passed (`final-guards.log`) |
| 앱 전체 중간 |**2598 passed/1 skipped** (`integration-final-frozen.log`,195.33초), 최종 고정 소스 전체 통과 |
| 엔진 최초 관련7파일 |95 passed/9 failed: source 영수증 전이 import 누락, 보완 |
| 엔진 영상 중간 |713 passed/9 failed: upstream의 M4 effect/배치 시험은 범위 밖이므로 새로 가져온 해당 시험만 제외하고 기존 pipeline 전체를 복원. canvas/flow/foot·fixture helper 적응 |
| 기존 engine 회귀 보존 재실행 |198 passed/10 failed: 옮겨진 private helper·누락 fixture import·jump→flow 계약을 적응. 이후93 passed (`restored-tests-final.log`) |
| 엔진 video+util 전체 중간 |719 passed/1 failed: walk 강제wide headroom의 구 기대값. idle override 보존과 gait headroom0를 함께 검사하도록 최소 수정. 최종 고정 전체 **762 passed**/15 marker warnings (`engine-final-frozen.log`,379.28초) |
| 웹 전체 |543 passed/28파일 (`web-reviewed-candidate.log`) |
| 웹 production build |tsc/Vite 통과 (`web-build-reviewed-candidate.log`) |
| doctor |**433파일** 원본/승인 patch 무결성 통과 (`doctor-frozen.log`) |
| ego |TaskSpace5/p1, offline provider fixture+실제 격리 API/worker+production proxy에서 `EGO_SMOKE_PASS` (`ego-smoke-pass.log`) |
| diff check |고정 소스 통과 (`diff-check-final.log`) |

엔진 시험은 기존 `test_video_pipeline.py`의 원문 전체·모든 parameter case를 복원했으며 다른 upstream 교체파일에서 없어진 기존 test15개도 보존했다. private 심볼 이동(`drop_specks`/`support_bounds`)과 jump 기준이 flow/그룹 보간으로 변경된 부분만 적응했다. 기존 두 인접 이상 프레임은 새 정책대로 같은 손대지 않은 외곽 원본 두 장에서1/3·2/3로 복구함을 검사한다. 기존 최대3회·원본/채택 프레임 보호·일반 보행 보호의 검증을 삭제하지 않았다. M4 effect/새 batch 전송 계약은 제품 범위를 넓히지 않았으며 M1 POST 보호를 유지한다.

브라우저 최초 smoke는 fixture heartbeat 만료·비허용 origin의 정적 자원403 때문에 실패했다. scratch Vite 설정도 react-refresh 해석에 실패해 제품 설정을 바꾸지 않고 허용 origin5173의 production proxy로 고쳐 같은 TaskSpace에서 성공했다. 다른 공간·사용자 포인터·Chrome/새 Chromium은 사용하지 않았다. 같은 공간에서 격리 프로젝트의 동작 만들기→영상 폼을 열고 TTA/overlap 기본off·60초 안내 DOM을 확인했다. 생성/설정 변경은 하지 않았으며 전체 UI 제작 여정·screenshot은 검증하지 않았다.

## 원본 보존·M1 대비 diff

사전 기준은 PM scratch의 `preservation-before.json`·`source-before.json`·`m1-before.patch`다. `.data`·`output` 사후 파일 해시를 순수 파일 읽기로 대조한 `preservation-comparison.json`은1,029→1,029파일, 변경/누락/추가0이다. `m2-vs-m1-files.json`은 M1 사본 대비 실제 신규 변경80파일의 전후 SHA이며 M1 누적 diff를 M2로 집계하지 않는다. `m2-vs-m1.patch`로 원문 diff를 보존했고 `candidate-freeze.json`의 policy·engine-lock SHA를 최종 대조했다.

독립 검수는 outcome succeeded·미해결 제품 finding0이며 PM이 최종 구현을 수용했다. 고정 이후 제품·시험 추가 변경 없이 최종 완료를 기록한다. 유료 생성·실제 provider/auth/관찰 호출·Git 게시·배포·전체 UI 여정과 다른 장치의 성능은 생략했다.


## 후보 고정·정리

고정 시각2026-10-22 04:20:56 UTC, engineDigest `e56bec744cf71af498de3735f048f97dc2a963a95a5a6f8c6b18ad204efcfb81`, engine-lock SHA `b4d2906baebb9666794da1097c33f880de0a95996290a84759101ada88fe0860`이다. 고정 이후 제품·엔진·시험은 변경하지 않았다. 최종 앱2598 passed/1 skipped, 엔진762 passed, 웹543 passed·build, doctor433파일·diff·사용자1029파일 동일과 최종 동일 MP4 비교를 확인했다. 앱 skip은 기존 Git에 없는 로컬 연구 원본이다.

PM `msg_e3652fa23c74`가 독립 검수의 ego 사용 완료와 구현 소유 서비스 정리를 지시했다. TaskSpace5를 `finish({keep:[]})`로1회 종료했고 직접 시작한API18306(18765)/worker29352/proxy34087(5173)만 종료했다. 엔진 pytest는 정상 완료한 뒤 정리했으며 별도 세션·사용자 서비스를 종료하지 않았다. 최종 판정은 아래 PM 수용 근거로 확인했다.

독립 검수의 넓은 보존 감사에서 `.grok/logs/unified.jsonl`, `models_cache.json`, `sessions/session_search.sqlite`, `settings_cache.json` 런타임4파일의 변화가 관측됐다는 PM `msg_ccfee0f3967c` 통보가 있다. 구현 세션은 Grok CLI·실제 provider/관찰·로그인 명령을 실행하지 않았고, ego provider는 시작 전 offline fixture로 교체했다. 앱 시험은 localhost/synthetic credential과 기존 관찰 차단 fixture, engine batch/facing은 대역으로 실행했다. 이4파일 변화의 원인은 미확정이며 되돌리거나 내용을 출력하지 않았다. 따라서 전체 전역 런타임 파일 불변으로 일반화하지 않는다. 사용자 `.data`·`output`1,029파일은 별도 사전/사후 해시로 불변을 확인했다.

넓은 프로세스 snapshot의 pytest74115는 검수 부모25139 소유로 종료하지 않았다. 구현 소유4개PID의 exited와 서비스 포트0은 `cleanup-confirmation.json`에 별도로 확인했다.


## 최종 완료 인수

PM `msg_b0ba17f77709`가 독립 검수 `worker_done msg_07eee427034a`(Task `task_ed7d8b3c75af`, Dispatch `ctx_1e4408c47e69`, outcome succeeded·미해결 제품 finding0)를 인수하고 최종 구현을 수용했다. 구현자는 제품/엔진/시험을 추가 수정하거나 검사를 확대하지 않았다. 최종 수용 근거는 앱2598 passed/1 skipped·엔진762 passed·웹543 passed/build·doctor433파일·동일 MP4 최종 셀/시간/형식/폴더DB 비교·사용자1029파일 해시 동일·diff와 자기 서비스 정리다. 실제 overlap 예산중단과 `.grok` 런타임4파일 원인미확정은 한계로 남기며 성공으로 바꾸지 않는다. 커밋·push·PR·merge·배포·유료 생성은 하지 않았다.
