# M3 구현·검증 기록

2026-10-22 KST · GPT 6.1 Sol xHigh 구현 · **최종 독립검수·PM 수용·소유 서비스 정리 완료 · 앞선 후보는 무효**.

Run `run_db69615cf19f`, Task `task_db590fec2577`, Dispatch `ctx_83ba0c1ecd17`, 구현 `term_c2ae39d6-d11d-45e8-9394-3e763786c3c4`. HEAD/main `c48e46ec4c48eac1a1625aa47274dd6ee426897a`. M1+M2 미커밋 원문을 보존하고 PM의 M3 시작 `source-before`와 비교했다. commit/push/PR/merge/배포, 유료 생성, provider/observer/로그인, 실제 사용자 DB open, 공용 sprite-gen·전역 설정 변경은 하지 않았다.

## 구현과 실제 호출

기존 `/v1/projects/{id}/jobs → execute → execute_clip_tools → render_clip → preview → apply_follow → publish_follow → write_project/폴더 동기화`를 확장했다. 새 큐·생성 API·처리 파이프라인은 없다. `preview_restore`와 `compare_clips`를 기존 registry/envelope에 추가하고 `apply_follow`가 accepted follow/restore/compare 후보의 정확한 파일을 새 검수 대기 동작으로 저장한다. 기존 동작·후보·승인·출력은 유지한다.

신규 영상은 기존 process/normalize/finish/render 경로에서 선택 raw/keyed, 실제 MP4 SHA·준비 이미지(있는 경우), 추출 옵션/manifest/report SHA, 원본 투영 셀과 최초 origin 셀을 보존한다. 콘텐츠 ID는 asset/video ID remap과 독립이다. baseline은 현재 최종 RGBA·셀 좌표/geometry·순서·개별 정수 ms·source sample/range에 묶인다. source/origin PNG·manifest는 별도 출력, 이미지는 프로젝트 assets, 동작·프레임·시간·계보는 library/폴더 SQLite에 함께 저장한다. 저장 실패는 기존 completed result/reuseResultAttemptId 경로로 저장만 재시도한다.

`clip_comparison`은 source keyed를 원래 normalization/finish/render 좌표로 다시 투영하고, 원본 영상·raw/keyed·준비 이미지·source/origin 파일을 다시 해시 검증한다. 현재 geometry·샘플 metadata·개별 ms·픽셀과 immutable projection geometry를 확인한 뒤 최초 origin부터 채택한 복원 chain을 재구축한다. 사용자 편집·origin 변조·key/facing·다른 schema/policy·crop/range/sample/시간 불일치는 unknown/저장 차단이다. 픽셀을 편집한 결과를 source로 등록하지 않는다.

고정 upstream v2.45.3 commit `59b2738a2e76ed7043d9691a230396ed6374a336`의 compare/restoration/playback/follow/follow_inspect를 재사용했다. 일반 비교는 `same-sample-defects-v1`/comparison schema1, 복원은 `source-restoration-v5`/repair schema4와 내장 comparison schema6이다. 앱 가변 시간·canonical 좌표는 별도 `frame-room-canonical-source-v1`/구현 SHA policy다. RGBA raw resample과 최종 셀이 정확히 일치할 때만 raw crop 기반 one-step cap을 허용한다. padding/팔레트/배치가 다르면 cap을 추정하지 않고 key hue 증가 픽셀을 보호한다. upstream final-pixel jump/ghost·outline/partial/key gate를 다시 수행한다. `improved/non_regressing/regressed/unknown`은 측정 결함 판정이며 미술 점수가 아니다.

follow는 upstream 공통 outline carry·영역별 Jacobian/불투명/변경 픽셀·소유관계 unknown, stretch floor를 연결한다. 가변 시간은 기존 시간 가중 응답을 유지한다. `readOn`은 실제 strip SHA를 확인한다. `readOnClipId/readOnClipRevisionId`는 같은 영상·구간·crop·배율·마무리의 정확한 원본 sample/keyed 대응을 검증한 뒤 upstream `cut_origin/transported_motion`으로 reading을 운반한다. 다른 hash·구간·보간·불일치 픽셀은 uncertain이며 추정 적용/저장을 막는다. 설정·revision·policy 변경 뒤 stale preview도 차단하고 저장 때 입력과 read-on 원본을 다시 확인한다.

