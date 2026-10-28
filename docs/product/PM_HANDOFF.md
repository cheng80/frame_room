# PM 세션 인계

갱신: 2026-10-28 KST. **M3까지 제품 구현·독립 검수 완료. 다음은 M4a이며 M4a/M4b/M5/M6는 미착수다.** 전체 M0–M6 진행 승인과 모델·보존 규칙은 유지한다. 이번 요청은 핸드오프 갱신과 기존 M1–M3 변경의 커밋·푸시이며, 새 기능 착수·PR·merge·배포는 포함하지 않는다.

## 2026-10-28 게시·다음 작업 기준

- 사용자의 명시적 요청은 **`핸드오프 갱신 및 커밋 푸시`**다. 기존 M1–M3 제품·엔진·계약·시험·보고서와 작업 지침을 검증해 현재 `main`에 게시한다. 아래 2026-10-22 기록의 미커밋·게시 미승인 표시는 당시 상태이며 이번 승인 범위에서는 대체된다. 당시 검증·실패·세션 식별자는 역사로 보존한다.
- 게시 전 로컬 `HEAD`와 실제 원격 `refs/heads/main`은 모두 `c48e46ec4c48eac1a1625aa47274dd6ee426897a`다. 검증 착수 전 변경 목록은 수정 73파일·신규 50파일·staged 0이었으며 모두 M1–M3와 그 지침·문서다. 이후 게시 대상 123파일을 경로별로 stage하고 검사한다. 이번 게시 기준은 이 절을 포함하는 커밋이며, 이후 인수자는 `git log -1 --oneline`·`git status -sb`·`git ls-remote origin refs/heads/main`으로 로컬/원격 실제 기준을 다시 확인한다. 현재 브랜치·사용자 변경을 임의로 되돌리거나 이전 M0 기준으로 실행하지 않는다.
- 10월 28일 현재 확인: 엔진 lock SHA `b8b7dcd6411d361aaae2d0a09609993eab708601b62c46024976cce355d8adfe`는 M3 최종 기록과 일치하고 원본/승인 패치 442파일 해시 및 `git diff --check`가 통과했다. 기반 엔진 표시는 `2.12.1`, 영상 품질은 `2.45.3-m2`, 동작 도구 품질은 `2.45.3-m3`이며 v2.45.3 전체 흡수 완료를 뜻하지 않는다.
- 웹 `dist`는 `index-B_mbS2YJ.js`에 RIFE TTA·루프 겹침 보정·원본 복원·동작 비교·영역별 실제 변형 검사·완성 결과 저장 재시도 UI를 포함한다. 설명서 `public/guide/content.json`과 `dist/guide/content.json`에는 해당 신규 안내가 아직 반영되지 않았다. 앱에 기능이 들어간 것과 설명서 최신화를 구분한다.
- **촬영 미완료:** 2026-10-24 ego `Page.captureScreenshot`의 기본 PNG·직접 CDP PNG/JPEG·viewport clip이 모두 시간 초과했고 완성 스크린샷은 0장이다. 실제 paint layer/canvas 부분 PNG 7개만 보존했으며 전체 화면·GPT 생성 결과로 소개하지 않는다. [촬영 보고서](/Users/cheng80/.codex/visualizations/2026/10/20/01a15781-f84d-7591-b17f-146cce24ebb6/frame-room-updates-2026-10-24/report.md). `open -g`에도 ego가 전경으로 전환된 부작용을 보고한 뒤 OS 창 조작을 중단했다. 재촬영 때 사용자 창·마우스를 가로채는 복구를 반복하지 않는다.
- 10월 28일 검증 착수 전 프로젝트 Orca 터미널 0개, 앱 포트 5173/8765/18765 LISTEN 0이었다. 종료된 M3 PM/worker와 10월 24일 촬영 Task `task_e12c2752a393`/Dispatch `ctx_eeb507f16208`는 재사용하지 않는다. 촬영 Task는 `failed`로 정산했으며 TaskSpace1 `finish({keep:[]})`·직접 API/worker 종료를 확인했다. M3 제품 합격과 촬영 실패는 별개다.
- 기존 M3 구현·검수 scratch는 현재 재사용할 수 없다. 아래 절의 `/var/folders/.../frame-room-m3-*`는 당시 증거 위치다. 새 작업은 저장소의 확정 소스·보고서를 기준으로 새 격리 자료를 준비하고, 제품 import 전 `SPRITE_DATA_DIR`을 먼저 지정한다. 실제 사용자 DB·원본·인증·공용 스킬은 시험 대상으로 열거나 수정하지 않는다.
- 이번 게시 전 검증 Run은 `run_e21216917c11`, 전용 조율 handle은 `term_de734b72-7bd6-4898-97ab-7b4f85179f2d`다. 독립 검토 Task `task_782556ccc9b1`/Dispatch `ctx_ed5e0a878e1b`/handle `term_9a778d8b-afb1-4a96-ba0c-ba81e75c468e`는 Orca CLI의 요청/실효 `codex / gpt-6.1-sol / xhigh`와 `turn_started`가 일치한다. 이번 실제 회귀 검증 결과와 세션 정리는 아래 결산에 기록한다. PM은 제품 코드를 수정하지 않았다.
- 게시 전 staged 상태에서 M0 guard 2건의 분류 오류를 독립 재현해 게시를 보류했다. 기준에 `local=null`로 남은 선언 신규 엔진·시험파일의 변화 분류와 후속 보고서를 M0 portable 자료로 취급하던 검사 범위를 `test_absorption_m0.py` 한 파일에서 수정했다. 구현 Task `task_b4417c148972`/Dispatch `ctx_78646f95b80d`/handle `term_be004a67-7973-488e-9ef2-69608a23dfa7`도 요청/실효 `codex / gpt-6.1-sol / xhigh`·`turn_started`가 일치한다. 기존 M0 JSON/baseline·엔진 lock·제품 기능은 보존했다. Git untracked/staged/committed의 SHA chain·실파일·승인 patch·불허 변경 탐지와 M0 경로금지·전체 milestone credential 차단 회귀 30개를 추가했다.
- 사전 소스 741파일·사용자 `.data`/`output` 1,055파일 SHA/크기와 patch·Git 상태는 `/Users/cheng80/.codex/visualizations/2026/10/24/01a16d64-f09d-7e52-bdd6-6b22abd4eda4/publication-2026-10-28/`에 보존했다. `.data`/`output`, 인증, 촬영 PNG 및 임시 로그는 Git 게시 대상이 아니다.