신규 recipe는 `video-processing-v6-sprite-gen-2.45.3-m3`다. 전체 실제 engine/adapter digest를 기존 extraction key·job·결과·retry guard에 계속 묶는다. 미완성 M2/legacy 작업을 현재 코드로 재개하지 않으며 구 완성 결과의 저장만 retry는 유지한다. 기반 pin/qualityVersion와 M1 transport·M2 보호를 보존했다. engine lock의 M3 13파일은 시작 사본 대비 전후/고정 upstream SHA를 기록하며 별도 `clipToolsQualityVersion=2.45.3-m3`다.

UI는 기존 접힌 동작 보완·검사에서 원본 복원/동작 비교, source/origin 상태, 수치 판정과 이유, before/after·가변 시간, 새 동작 저장을 제공한다. CandidateComparison은 외형 시각 비교와 최종 셀 측정 도구의 목적을 구분하고 콘텐츠 ID를 표시한다. 기존 초안/충돌·늦은 응답 보호를 재사용한다.

## M0 M3 6항목 연결

| 역사 대장 ID | 실제 앱 경로·증거 |
| --- | --- |
| `cmd.video-loop-compare` | compare_clips → canonical renderer → upstream same-sample ordering → ClipTools 비교·새 동작 저장. 시계/crop/sample 불일치 unknown, identical non_regressing·실제 회귀 시험 |
| `cmd.video-source-manifest` | video_task sourceReceipt → capture_video → 프로젝트 raw/keyed/source/origin assets·별도 source-manifest.json. 실제 보존 프로젝트 4개 사본의 source2/unknown21/origin23 구분, MP4 재투영·portable 재검증 |
| `cmd.video-loop-repair` | preview_restore → origin/source 재구축 → upstream key/jump/ghost judge → schema4+6 → apply_follow. 합성 두 차례 improved 복원·backup 재복원·key/facing/origin/schema/stale·저장만 retry |
| `cmd.handed-check` | 기존 check_handed → actual rendered cells → marker/board → readonly 결과. 기존 clip-tools/processing 시험 전체 보존 |
| `cmd.video-follow` | preview_follow → 시간 가중 응답·공통 outline carry·stretch floor·read-on whole-cell transported → immutable apply_follow |
| `cmd.video-follow-inspect` | 같은 follow 결과의 슬롯별 Jacobian·solid/changed px·ownership unknown → ClipToolsPanel, upstream inspect/read-on/stretch 시험 |

## 실제 자료·저장 증거

scratch는 `/var/folders/yk/7gcx2d_d3g36kr1klhhz4q700000gn/T/frame-room-m3-impl-eay7l87i`다. 모든 제품 import/pytest는 shell에서 SPRITE_DATA_DIR을 저장소 밖 scratch로 먼저 지정했다. 사용자 프로젝트 폴더 4개는 파일로 복사한 뒤 사본만 열었다. `legacy-source-proof.json`/`legacy-probe-final.log`: **full extraction source2, unknown21, origin unsupported-legacy23**. 두 source는 실제 preview_restore API/worker에서 full extraction을 확인하고 origin 미기록 때문에 복원 unknown으로 남겼다. 역사 M0 JSON/baseline·M1/M2 보고서를 재작성하지 않았다.

`test_absorption_m3.py`의 PIL 합성 계약 그림과 실제 로컬 인코딩 MP4에서 결함 셀2/8을 차례로 source 복원했다. 각 accepted preview→별도 after PNG/WebP/GIF→새 동작→폴더DB, source/origin ID 유지·개별80..91ms·순서와 렌더 픽셀을 확인했다. ZIP restore의 ID remap 뒤 jobs/cache 없이 원본 재투영과 재복원을 확인했고 폴더 재열기도 검증했다. 저장 트랜잭션 실패 뒤 실제 별도 child에서 execute를 금지한 상태로 completed bytes만 재사용했다. 이는 합성 계약 성공이며 GPT 생성 결과나 실제 미술 품질 향상으로 소개하지 않는다.

`m3locked-comparison.json`/`real-app-locked.log`: 기존 보존 Grok MP4의 scratch 사본 SHA `9a1945d761bbbbc9e4d6a05f6a1258d4306a7e43c82e21a2163ec52fd247af31`, 새96×128·구간33–59·8셀·`[125,125,125,167,125,125,125,166]ms`/1083ms. 실제 앱 source/keyed 재투영, 일반 비교 non_regressing 선택 저장, 별도 exports/library/폴더 SQLite·ZIP restore/source/origin ID·cache 없는 재열기가 일치했다. 실제 입력에는 복원할 결함 제안이 없었고 source restoration도 non_regressing·canApply false다. 기존64×128 결과는2셀의 실제 좌측 clipping으로 도구가 거절했으며 기존 출력은 보존했다. width 변경을 품질 비교 우월성으로 해석하지 않는다. GIF 양자화 시간은 기존 형식 한계를 유지한다.

## 첫 후보 검사·고정 이력 (R1으로 무효)

- 최종 앱 전체 `integration-final.log`: **2618 passed, 1 skipped**, 233.66초. skip은 기존 Git에 없는 연구 원본이다.
- 영향 `impact-transport-final.log`:97 passed. source/guard 보강 `guard-source-final.log`:64 passed. 이 수는 전체와 중복이므로 합산하지 않는다.
- 웹 `web-transport.log`:545 passed,28파일. `web-build-final.log`:tsc/Vite production build 통과.
- `doctor-final.log`:**442파일** 원본/승인 patch 무결성 통과. diff check 통과.
- 최종 엔진 video+util `engine-final.log`:**876 passed**,15개 기존 real_rife marker warning,432.62초. 앞선 중간876건은875pass/1fail(구 전역 gain 기대값). 같은 기존 시험을 삭제하지 않고 upstream 영역별 gain·안전 비율 의미로 적응했고 별도14pass다. 새 source/compare/inspect 묶음 중간115pass/설명문1fail도 CLI 설명 수정 뒤 최종 전체에 포함했다.
- 추가 CLI/docs 검사5pass/1fail: `loop-repair.md`·`prompt-assembly.md`의 기존 상대 링크 누락이다. M3 시작 사본의 같은 시험도 같은10링크로 실패한 `engine-docs-baseline.log`를 보존했다. 제품 경로 실패와 구분하며 이 과거 문서 누락을 수정했다고 하지 않는다.
- 중간 앱 전체2613pass/1fail/1skip은 M0 역사 대장 delta allowlist가 M3 CLI/모듈 추가를 모르던 실패다. M0 JSON은 유지하고 시험이 M1→M2→M3 SHA 전이를 모두 확인하도록 강화했으며 최종 전체가 통과했다. 기타 초기 실패/fixture 경계·source key·Path 타입·저장 retry 응답코드 기록은 scratch 로그에 보존했다.

`tested-source-start.json`은 검사를 실행한 제품/계약/시험509파일 SHA다. `candidate-freeze.json`·`m3-vs-m2-files.json`·`m3-vs-m2.patch`는 M1+M2 신규 기준 사본 대비 **34파일**의 전후 SHA/diff다. 후보 문서는 별도이므로 보고서가 제품 SHA를 바꾸지 않는다. 사전/사후4098항목(사용자 자료1029+공용skill3063개 일반 파일 및 Python symlink 대상3+존재하는 지정 auth/config3)의 SHA/크기 변경·누락·추가0을 `preservation-comparison.json`에 기록했다. 동일 범위를 다시 열거해 추가 파일도0임을 확인했다. M2 Grok 런타임4파일 원인은 미확정이며 내용을 출력하거나 되돌리지 않았고 전역 전체 불변으로 일반화하지 않는다.

## ego·독립검수 대기

ego TaskSpace6/p1 `frame-room-m3-20261022`, ownership agent. 기존 공간0을 확인하고 새 공간1개만 만들었다. API14386/18765·worker15381·proxy5173은 구현 소유의 scratch live-data이며 provider/catalog는 실행 전 offline fixture로 바꿨다. 다른 공간·사용자 마우스·Chrome·별도 Chromium·실제 인증을 사용하지 않았다. 최종 build `index-B_mbS2YJ.js`를 reload한 실제 편집 화면에서 restore 요청·improved·source/origin 별도 상태·12슬롯/1026ms·before/after를 확인했다. 최종 빌드에서 실제 새 동작 저장→v3 ACK·새 동작 자동 선택을 확인했고 `ego-journey.json`에서 별도 출력 PNG12개·library·폴더 SQLite·source/origin ID·80..91ms 일치를 확인했다. `ego-smoke-final.log`의 EGO_SMOKE_PASS도 통과했다. 최초 offscreen click timeout 뒤 같은 공간의 DOM 스크롤로 위치를 바로잡고 실제 click을 성공시켰으며 timeout 자체를 성공으로 세지 않는다. screenshot·다른 전체 UI 여정은 미검증이다. PM05:20UTC 통보 후 ego 조작을 중단하고 같은 TaskSpace6/p1을 독립검수에 넘겼다. 공간/서비스 정리는 사용 완료·최종 인수 때 갱신한다.