### 남은 필수 범위와 인수 순서

1. **M4a — 재생 의미·동작 제작/미리보기:** `loop`·`once-return`·`once-hold`·`lifetime`, 정지 파생 동작, 플레이어·편집/job snapshot·validators·runtime 차기 버전·GIF/WebP·backup/restore를 함께 연결한다. 기존 runtime v1은 계속 읽고 출력 형식의 표현 한계를 표시한다.
2. **M4b — 방향 세트·게임 출력:** 방향별 clip/revision·공통 크기·지면/anchor를 묶고 현재 편집 결과의 canonical bake에서 결정적인 `game-pack`을 만든다. 기존 atlas/runtime/PNG/Aseprite/animations ZIP과 개별 동작을 보존한다.
3. **M5 — 자료·음원 제작:** 시트 추출·배치/알파 보완, `pixel-draw`, UI kit·타일·로고, SFX/BGM의 생성·가져오기·듣기·정규화·loop/crossfade·샘플 시간·이벤트·Opus/AAC·sound-only pack을 전용 자료형·폴더 저장·백업/복구까지 연결한다.
4. **M6 — 나머지 제작·편집·장면 도구:** 방향/시트 제작·curation·atlas 재구성·팔레트 변형, 영상 extend/edit·시작/끝/참조 이미지, layer/rig·호흡·그림자·QA, 생성형 중간 프레임, ambient loop, scene 배치/렌더·Phaser/Flame 출력을 전체 대장과 대조해 연결한다. 이미 구현된 도구는 재사용한다.
5. **전체 완료 판정:** 공개 기능 84항목 모두의 앱 진입·자료형별 별도 출력/library/폴더 DB·재열기/backup/restore·검증 근거를 채운다. 영향 및 전체 필수 검사·웹 빌드·독립 검수·ego 실제 제작/저장/출력 여정, 신규 설명서·화면 캡처를 마친다. 실제 provider 인증/생성·장치별 성능은 승인된 범위에서 별도로 실측하며 모의 성공을 실제 생성 성공으로 기록하지 않는다.

다음 큰 기능을 맡을 새 PM은 [전체 계획](SPRITE_GEN_ABSORPTION_PLAN_2026-10-21.md)과 [M3 독립 검수](absorption/M3_REVIEW_2026-10-22.md)를 읽고 새 소스 기준을 고정한다. 모든 역할은 `--agent codex --model gpt-6.1-sol --effort xhigh`, 기능별 구현1·독립검수1, PM 제품 수정 금지·Orca 오케스트레이션 규칙을 유지한다. 현재 환경에는 컨텍스트 사용률 수치가 없어 80% 자동 감시를 주장하지 않는다. 이번 게시 작업에서 M4a 세션을 생성하지 않는다.

### 게시 전 검증·정리 결산