PM candidate_ready 후에도 이 구현 세션은 검수 수정 대기를 유지한다. 독립 검수 미해결0·PM 최종 수용 전 worker_done하지 않는다. 유료 생성·실제 provider/observer·전역 설정·Git 게시·배포는 생략했으며 실제 복원 미술 우월성·전체 다른 UI 여정·다른 장치 성능은 검증하지 않았다.

추가 최종 대조: PM 사전4092파일도 SHA 변경·누락0(`pm-preservation-comparison.json`)이며, 최종 검사 후509파일 source SHA 변경0이다. 모든 필수 통과 수는 동일 고정 소스를 기준으로 하며 기존 docs10링크 실패는 별도 한계다.


## M3-R1 수정·재후보 준비

독립검수 P1은 최초 후보의 validate_apply가 source 증거를 다시 읽고도 report.source/origin/baseline을 그 실 identity와 직접 대조하지 않던 문제다. 최상위와 내장 comparison의 id/sha를 함께 변조하면 저장됐다는 재현을 인수하고 첫 후보를 무효화했다. `candidate-freeze-before-r1.json`과 PM의 `candidate-before-r1` 사본에 첫 소스를 보존했다.

R1은 세 파일만 수정한다: `clip_comparison.py`의 정책에 실제 clip_tools_task 소스를 포함하고, `clip_tools_task.py`의 공통 API/execute/publication 검증이 현재 렌더 source 좌표/슬롯·실 source/origin/baseline·실 after PNG의 candidate identity를 직접 대조한다. 일반 비교도 source/origin을 명시하고 실제 선택 clip과 candidate를 연결한다. 최상위/내장 identity 및 전체 settings/source/report/axes/verdict/canApply는 검증된 report.json 승인 바이트와 일치해야 한다. 변경 없는 복원을 improved로 꾸민 경우 실제 baseline/candidate 동일성으로도 거절한다. 저장 시 follow 효과를 다시 실행하지 않으며 completed bytes 저장만 retry를 유지한다.

추가 no-op 지적도 같은 파동에서 반영했다. 표시된 unchanged를 신뢰하지 않고 실제 after RGBA가 현재 렌더 source.pixelHashes와 같을 때만 no-op으로 판단한다. 부모 증거가 유효하면 source/origin·기존 unsupported 상태를 유지한다. 부모 geometry/sample이 무효면 `parent-source-evidence-unverified`를 보존해 새 geometry로 무효 증거가 되살아나지 않는다. 실제 warp의 source 복원은 계속 follow-source-warp-unverified이며, 일반 비교 검증은 아래처럼 분리했다.

`r1-parent-final.log` **101 passed**: DB와 report 파일/해시까지 함께 위조한 source/origin/baseline/candidate × enqueue/execute/publish, 일반 비교4 identity·내장 불일치·좌표 변조·no_change 판정/axes/settings/source 변경, 정상 no-op→비교/복원 및 무효 부모2종을 검증했다. 독립 검수자가 작성한 재현 파일을 구현 환경에서 재실행한 `independent-probe-r1-parent-final.log`도 **10 passed**다. 이는 검수자의 최종 재수용을 대체하지 않는다. 직전 R1 중간 로그 `r1-impact-final.log`212pass·`integration-r1-final.log`2639pass/1skip은 부모 guard 추가 전 실행 이력으로 분리한다.

중간 `tested-source-r1-start.json`509파일·`r1-vs-candidate-files.json`3파일 기준 전체 앱은 `integration-r1-parent-final.log` **2641 passed, 1 skipped**였다. 이 실행 뒤 follow 일반 비교를 수정했으므로 최종 재후보의 전체 앱 결과와 구분한다. engine/web/build 소스 변경0을 대조했으므로 기존876/545/build 통과를 동일 소스 근거로 재사용하며 postfix 직접 재실행으로 쓰지 않는다.

자체 API14386/worker15381, 후속 R1 API89672/worker95153은 정확한 명령을 확인하고 종료했다. 최종 API4925(18765)/worker12892는 같은 scratch live-data에서 수정 소스를 새로 로드했고 offline provider fixture를 시작 전에 유지했다. proxy5173은 불변이며 같은 ego TaskSpace6/p1·같은 project URL을 유지한다. 새 R1 최종 fixture clip은 `76e4d6ab-52ed-4b01-9f3b-77b1170e44d4`(합성 복원 대상 · R1 최종)이다. 이전 fixture의 source receipt를 새 policy로 덮어쓰지 않고 새 source/후보를 명시적으로 추가했다.

`live-http-r1-parent-final.log`/`live-http-r1-result.json`: 실제 수정 API→새 worker에서 정상 복원·새 동작 저장, 별도 PNG12개/library/폴더DB·source/origin 보존을 확인하고, source origin을 DB/report SHA까지 함께 위조한 뒤 실제 HTTP apply424·추가 동작/수정 없음도 확인했다. `real-app-r1-parent-final.log`/`m3r1final-comparison.json`은 보존 실제 MP4로 source 투영·선택 저장·backup/ID remap·cache 없는 재열기를 다시 통과했다. 브라우저는 독립검수 사용을 기다리며 구현자가 조작하지 않는다.

## 중간 재후보: follow 뒤 일반 비교 (read-on 열수 수정 전)

PM 계약 판정에 따라 복원 제약과 일반 same-sample 비교를 분리했다. `read_comparison_evidence`는 공통 source 원본/정책/현재 RGBA/geometry/개별 ms/sample 검사를 유지하고, 실제 warp에서는 `followProof` schema1의 부모 렌더 입력·설정·선택 read-on 입력을 프로젝트 assets로 다시 읽는다. 부모 origin부터의 복원 또는 이전 follow 계보를 검증한 뒤 고정 엔진으로 follow를 재현해 최종 픽셀을 대조한다. 단순 unsupported 무시나 현재 편집을 source로 승격하는 경로는 없다. source/origin은 불변이며 복원은 계속 unknown이다. 잘못된 부모·누락 proof·정책/시간/sample/설정/readOn/보간은 일반 비교도 unknown이다. 계보 검증은 최대64단계이며 초과 시 unknown이다.

`saved_render`는 해당 clip/frames/groups/alignments만 보존하고 sourceProcessing 중복은 제거한다. 비교 선택 저장과 no-op follow는 기존 proof를 보존한다. 일반 비교 시의 재현은 부모 증거 검증이며 승인 후보의 출력은 기존 미리보기 바이트를 그대로 저장한다. 신규 의존성·API·생성 provider는 추가하지 않았다. 기존 origin 복원 chain 재구축을 `_restoration_state`로 공유한다.

합성 계약 그림의 균일한 몸 안 타원 `[32,36,16,18]`은 gain8에서도 changedPx0이므로 실제 warp 시험에 사용하지 않았다. `[18,36,12,25]`, gain3에서 실제 변경 픽셀을 확인하고 canonical/transported 각각 parent→warp·warp→parent의 upstream 측정과 회귀, self 비교 non_regressing 선택 저장, 별도 PNG12개/library/폴더 SQLite·개별 시간·source/origin 유지, 복원 unknown, ZIP/asset-video ID remap 뒤 jobs/cache 없는 비교를 검증했다. `follow-backup-final.log` **2 passed**다. 무효 proof8종8pass 뒤 settings 범위 음성 검사를 추가해 최종 전체 앱에 포함했다. 중간 `follow-r1-impact.log`109pass/2fail은 수정 전 DB 파일명을 import한 시험 실행이며, 실제 `project.sqlite3/projects.snapshot`로 고친 다음 위2건이 통과했다. 초기 helper 분리의 iq 참조 누락은 수정했고 실패 로그도 보존했다. 기존 시험을 삭제하지 않았다.

`candidate-freeze.json`/`tested-source-follow-start.json`은 최종 제품·계약·시험 **509 SHA**, `m3-vs-m2-files.json`/`m3-vs-m2.patch`는 M3 시작 사본 대비 **34파일**이다. 직전 R1 대비 clip_comparison/clip_tools_task/CLIP_TOOLS 계약/M3 시험4파일만 변경했다. 중간 앱 `integration-follow-final.log`는 **2652 passed, 1 skipped**, 308.84초다. skip은 기존 연구 원본 미포함이다. 동일 고정 소스의 doctor442·diff check 통과, 엔진876/웹545/build는 소스 SHA 불변 근거로 재사용한다. `source-follow-verification.json`의509 변경0, `preservation-follow-comparison.json`의4098 SHA/크기 변경·누락0을 확인했다.