- **오늘 최종 전체 integration: 2,683 passed / 1 skipped, 335.88초.** skip은 `test_pipeline.py:576`의 Git에 없는 기존 연구 원본이다. M0 guard 수정 전 staged baseline은 2,651 passed / 1 skipped / 2 failed였으며, 두 실패를 숨기거나 과거 통과로 대체하지 않고 수정 후보에서 전체를 다시 실행했다.
- **오늘 엔진 `tests/video tests/util tests/test_lsq.py`: 878 passed, 450.98초, 기존 `real_rife` marker 경고 15개. 웹 전체 545 passed / 28파일, TypeScript/Vite production build 통과.** 엔진·웹은 이번 수정 전후 SHA가 같아 오늘 실제 실행 결과를 재사용했다. 새 빌드도 `index-B_mbS2YJ.js`이며 신규 UI를 포함한다. 전체 엔진의 다른 도메인·문서 시험까지 다시 실행했다는 뜻은 아니다.
- 구현의 M0+engine guard **77 passed**와 독립 재실행 **77 passed**, 추가 독립 변조·누락 probe **11조건 통과**를 확인했다. 이 수는 전체 integration과 중복이므로 합산하지 않는다. 후보 `test_absorption_m0.py` SHA는 `ae07bc246a0851f3795ab488b867bfd6c567f4ca286f02631cc88ea4dd144737`다.
- Python 초회는 검사자가 지정한 pytest `--basetemp`의 부모 폴더 부재로 setup 오류가 났다. scratch 부모만 준비해 동일 소스로 재실행했고 초기 실패 로그를 보존했다. 이 실행 환경 오류와 이후 실제 staged guard 두 실패를 구분한다.
- 엔진 원본/승인 patch **442파일 SHA 불일치 0**, diff 검사 통과. 이번 게시 작업의 소스 변화는 PM 핸드오프와 구현자의 M0 시험뿐이며 M1–M3 제품 코드·lock·기존 보고서·M0 역사 JSON은 변경하지 않았다. 최종 사용자 `.data`/`output` **1,055파일 SHA/크기 변경·누락·추가 0**을 PM과 검토자가 각각 확인했다. 독립 검수 합격·미해결 제품/검증 finding **0건**, 게시 범위 123파일 적합을 수용했다.
- 실제 브라우저 재검증·재촬영, provider 인증/생성·observer·유료 호출·다른 장치 성능·배포는 하지 않았다. 기존 엔진 문서의 10개 링크 누락은 10월 22일 시작 사본에도 있던 별도 한계이며 이번에 고쳤거나 해당 문서 시험을 재실행했다고 기록하지 않는다. 새 설명서와 완성 화면 캡처는 남은 작업이다.
- 상세 실행 명령·종료코드·JUnit·후보 diff·보존 대조는 위 `publication-2026-10-28/implementation/report.md`·`report.json`, `review/review.md`·`review-final.json`과 로그에 보존한다. 주요 비밀정보 패턴 hit 0을 확인했으며 heuristic 검사를 비밀 부재의 완전 증명으로 확대하지 않는다.
- 구현 `msg_0c8ec79aed84`·검토 `msg_2af18c0a13df`의 정확히 1회 `worker_done succeeded`를 확인했다. 두 Dispatch 모두 `worker-release`가 **released / closed_agent_terminal / transcript captured**이며 Run의 released 2·active/reclaimable 0, 진행 Task 0이다. 이번 조율 shell도 종료 응답 `ptyKilled=true`, 프로젝트 터미널 `totalCount=0/truncated=false`를 확인했다. 이전 세션이나 다른 프로젝트는 정리하지 않았다.

## 2026-10-22 사용자 요청에 따른 세션 정리

- 현재 Codex 채팅의 명시적 요청 `Orca 세션 정리`에 따라 M3 PM `term_6a03edc7-a106-4325-8d75-23aaa0ea7c12`과 보존 구현 `term_c2ae39d6-d11d-45e8-9394-3e763786c3c4`의 완료·입력 대기를 확인하고 종료했다. 두 close 영수증 모두 `ok=true/ptyKilled=true`, 종료 후 프로젝트 terminal list는 `totalCount=0/truncated=false`다.
- 출력·정리 영수증·이 문서와 M3_RUN의 변경 전 사본은 `.data/orca-session-archives/2026-10-22-m3-cleanup-163438/`에 보존했다. 화면/worker 출력은 제한된 기록이며 전체 대화 아카이브가 아니다. 프로젝트 자료·미커밋 제품 변경·기존 Task/Dispatch 이력은 유지했다.
- 구현의 orchestration 이력은 `retained/user_takeover`, 검수는 `released/transcript captured` 그대로다. 이번 구현 종료는 사용자 소유 세션의 명시적 정리이며 `worker-release` 성공으로 바꾸어 기록하지 않는다. 두 Task 모두 succeeded/completed, reclaimable0·프로젝트 터미널0이다.
- 아래 M3 수용 당시의 종료 확인 대기 기록은 이 정리로 해소됐다. 종료된 PM/worker handle을 재사용하지 않는다. 다음 PM은 이 문서와 M3 보고서를 읽고 실제 현재 소스 기준을 고정한 뒤 M4a를 인수한다. 이번 요청에서 새 PM 생성이나 M4a 작업 배정은 하지 않았다.

## 2026-10-22 당시 기준·M3 결산·다음 M4a