최종 실제 명령은 저장소 root에서 `SPRITE_DATA_DIR="$(cat /tmp/frame-room-m3-impl-current)/pytest-follow-full" engine/sprite-gen/.venv/bin/python -m pytest tests/integration -q`, `SPRITE_DATA_DIR="$(cat /tmp/frame-room-m3-impl-current)/doctor-follow" engine/sprite-gen/.venv/bin/python scripts/doctor.py`, `git diff --check`다. `PYTHONPATH="$PWD:$PWD/tests/integration"`와 독립 scratch를 지정한 검수자 외부 probe는 원래 R1 10pass였고, 추가 nonzero3건은 균일한 몸 타원에서 unchanged=False를 가정해 첫 assert에서 실패했다. 검수파일을 수정하지 않고 PM에게 실제 변경이 있는 타원/강도를 전달했다. 이 중간 로그를 최종 독립 합격으로 표시하지 않는다.

소유 API4925/worker12892를 정확한 명령 대조 후 종료하고 고정 소스로 **API60661:18765/worker61085**를 재시작했다. 같은 offline fixture·live-data·proxy5173·ego TaskSpace6/p1·project URL을 유지하며 신규 source clip은 `2becc63b-a95a-4604-b0e8-86d681b19ba4`(합성 복원 대상 · follow 비교 최종)다. `live-http-follow-final.log`는 실제 HTTP에서 정상 복원/저장·보고서 identity 위조424·nonzero follow→일반 측정→선택 저장→source 복원 unknown을 통과했다. `live-http-follow-result.json`에 job/clip/시간·출력/library/폴더 DB 일치를 기록했다. 첫 HTTP 검증은 기존 outbox commit 뒤 폴더 flush 전을 읽어 일시 불일치했고, 원래 outbox 반영을 기다리는 검증으로 최종 일치를 확인했다. 즉시 폴더 동기화로 일반화하지 않는다.

`real-app-follow-final.log`/`m3followfinal-comparison.json`: 보존 실제 MP4를 최종 policy로 다시 처리해 source 투영, 실제8셀/1083ms·96×128, non_regressing 선택 저장·별도 출력/library/폴더 DB·backup/cache 없는 재열기를 재통과했다. 실제 영상에 accepted 복원 제안이 없다는 한계는 유지한다. 마지막 재열거에서 기존4098 변경·누락0, output/공용skill/authconfig 추가0을 확인했다. `.data/orca-session-archives/2026-10-22-completed-pm-cleanup-150025/` 아래 세션 정리 아카이브10개가 추가되어 메타 경로로만 출처를 기록하며 생성 세션은 미확정이다. 현재 M3 PM도 생성하지 않았음을 확인했다. 구현자가 생성·열람·삭제하지 않았으며 전체 .data 추가0으로 일반화하지 않는다. 브라우저 최종 독립검수와 서비스/공간 정리는 최종 수용 단계에서 갱신한다.


## 최종 재후보: 원본12/대상8 read-on SHA

독립검수의 열수 오류를 수용해 `_verify_follow`가 readOn strip을 재구성할 때 대상 셀수가 아닌 실제 읽기 원본의 셀수로 columns를 정하도록 수정했다. `[reading12 → target8]` whole-cell subset에 명시적 원본 SHA가 있는 경우도 동일한 strip 바이트를 검증한다. 이 수정으로 앞선2652pass 후보를 무효화했으며 실행 이력은 보존했다.

새 `test_transported_subset_reading_hash_keeps_original_strip_columns_after_save_and_backup`은 source12/phase3 subset8, 실제 nonzero warp, explicit SHA, 일반 비교/선택 저장, source/origin·시간 보존, ZIP/ID remap/jobs-cache 없는 재검증·source 복원 unknown, 잘못된 SHA uncertain/409, 부모 보간 미증명 unknown/저장409를 검증한다. `read-on-subset.log` **1 passed**, 8.75초다. 기존 시험을 삭제하지 않았다. 검수자 외부 probe도 구현 scratch에서 **14 passed**, 35.51초(`independent-probe-subset-final.log`)이며 독립 검수자의 최종 수용을 대체하지 않는다.

`candidate-freeze.json`/`tested-source-subset-start.json` **509 SHA**, M3-vs-M2 **34파일**로 재고정했다. 직전 후보 대비 clip_comparison.py와 test_absorption_m3.py 2파일만 변경했다. `SPRITE_DATA_DIR="$(cat /tmp/frame-room-m3-impl-current)/pytest-subset-full" engine/sprite-gen/.venv/bin/python -m pytest tests/integration -q`는 `integration-subset-final.log`에서 **2653 passed, 1 skipped**, 344.78초로 통과했다. doctor442/diff는 다시 통과했고 엔진876/웹545/build는 같은 엔진·웹 소스 SHA 근거로 재사용한다.

최종 policy의 `real-app-subset-final.log`/`m3subsetfinal-comparison.json`은 보존 실제 MP4 source 재투영·8셀/1083ms·일반 non_regressing 선택 저장·별도 출력/library/폴더 SQLite·ZIP/ID remap·cache 없는 재열기를 다시 통과했다. 이전 source receipt를 새 policy로 덮어쓰지 않고 새 프로젝트에서 처리했다. 실제 accepted 복원 제안이 없다는 한계는 유지한다. API60661/worker61085는 정확한 명령 대조 후 종료했고 같은 scratch UI 프로젝트에 새 full12/subset8 source fixture를 구축 중이다. 새 PID/HTTP/ego·보존·정리는 후속 결과에 갱신한다.


최종 서비스는 **API97757:18765/worker97827**(offline fixture, 같은 live-data), proxy5173이다. 기존 UI project `668133f3-dc8a-4f66-8b20-72faedae5695`, full12 `779b5861-94c9-4d35-8b3c-30bc91c218e7`, subset8 `5aa55cfe-4399-4d01-9fd2-2468c3407e18`, ego TaskSpace6/p1을 그대로 독립검수에 인계했다. `browser-project-subset-final.json`이 명시적 인계 식별자다. 구현자는 ego를 조작하지 않으며 최종 검수 수용 전 서비스를 유지한다.

`live-http-subset-final.log` **FINAL_HTTP_SUBSET_READON_COMPARE_SAVE_GUARDS_PASS**: 원본12의 source 복원 improved 미리보기, explicit 원본 strip SHA→대상8 실제 follow, non_regressing 일반 비교·선택 저장, after PNG8개/library/폴더 SQLite·`[83,84,85,86,87,88,89,90]ms`/692ms 일치, source/origin 불변, warp 복원 unknown, 잘못된 readOn 저장409와 DB/report/해시를 함께 위조한 origin 저장424·프로젝트 변경 없음이 실제 HTTP→새 worker에서 통과했다. 식별자와 결과는 `live-http-subset-result.json`에 보존했다. 검증은 기존 outbox flush를 기다린 최종 폴더 일치이며 즉시 동기화로 일반화하지 않는다.

누적 UI 프로젝트 snapshot10,346,637bytes에서 fixture 구축·HTTP 검증이 느렸지만 정상 완료했다. 완료 확인과 전환 명령을 같은 도구 호출에 이어 실행해 완료를 반영하기 전 작은 추가 scratch fixture를 생성한 것은 불필요한 실행이었다. 추가 project `7ac55f3b-4f8d-41af-996a-98eccb3aeea7`은 미사용 상태로 보존했고 기존 검수 URL/대상·ego 공간은 바꾸지 않았다. `browser-project-r1.json` 포인터도 명시적 기존 subset-final 인계와 맞췄다. 추가 생성/진단/제품 수정은 중단했다.

`source-subset-verification.json`의509 SHA 변경0, `preservation-subset-comparison.json`의 기존4098 SHA/크기 변경·누락0을 확인했다. 재열거10추가는 `.data/orca-session-archives/2026-10-22-completed-pm-cleanup-150025`의 별도 세션 정리 기록이다. PM이 README/cleanup-result 메타에서 사용자 요청에 따른 M1/M2 PM 정리와 M3 세션 유지 기록을 확인했다. 현재 M3 PM/구현 세션의 생성 행위로 단정하지 않고 별도 자료로 보존하며 삭제·되돌림하지 않았다. 제품 원본/출력1029와 공용skill/auth/config은 그대로다. 실제 사용자 DB를 열지 않았고 원래.data 전체 추가0으로 보고하지 않는다.

최종 독립검수 수용·ego/소유 서비스 정리는 아직 대기다. 앱 skip1·엔진 기존 warning15·기존 docs10링크 실패·실제 영상 accepted 복원 제안 없음·실제 provider/observer/다른 장치 성능 미검증은 기존 한계를 유지한다. commit/push/PR/merge/배포는 하지 않았다.


최종 ego 검수에서 TaskSpace6 not found가 보고되어 PM 지시에 따라 원래 CLI `/Users/cheng80/.local/bin/ego-browser`·기본 service(별도 EGO_SERVER_NAME/BROWSER_BIN 없음)의 `listTaskSpaces()`만 읽었다. inventory는 `[]`였고 새 공간 생성/이동/finish를 하지 않았다(`ego-original-space-inventory.json`). 공간 소멸 원인은 미확정이며 구현자/현재 M3 PM의 종료로 단정하지 않는다. PM이 검수자에게 새 agent 소유 최종 공간1개 생성/정리를 맡겼다.