- PM `term_6a03edc7-a106-4325-8d75-23aaa0ea7c12`, Run `run_db69615cf19f`. 자신의 현재 prompt·모델 `GPT-6.1-Sol xhigh`를 대조했다. PM은 제품 코드를 수정하지 않았다. 이전 M2 인수 status `msg_604e0e468ee5`/확인 `msg_41772c9dec81` 후 M3 구현1·독립검수1을 운영했고 두 requested/effective codex/gpt-6.1-sol/xhigh·turn_started가 일치했다. Opus는 사용하지 않았다.
- 구현 `task_db590fec2577`/`ctx_83ba0c1ecd17`/`term_c2ae39d6-d11d-45e8-9394-3e763786c3c4`, 검수 `task_a6428ecb7df9`/`ctx_53dec829ea74`/`term_de33c628-3151-4602-9e26-bbdc3753f145`. 둘 다 worker_done succeeded(구현 `msg_442035f31f10`, 검수 `msg_d93273cce0ac`). 검수는 released·transcript captured·closed다. 구현 release는 **retained/user_takeover**를 반환해 사용자 확인을 요청했으며 임의 종료하지 않았다. 현재 released1/retained1·reclaimable0·진행Task0이다. 정리 완료를 거짓 주장하거나 종료/보존 worker Task를 재사용하지 않는다.
- 최종 앱 **2653pass/1skip**, engine **876pass/15markerwarnings**, web **545pass/build**, doctor **442파일/diff** 통과. engine/web는 최종과 동일SHA여서 기존검사를 재사용했다. 독립 최종14경계/영향227·engine116/web55·보존MP4/ZIP/fresh 인덱스/cold 재열기·legacy source2/unknown21/origin23legacy·ego 실제저장/stale 통과. 상세한 범위/중간실패/해결/미검증은 [M3 실행](absorption/M3_RUN_2026-10-22.md), [구현](absorption/M3_IMPLEMENTATION_2026-10-22.md), [독립검수](absorption/M3_REVIEW_2026-10-22.md)를 따른다.
- 최종 고정 `2026-10-22T06:08:28.533760+00:00`의509 SHA·tested-source-subset-start가 현재와 같다. M3-vs-M2 제품/계약/시험34파일은 구현 scratch `m3-vs-m2-files.json`/patch로 구분한다. PM 신규기준 `/var/folders/yk/7gcx2d_d3g36kr1klhhz4q700000gn/T/frame-room-m3-pm-yh7x4hg3`의 source-before727파일·m1-m2-before.patch·preservation-before4092를 보존한다. 구현 scratch `/var/folders/yk/7gcx2d_d3g36kr1klhhz4q700000gn/T/frame-room-m3-impl-eay7l87i`, 검수 scratch `/var/folders/yk/7gcx2d_d3g36kr1klhhz4q700000gn/T/frame-room-m3-review-rfgkzg1r`다.
- 최종ego7/p1은 검수자가 finish keep[]했다. 작은 합성project7ac55f3b-4f8d-41af-996a-98eccb3aeea7의 revision5→6·새clip67c0f783-7b6f-4c9a-8425-b288645970c6, 별도출력/library/폴더DB 셀·개별시간 일치다. API97757/worker97827/proxy77612는 종료·생존0·18765/5173 LISTEN0이며 cleanup-final.json에 소유명령을 기록했다. ego6 소멸 원인은 미확정이다.
- 최종 M3 recipe `video-processing-v6-sprite-gen-2.45.3-m3`, engineDigest `823cc81298696d190255dabb333f470046752d0f287d6eac979fc9186c446500`. bridge `frame-room-canonical-source-v1`, 구현SHA `2f15d47894a0771010f79d6b1ffbce70754fe9ab70cc90ef85e1d902b4493109`, engine-lock SHA `b8b7dcd6411d361aaae2d0a09609993eab708601b62c46024976cce355d8adfe`. 구현 `policy-identity-final.json`은 최종 실제 MP4 영수증과 고정509에서 읽은 값이다. 복원 repair4/comparison6·일반비교 schema1과 exact-raw-projection-else-protect를 구분한다. M2 v5와 구 recipe 미완성 재개 차단·구 완성 결과 저장만 retry는 유지한다.
- 사용자 원래1029파일·1117686350bytes와 공용sprite-gen3063파일의 SHA/크기 변경·누락0, 역사12파일불변이다. `.data/orca-session-archives/2026-10-22-completed-pm-cleanup-150025/`10개추가는 보존한다. README/cleanup-result 메타에는 사용자요청 M1/M2 PM 정리라고 적혔으나 생성주체·원요청/승인원문은 이Run에서 직접확인하지 못했다. M3 PM/구현의 생성행위가 아니다. 넓은Grok runtime4파일 변화는 원인미확정이며 되돌리거나 전역전체불변을 주장하지 않는다. 실제 auth/config·공용skill은 불변이다.
- HEAD/main/실제원격main **c48e46ec4c48eac1a1625aa47274dd6ee426897a**. M1+M2+M3 전부 미커밋이며 AGENTS/계획/인계·제품·계약·engine lock/patch·시험·보고서를 보존한다. Git게시/유료생성/배포 승인은 없다. M0 역사JSON/baseline은 재작성하지 않았다. 다음 PM은 실제 현재소스의 M4a 신규diff기준을 별도로 고정한다.
- M3 실제영상은 기존 보존Grok MP4의 사본이며 새생성이 아니다. accepted 복원/미술우월성·provider/observer/로그인/유료생성·다른장치성능·전체UI/screenshot은 미검증이다. 기존엔진docs10링크 누락5pass/1fail·누적10MB fixture CPU지연 한계를 보고한다. Postman CLI1.69 simulation 미지원은 전역업데이트/외부게시없이 localhost 검증으로 구분한다.
- 다음은 **M4a 재생 의미·동작 제작/미리보기**이며 M4b 방향세트/game-pack, M5/M6도 필수다. 플레이어/편집/job snapshot·validators/runtime/GIF·WebP/backup·restore/canonical 호환·v1계속읽기·차기runtime/형식 한계를 함께 다룬다. loopMode와재생모드혼동/이름추정 금지, M2 helper만으로M4앱완료 처리하지 않는다.
- 컨텍스트 사용률 수치는 제공되지 않는다. 추정/자동80%감시 주장 없이 정리 마감 후 다음기능전에 새 GPT6.1Sol xHigh PM에 인계한다. 새PM은 같은 M3→M4a 경계 재이관을 반복하지 않는다. 자신의handle을확정한뒤 정식대상 run:run_db69615cf19f로 일반인수status를보내며 이전PM handle을 sender로 빌리지 않는다.