PM 요청으로 이미 만들어 둔 작은 project7ac55...를 읽어 source 재투영/현재policy·library/폴더 DB 일치를 확인했다. full12 clip81b57bed-cfc3-45c1-9b1c-3401a402c691, subset8 clipd12947fd-1b32-490f-bc7f-2224aec96909, snapshot137480bytes, 경로와 URL은 `small-final-proof.json`/`browser-project-small-final.json`에 있다. 새 생성 없이 검수자가 이 기존 fixture를 재사용할 수 있다. 제품509 소스와 서비스를 유지한다.


최종 policy identity는 이미 실행한 `m3subsetfinal-comparison.json`의 실제 processing/restoration 영수증과 최종509 manifest를 재사용했다(`policy-identity-final.json`). 새 검사/재처리는 하지 않았다.

| 고정 항목 | 실제 최종 값 |
| --- | --- |
| video processing VERSION | `video-processing-v6-sprite-gen-2.45.3-m3` |
| processing engineDigest | `823cc81298696d190255dabb333f470046752d0f287d6eac979fc9186c446500` |
| clip bridge | `frame-room-canonical-source-v1` |
| clip implementation SHA256 | `2f15d47894a0771010f79d6b1ffbce70754fe9ab70cc90ef85e1d902b4493109` |
| engine/engine-lock.json SHA256 | `b8b7dcd6411d361aaae2d0a09609993eab708601b62c46024976cce355d8adfe` |
| source restoration | `source-restoration-v5`, `key-protected-source-copy-one-step-cap-jump-ghost-guard-v1`, repair4/comparison6 |
| general comparison | `same-sample-defects-v1`, comparison1 |
| raw cap | `exact-raw-projection-else-protect` |


검수자가 첫 ego6 성공 여정의 조작 순서를 요청해 `ego6-success-notes.md`에 공유했다. 당시 실행은 inline으로 별도 완결 .mjs가 없으며, 실제 결과 근거는 기존 `ego-journey.json`/`ego-smoke-final.log`다. 안내는 동일 웹 SHA 소스의 role/label locator와 슬롯 inspector의 scrollIntoView→실제 click 흐름을 연결한 재현 참고이며 새 실행이나 원본 script 전문으로 주장하지 않는다. 검수자의 TaskSpace7을 구현자가 조작하지 않았다.


## 최종 독립검수·정리

PM의 `msg_767d46eea799`는 독립 검수 `msg_88c513dd3587`에서 최종 ego UI 저장·stale 차단, PNG12/WebP/strip/rendered/library/폴더 SQLite의 실제 RGBA·슬롯 순서·앵커·80..91ms/1026ms·source/origin 보존이 통과했고 TaskSpace7 finish가 성공했음을 확인한다. 구현자가 검수 공간을 직접 조작하거나 finish를 중복 호출하지 않았다. 기존 TaskSpace6 부재 원인은 미확정으로 유지한다.

정리 전 기본 ego inventory에서6/7을 필터해 `[]`를 확인했다. 소유 명령을 다시 대조한 API97757(18765), worker97827, proxy77612(5173/실행 세션75664)만 SIGTERM으로 종료했다. 종료 후 세 PID 생존0·18765/5173 TCP LISTEN0이며 다른 프로세스·세션·공간·자료는 변경/삭제하지 않았다. `cleanup-final.json`에 전후 명령·PID·포트와 독립 finish 근거를 보존했다. 완료된 시험/fixture/HTTP 프로세스는 남지 않았으며 모든 scratch 프로젝트·원본·출력은 보존했다.

`cleanup-source-preservation.json`에서 최종509 SHA 변경0, 기존4098 SHA/크기 변경·누락0, 별도 세션 정리 아카이브10추가만 다시 확인했다. 최종 제품검사 결과는 앱2653pass/1skip·검수자 probe 재실행14pass·동일 엔진876pass/웹545pass/build 재사용·doctor442/diff 통과이며, 추가 재처리/검사 확대는 하지 않았다. 최종 독립보고서의 PM 수용 후 별도 요청 때만 worker_done을 보낸다. commit/push/PR/merge/배포는 하지 않았다.


2026-10-22T06:51:01Z PM `msg_765a7ea3729f`에서 최종 source/test/UI와 cleanup_complete를 수용했다. 제품/검사 추가 없이 이 보고서에 수용을 기록하고, 마지막 inbox 확인 뒤 Task/Dispatch의 worker_done succeeded를 정확히 한 번 보낸다.