## M3 새 PM 인계 영수증

- 새 PM `term_6a03edc7-a106-4325-8d75-23aaa0ea7c12`, 같은 worktree. `orca agent launch --agent codex --model gpt-6.1-sol --effort xhigh --worktree path:/Users/cheng80/Desktop/Current_works/frame_room`으로 실행했다.
- operation `1792643635984-fe31f63008924549a410b1d68e86cd90`, prompt outcome `handed-to-terminal`. 전체 인계 prompt/launch 영수증은 M2 PM scratch의 `m3-pm-prompt.txt`·`m3-pm-launch.json`이다. agent-launch는 requested/effective 객체를 제공하지 않는다. 실제 terminal-show에서 `GPT-6.1-Sol xhigh`와 M3 인수 작업 제목·실행을 대조해 확인했다. 기능 worker-start에서는 요청/실효 객체를 계속 확인한다.
- 새 PM이 자신의 handle에서 M2 Run으로 일반 인수 status를 보내고 새 M3 Run·식별자를 이 문서에 갱신한다. 인계 prompt 전달은 완료됐으며, 새 PM의 인수 확인 후 M2 PM은 M3 배정·문서 수정을 종료한다. 현재 M2 worker는 모두 종료됐으므로 중복 생성할 기능 세션은 없다.

## M2 완료·다음 M3 인수 기준

- M2 Run `run_70d73cc5d001`, 현재/송신 PM `term_33b48ee3-9f56-4528-a4bb-a346b368d768`. 구현 `task_292e4f98827a`/`ctx_7b611eb73981`, 독립검수 `task_ed7d8b3c75af`/`ctx_1e4408c47e69`는 모두 succeeded·released, transcript captured·closed. worker_done은 구현 `msg_86fb99dad5a3`, 검수 `msg_07eee427034a`. reclaimable0·진행worker0 확인. 종료한 worker/M1 Task를 재사용하지 않는다.
- [M2 실행/판정/정리](absorption/M2_RUN_2026-10-22.md), [구현](absorption/M2_IMPLEMENTATION_2026-10-22.md), [독립검수](absorption/M2_REVIEW_2026-10-22.md) 완료. 미해결 제품finding0. 최종 전체앱2598pass/1skip·엔진762pass/15markerwarnings·웹543/build·doctor433/diff통과. 독립103/47/2/31과 자체 실제MP4 저장/출력·ego DOM/smoke 확인. 수는 중복이므로 합산하지 않는다.
- 현재 HEAD/main/원격main `c48e46ec4c48eac1a1625aa47274dd6ee426897a`. **M1+M2 모두 미커밋**이며 commit/push/PR/merge/배포·유료생성 승인은 없다. AGENTS·인계·계획과 모든 미커밋 제품/계약/engine lock/patch/시험/보고서를 보존하고 M3 diff를 신규 기준과 분리한다. M0 JSON/baseline은 역사적 증거로 그대로다.
- M1→M2 이전 기준/사본/patch/자료해시는 `/var/folders/yk/7gcx2d_d3g36kr1klhhz4q700000gn/T/frame-room-m2-pm-1l9eqi0r`다. M2 scratch `/tmp/frame-room-m2-impl-DJu2hP`의 `candidate-freeze.json`, `m2-vs-m1-files.json`은 M1대비80파일의 전후SHA, 최종PM대조 변경0. 새 M3는 실제현재전체소스 기준을 별도로 고정한다.
- 새 처리 `video-processing-v5-sprite-gen-2.45.3-m2`; engineDigest `e56bec744cf71af498de3735f048f97dc2a963a95a5a6f8c6b18ad204efcfb81`, engine-lock SHA `b4d2906baebb9666794da1097c33f880de0a95996290a84759101ada88fe0860`. 기반pin/qualityVersion=2.34.0 유지, videoQualityVersion=2.45.3-m2는 선별반영이다. legacy retry 차단과 구완성결과 저장만retry는 제품에 강제된다.
- 사용자 `.data`/`output`1029파일·1117686350bytes 사전사후SHA/크기 변경·누락·추가0, AGENTS/M0/M1역사9파일동일. 독립 넓은11300파일중11296파일과 실제auth/config/settings·공용sprite-gen·symlink동일. `.grok` logs/unified.jsonl·models_cache.json·sessions/session_search.sqlite·settings_cache.json4개는원인미확정변경. PM/구현은Grok/실provider호출없음을대조했다. 전역runtime전부불변으로일반화하거나4파일을되돌리지 않는다.
- 같은보존MP4 SHA `9a1945d761bbbbc9e4d6a05f6a1258d4306a7e43c82e21a2163ec52fd247af31`의 M1/M2 최종 구간33–59·8셀·125/125/125/167/125/125/125/166ms·PNG/GIF/WebP·library/폴더DB 일치. GIF형식양자화1080ms, 원본/WebP1083ms. 실제RIFE544px TTAoff/on cold/warm은실행했지만 overlap은20/60초예산중단으로성공/품질개선미검증. CPU/다른장치·전체UI여정·TTA미술우월성미검증. ego5smoke/옵션offDOM확인,추가펼치기click은pointertimeout. 해당TaskSpace finish·자체API/worker/proxy/PID종료/포트0 확인.
- 다음은 전체계획 **M3 비교·원본 복원·후속 보정**이다. source/origin/baseline identity·정책/schema·최종셀/시간/sample mapping·unknown/stale preview·저장보존을 기존 follow/compare 경로에 통합한다. M0 full extraction 증거는2동작만, 나머지21은unknown/unsupported-legacy다. M2가 source helper를 의존성으로가져온것을M3앱기능완료로해석하지않는다. 실제대장M3·계획·M0/M2한계를먼저읽고범위를확정한다.
- PM/구현/검수 모두 `--agent codex --model gpt-6.1-sol --effort xhigh`·requested/effective확인, Opus5.5금지, PM제품수정금지. Orca최신스킬, ego소유공간/README, import전SPRITE_DATA_DIR격리·사전사후해시·공용스킬/실제자료/인증/전역설정불변, Postman지침/CLI1.69simulation미지원 한계 유지.
- 컨텍스트usage수치는제공되지않는다. 추정/80%자동감시주장없이 M2완료기능경계에서보수적으로새PM이관. 새PM은같은M2→M3경계의재이관을반복하지않고 M3를완수한다. M2/M1보존PM은사용자소유이므로다른세션을임의종료하지않는다.

## M2 PM 인계 영수증

- 새 PM: `term_33b48ee3-9f56-4528-a4bb-a346b368d768`, 같은 worktree `44decedb-a41b-4a32-a841-32dc531e945c::/Users/cheng80/Desktop/Current_works/frame_room`.
- `orca agent launch --agent codex --model gpt-6.1-sol --effort xhigh --worktree current`의 operation `1792640263935-99e09901244d439b9a96384b7fc37843`, prompt outcome `handed-to-terminal`이다. `terminal show/read`에 `GPT-6.1-Sol xhigh`와 M2 인수 제목·AGENTS/Git 확인 실행이 표시돼 실제 착수를 확인했다. 이 API는 worker-start와 달리 requested/effective 객체를 반환하지 않아 실제 터미널 표시와 실행을 별도 대조했다.
- 인계 범위는 M2다. M1 미커밋 변경/검증/정리와 전체 계획·M0 선행 보호 조건을 전달했다. 새 PM이 자신의 Run·구현/검수 세션을 만들며 이 문서에 식별자를 갱신한다. M1 PM은 이 기록 후 M2 배정·문서 수정을 종료한다.

## M2 실행 소유권 이력

- PM `term_33b48ee3-9f56-4528-a4bb-a346b368d768`의 현재 작업 transcript와 `GPT-6.1-Sol xhigh` 표시를 대조했다. 기본 terminal 조회는 이전 PM을 가리켜 이후 모든 coordinator 명령은 자신의 handle을 명시한다.
- 새 Run `run_70d73cc5d001`, coordinator는 위 PM이다. 구현 `task_292e4f98827a` / `ctx_7b611eb73981` / `term_31509b46-a2cb-405e-b6bb-fb9cef9e779e`, 독립검수 `task_ed7d8b3c75af` / `ctx_1e4408c47e69` / `term_23dcf712-ea01-482e-915e-d7df47885cfe`. 두 requested/effective `codex / gpt-6.1-sol / xhigh`와 turn started를 확인했다. M1 Run으로 일반 인수 status `msg_215aea0d770d`를 전송했다. 이전 PM handle을 sender로 사용하지 않았다.
- [M2 실행 범위·인수 조건](absorption/M2_RUN_2026-10-22.md). M1 미커밋 전체 기준 사본·patch·해시는 `/var/folders/yk/7gcx2d_d3g36kr1klhhz4q700000gn/T/frame-room-m2-pm-1l9eqi0r`에 보존했다. 사용자 `.data`·`output` 사전 1,029파일·1,117,686,350 bytes를 제품 import 없이 해시했다.
- Git HEAD/main/실제 원격 main 모두 `c48e46ec4c48eac1a1625aa47274dd6ee426897a`, worktree 1개. M1 workers released 2·진행0 확인.
- 컨텍스트 사용률은 제공되지 않는다. M1→M2 같은 경계에서 재이관하지 않고 M2를 완수했다. 다음 기능 M3 착수 전에 새 PM에게 이관한다.

## 이전 PM의 인수·M1 실행

- 새 PM handle: `term_0ff68e4e-3300-496a-bf82-d8282efe18ad`. 현재 요청과 실행 내역을 `terminal read`로 대조했고 `terminal show`에 `GPT-6.1-Sol xhigh`가 표시된다. 이전 sender를 빌리지 않았다.
- 새 Run: `run_5dbba83351d2`, coordinator가 위 handle임을 생성 영수증으로 확인했다. [M1 실행·인수 조건](absorption/M1_RUN_2026-10-22.md)에 범위·검증·식별자를 기록한다.
- 구현 `task_55937e2c26b7` / `ctx_d9e7057fe9a2` / `term_befdcf36-5ca6-4bc3-adc4-57e8b4ae7ef3`, 독립 검수 `task_fcce5da0fbd5` / `ctx_c03d68ff4bf9` / `term_1ada7788-d3ca-4a83-a7c1-161a8491cb85`. 두 세션의 requested/effective `codex / gpt-6.1-sol / xhigh` 일치와 turn start를 확인했고 같은 세션에서 검수 수정까지 처리했다. 구현·검수 모두 `worker_done` succeeded, 미해결 0이며 transcript captured·released를 확인했다. 최종 상태는 아래 정리 기록을 따른다.
- 실제 Git 확인: `main` / `c48e46ec4c48eac1a1625aa47274dd6ee426897a`, HEAD…`origin/main` 0/0, worktree 1개. 인계된 미커밋 문서 3개의 변경을 보존한다.
- 현재 도구에는 컨텍스트 사용률이 없다. 인계 직후 재이관을 반복하지 않고 M1 구현·독립 검토를 완수했다. M1 완료·정리 후 다음 기능 M2 착수 전에 보수적으로 새 PM에게 이관한다. rate limit 표시를 컨텍스트 수치로 해석하지 않는다.

## 목표와 승인 범위

- sprite-gen v2.45.3의 전체 기능을 프레임룸에 흡수한다. 품질·복구 안정성을 우선하며 M0–M6 모두 필수다.
- **PM·구현·독립 검토 모두 GPT 6.1 Sol · xHigh**다. 각 역할은 별도 세션으로 실행하며 Orca CLI 인자는 `--agent codex --model gpt-6.1-sol --effort xhigh`다. **Opus 5.5는 사용자 재허용 전까지 금지**다. PM은 제품 코드를 직접 수정하지 않는다. 오케스트레이션은 Orca CLI만 사용한다.
- 큰 기능마다 Run 1개, 구현 세션 1개·독립 검수 세션 1개를 사용하고 검수 수정까지 끝나면 기록을 남기고 정리한다. 다음 큰 기능은 새 세션으로 시작한다.
- PM 컨텍스트 사용률 80% 이상이면 배정을 멈추고 이 문서를 갱신해 새 PM에게 이관한다. 사용률이 제공되지 않는 환경은 큰 기능 경계에서 보수적으로 이관한다. 현재 확인한 Orca `status`·`terminal show` 응답에는 PM 컨텍스트 사용률이 없다. 상시 자동 감시나 자동 이관 프로그램을 설치한 상태는 아니다.
- M0 커밋·푸시와 작업 워크트리 확인은 완료했다. 최신 요청은 모델 역할 변경과 새 PM 세션 인계 후 진행이다. M1부터 전체 흡수 계획을 이어가되 새 문서·구현의 commit/push/PR/merge/배포는 별도 승인 없이 수행하지 않는다. 유료 생성도 승인 범위에 없다.

## 현재 기준과 다음 작업

- M0 기준 커밋: `c48e46ec4c48eac1a1625aa47274dd6ee426897a`, `main` → `origin/main` 푸시 완료. 작업 전 `git status --short --branch`, 원격 비교, 워크트리 목록을 다시 확인한다.
- [전체 흡수 계획](SPRITE_GEN_ABSORPTION_PLAN_2026-10-21.md), [M0 독립 검수 보고](absorption/M0_REPORT_2026-10-21.md)를 따른다. 84개 기능은 모두 앱 통합 구현 예정이며 M0 도구 구축을 기능 통합 완료로 해석하지 않는다.
- M1 보존·복구는 완료다. 최종 integration **2,577 passed, 1 skipped**(179.37초, Git에 없는 연구 원본), 영향+엔진 235건, 웹 541건·build, doctor 407파일·diff 통과. 독립 검수 안전 transport 54건·TLS 4건·ego smoke/DOM 통과, 발견한 5개 문제 수정·미해결 0이다. 구현 사용자 1,029파일·검수 970파일 전후 해시 일치·변경/누락/추가 0이다. 상세 명령과 scratch manifest 경로는 [구현 기록](absorption/M1_IMPLEMENTATION_2026-10-22.md), [독립 검수](absorption/M1_REVIEW_2026-10-22.md)를 읽는다.
- 다음은 M3 비교·원본 복원·후속 보정이다. 위 M2 완료·다음 M3 인수 기준을 현재 상태로 따른다. 아래 M1/M0 절은 역사적 실행 기록이다. M1+M2 미커밋 변경과 M0 JSON/baseline을 보존한다.
- M0 독립 검수: 전체 integration 2,521 passed·1 skipped, replay 2/2 일치. 푸시 전 추가 확인: M0+engine guard 47 passed, 엔진 407파일 무결성·대장·port-plan 검사 통과. 코드 변경 없이 전체 integration은 반복하지 않았다.
- 남은 한계: M0 최초 삭제/출력 실패 원인은 여전히 미확정이나 강제 순서 경합은 M1에서 수정·검증했다. M0 최초 DB 접근 이전 해시 부재도 소급 해소하지 않았다. M1 ego는 offline provider fixture·별도 포트의 smoke/DOM이며 screenshot은 CDP timeout으로 실패, 전체 UI 여정은 미검증이다. 실제 RIFE 성능·provider 인증/유료 생성은 하지 않았다. Postman CLI 1.69.0은 simulation 미지원이라 실제 localhost HTTP/TLS 시험으로 검증했고 외부 게시/전역 갱신은 하지 않았다.

## Orca 정리 기록

### M1 최종 상태·다음 PM 착수 조건

- Run `run_5dbba83351d2`의 구현/검수 Task 모두 `worker_done succeeded`다. 완료 메시지는 구현 `msg_6fb14468af65`, 검수 `msg_c66893f59146`다.
- `ctx_d9e7057fe9a2`·`ctx_c03d68ff4bf9` 모두 worker-release `released`·`closed_agent_terminal`·`transcript/captured`를 확인했다. 해당 Run reclaimable 0, released 2, 실행 중 worker 0이다. 정리 직후 프로젝트 터미널은 M1 PM 1개였다.
- 최신 Git은 main/c48e46e이고 원격 refs/heads/main도 `git ls-remote`로 같은 전체 해시임을 확인했다. 커밋·push는 하지 않았다. 인계된 문서 3개와 M1 제품·계약·엔진·시험 변경 및 보고서 4개/신규 transport 시험을 모두 보존한다. 실제 파일 목록은 `git status --short --branch`로 재확인한다.
- M2 PM은 새 handle에서 자신의 Run을 생성하고 새 구현·독립 검수 각 1세션을 지정 모델로 운영한다. 이전 Run/handle은 실행 이력이며 sender 권한으로 사용하지 않는다. M1 수정은 완료했으므로 동일 M1 경계 이관을 반복하지 말고 M2를 진행한다.
- M0 기능 대장은 역사적 조사로 그대로다. M1 대응·범위별 완료는 M1_RUN 최종 판정과 전체 계획 10장을 본다. 84개 전체 완료로 표시하거나 영상 참조/종료 입력(M6)을 완료로 닫지 않는다.

### M0 과거 정리

- M0 Run `run_fa25d7306241`의 Task 4개는 모두 성공으로 완료했다. 기록은 실행 근거이며 새 PM이 이전 sender 권한을 갖는 근거가 아니다.
- 최초 구현 `task_b0a40e2559d4` / `ctx_00c3288518b8`, 검수 준비 `task_d09881521e8c` / `ctx_ee2563c8cdfb`, 수정 구현 `task_0e13b1c40dd8` / `ctx_263d46d7a274`, 최종 검수 `task_9a0c7b9cd503` / `ctx_91865aae6b4f`.
- 수정 구현 세션과 작업 전용 PM shell은 앞서 종료했다. 사용자 인계로 남았던 최초 구현 `term_3380931d-4cd2-452d-b449-0c3da26e2d97`, 최종 검수 `term_07ae7d8b-cfbe-467a-b449-97d3a4d2a5b7`는 이번 사용자 정리 요청에 따라 입력 대기 상태 확인 후 종료했다. 두 종료 응답 모두 `ptyKilled: true`다.
- 종료 전 두 세션의 제한된 출력과 worker 읽기 결과를 로컬 `.data` 아래 `orca-session-archives/2026-10-21-m0-cleanup/`에 저장했다. 검수 세션의 미전송 입력도 `review-terminal.json`에 보존했다. 이는 전체 대화 아카이브가 아니며 Git 대상이 아니다. durable Task/Dispatch 이력은 지우지 않는다.
- 정리 후 프로젝트의 Orca 터미널 0개, `reclaimable` worker 0개를 확인했다. 과거 `retained` 3개·`released` 1개 카운트는 Task/Dispatch 보존 이력이며 남아 있는 터미널 수가 아니다. 현재 실행 중인 기능 worker는 없다.
- 이관 준비 시 미커밋 변경은 이전 PM이 작성한 `AGENTS.md`와 이 문서였고, 최신 모델 정책을 전체 계획의 역할 절에도 반영한다. 새 사용자 변경 여부는 이관 시 다시 확인한다. 새로 인계받은 PM은 같은 경계에서 이관을 반복하지 않는다.
- 새 PM은 기존 종료 세션을 재사용하지 않고 자신의 세션에서 Run을 생성한다. 이 문서에 기록된 handle을 sender로 사용하지 않는다.

## 이관 직전 갱신할 항목

1. 실제 브랜치·HEAD·원격 차이와 미커밋 파일, 사용자 변경의 소유자를 기록한다.
2. 해당 기능의 완료 조건, 완료/진행/남은 작업, 실패·skip을 포함한 실제 검증과 위험을 갱신한다.
3. 진행 중 Run/Task/Dispatch/worker 식별자·모델·현재 소유자와 다음 행동을 기록한다. 없는 작업을 실행 중이라고 쓰지 않는다.
4. 새 PM에게 이 문서와 필요한 문서 경로를 Orca CLI로 전달하고 전달 결과를 확인한다. 진행 중 작업의 인계와 기존 PM의 배정 종료를 확인한 뒤 이전 PM 세션을 정리한다.
