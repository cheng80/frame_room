# sprite-gen 전체 기능의 프레임룸 흡수 계획

2026-10-22 KST · **전체 범위 확정, M0–M3 제품 구현·독립 검수 완료 · M3 세션 결산 후 M4a**

사용자 결정은 **전체 기능 흡수**다. 앞서 선택한 품질·복구 우선은 구현 순서에 적용하며 기능을 제외하는 기준으로 사용하지 않는다. `v2.45.3`의 공개 사용자 기능을 모두 프레임룸의 실행·편집·저장·출력 경로에 연결한다. 엔진에 이미 있어도 앱에서 쓸 수 없는 기능은 연결할 대상으로 포함한다. M0–M6 전체가 필수 범위이며 단계별 출시는 중간 성과다. 2026-10-21 사용자 요청으로 M0부터 구현 착수를 승인받았다. 유료 생성·Git 게시는 이번 착수 범위와 구분한다.

## 1. 기준과 조사 범위

| 대상 | 확인 기준 |
| --- | --- |
| 현재 프레임룸 | HEAD `6551294c1dd6e4f49246771cfe438daa885e8d96`, 문서 작성 전 working tree clean |
| 프로젝트 전용 엔진 | `engine/engine-lock.json`: 기반 `v2.12.1`, `qualityVersion: 2.34.0` 선별 반영 |
| 흡수 대상 | 정식 `v2.45.3`, commit `59b2738a2e76ed7043d9691a230396ed6374a336` |
| 공개 시각 | 2026-10-21 16:08 KST, GitHub release published_at 기준 |
| 차이 규모 | upstream `v2.34.0...v2.45.3` 401커밋. 프로젝트 자체 변경과 동일한 차이 수는 아님 |
| `main` | 조회 시점에 `v2.45.3`과 같은 commit. 어제의 ‘v2.44 이후 미출시’ 구분은 이번 기준에 적용하지 않음 |

출처: [정식 릴리스](https://github.com/aldegad/sprite-gen/releases/tag/v2.45.3), [버전 간 비교](https://github.com/aldegad/sprite-gen/compare/v2.34.0...v2.45.3), [고정 commit의 변경 기록](https://github.com/aldegad/sprite-gen/blob/59b2738a2e76ed7043d9691a230396ed6374a336/CHANGELOG.md).

이번 확인은 공개 변경 기록·기능 문서와 현재 코드·계약의 정적 대조다. 함수별 전체 diff, 실제 처리 성능, 새 모델의 생성 품질과 호환성은 구현 단계의 검증 항목이다. 기능표의 ‘보완’은 로컬의 모든 같은 기능이 구버전이라는 판정이 아니라 실제 호출 지점을 조사할 작업 분류다.

### 전체 범위와 누락 방지

전체 기능의 기준은 고정 commit의 [공개 기능 문서 목록](https://github.com/aldegad/sprite-gen/blob/59b2738a2e76ed7043d9691a230396ed6374a336/docs/README.md), CLI 명령 등록과 `sprite_gen/_modules.py`의 분류다. 변경 기록에 강조된 신규 기능뿐 아니라 기존 엔진에만 있고 프레임룸에 연결되지 않은 공개 기능도 대조한다. 실험 기능과 원본에서 선택 기능으로 소개한 도구도 제품 범위에 포함한다. 유지보수 전용 배포 명령을 사용자 제작 버튼으로 만들 필요는 없지만 이식에 필요한 빌드·무결성·회귀 지원은 유지한다.

| 기능 영역 | 필수 흡수 범위 | 주 담당 단계 |
| --- | --- | --- |
| 이미지·시트 제작 | prepare, gen/gen-set, 기준·방향 anchor, 캐릭터/효과, provider 선택·설정·명세 | M0/M5/M6 |
| 영상 제작 | 시작/끝 그림·참조 입력, 영상 생성·확장·편집·재개, prompt helper·외부 제작물 가져오기 | M1/M4/M6 |
| 루프·보정·검사 | 추출·키 제거·구간·두 걸음·보간·정렬·캐시·follow·복원·정지·방향 세트・움직임/접지/좌우 검사 | M2/M3/M4/M6 |
| 새로운 제작 방식 | pixel-draw, logo, UI kit, 양축 타일, 생성형 중간 프레임 | M5/M6 |
| 음원 | sound SFX/BGM 생성, 가져오기·정규화·loop·cache·사용량·재생 이벤트 | M5 |
| 편집·합성 | curation, 완성 atlas 가져오기, 팔레트 변형, layer/rig 합성, 호흡·그림자 | M5/M6 |
| 출력·장면 | PNG/atlas/GIF/WebP/Aseprite·Phaser/Flame 메타데이터·game-pack v2·sound-only·장면 구성/검사/렌더·ambient loop | M4/M5/M6 |

M0에서 명령·문서별로 고유 항목을 만들고 **현재 구현 근거 → 앱 진입점 → worker/API → 저장 형식 → 출력/복구 → 시험 → 담당 단계**를 연결한 기능 대장을 작성한다. 표는 영역 분류이며 전체 대장 작성을 이미 완료했다는 뜻은 아니다. `미조사/구현 예정/구현 중/검증 대기/완료/차단` 상태를 사용하고 ‘중요하지 않음’이나 ‘나중에 검토’로 항목을 닫지 않는다. 지원 환경·인증·의존성 제약이 있으면 차단 조건과 해결 작업을 기록하고 남은 기능으로 집계한다.

## 2. 제품 목표와 보존 조건

- 이미 받은 영상을 다시 생성하지 않고 끝까지 복구·저장한다. 접수 ID가 있으면 같은 요청을 조회하고, 접수 여부를 모르면 새 제출을 막는다.
- 걷기 한 주기·잔상·이음새·보간 손상을 검사하고, 실패 이유와 바뀐 프레임을 최종 출력에서 확인할 수 있게 한다.
- 기존 자료·편집·시간·앵커·저장 이력을 보존하면서 새 결과를 별도 동작으로 추가한다.
- 기본 걷기 8장, 선택 12장과 명시한 4~64장, 원본 주기 시간, 기본 `repairMode=off`, 기존 GIF 마무리·nearest 편집·cyan 키 제거를 유지한다. 원본 주기 판정이 바뀌는 새 결과는 원래 구간과 새 구간·시간을 함께 기록한다.
- 수동 승인 관문을 다시 만들지 않는다. `pending`은 실행을 막지 않고 기존 `rejected`와 파일·좌표·시간·revision의 기술 검사는 유지한다. ‘새 동작으로 저장’은 편집 실행이며 별도 승인 절차가 아니다.
- 동작 생성·보정은 **별도 출력 + 프로젝트 라이브러리의 동작·프레임·개별 시간 + 프로젝트 폴더 반영**까지 성공해야 완료다. 저장 실패 뒤에는 완성된 파일의 저장만 재시도한다.
- 공용 sprite-gen 스킬, 사용자 프로젝트와 전역 인증·기본 설정을 변경하지 않는다. 프로젝트 전용 엔진을 대상으로 한다.

현재 계약: [6단계 제작](SIX_STEP_WORKFLOW.md), [독립 작업 저장](STANDALONE_LIBRARY_SAVE_2026-10-12.md), [영상](../../packages/contracts/VIDEO.md), [실행·출력](../../packages/contracts/IMPLEMENTATION.md), [프로젝트 폴더](../../packages/contracts/PROJECT_FOLDERS.md).

## 3. 신규 기능의 배치

‘단계’는 구현 순서를 뜻한다. 각 단계의 세부 UI·스키마는 착수 전에 확정하며 M5·M6도 전체 완료에 필수다. 기능별로 기존 화면의 도구·입력·출력 설정을 재사용하되 필요한 제품 기능을 생략하지 않는다.

| 신규 기능군 | 현재 기반 / 필요한 차이 | 프레임룸 연결 | 단계 |
| --- | --- | --- | --- |
| 같은 요청의 poll·다운로드 재시도, `video-resume`, 전체 제한 시간 | checkpoint·GET 재개·POST 1회 보호는 이미 있음. 일시 응답 오류·잘린 JSON·잘못된 MP4·시간 예산의 처리 보완 | 작업 센터의 기존 요청 이어받기, 저장 단계별 복구 안내 | M1 |
| provider 실패·사용 경로·제한 정보 | 로그인 격리·단일 제출 보호 유지. 엔진의 자동 POST 재시도와 provider 전환 정책은 그대로 도입하지 않음 | 현재 ProviderConnections·작업 영수증에 필요한 실패 이유만 전달 | M1 |
| 두 걸음 주기, 반걸음·누락된 발 교차·장비 독립 주기·lead-in 처리 | `_select()`·`_gait_fallback()`이 공개 CLI 전체를 실행하지 않음 | 기존 영상 재처리와 원본/새 구간 비교, 8장 샘플링 전에 주기 확정 | M2 |
| 잔상 화면 검사·원본 대체·`filmed-ghost` 재촬영 권고 | 현재 retake·held·period 진단 위에 추가 | 문제 슬롯과 처리 내역 표시, 재촬영은 사용자 별도 실행 | M2 |
| flow 기반 보정, 급가속 구간 완화·몸통 보행 유지, overlap-wrap | 현재 `_repair_selection()`은 `repair_jumps()` 직접 호출 | 보정 선택 시 실제 adapter 경로에 연결. 몸통의 원래 보행을 손상하는 완화는 채택하지 않음 | M2 |
| 상대 윤곽 손상 검사·RIFE TTA·보간 캐시 | 현재 직접 보간/정렬 경로·도구 탐색 존재 | 새 정책의 품질 판정·도구 identity·중단 가능한 시간 예산 연결 | M2 |
| 원본 manifest·루프 비교·원본 기반 복원 | 계보·후보 비교 기반은 있으나 공개 source/origin/baseline 계약과 다름 | ‘결과 확인’의 비교·복원 도구, 새 동작으로 저장 | M3 |
| follow 검사·`--read-on`·`--stretch-floor` | 부분 흔들림 preview/apply와 좌우 검사는 이미 앱에 있음 | 기존 ClipTools 보완, 영역/좌표 근거를 증명할 수 없으면 이동을 추정하지 않음 | M3 |
| 방향별 시트·동일 지면선·시트 단위 배율 | 방향별 영상 묶음·개별 애니메이션 출력 존재 | 다방향 동작을 한 세트로 선택하고 지면·크기 차이 확인, 통합 시트 출력 | M4 |
| `loop / once-return / once-hold / lifetime`, 사용자 동작 문장·종료 자세 | state 8종 allowlist, 재생·bake는 `hold-last`만 지원 | ‘동작 만들기’의 재생 방식과 문장, 편집·미리보기·출력 동시 지원 | M4 |
| `video-stop` | 별도 정지 동작 제작 기능 없음 | 원본 걷기/달리기에서 정지 전환 파생. 역재생인 출처와 접합 거절 이유 표시 | M4 |
| `game-pack` 다중 atlas·크기·재생 메타데이터·이벤트 | canonical bake·runtime·Aseprite·PNG/GIF/WebP 출력 존재 | 기존 ‘내보내기’의 선택 출력으로 추가, 별도 렌더 체계를 만들지 않음 | M4 |
| `slice-sheet` contain·공통 배율·추출 manifest, 행별 anchor/배율 수정 | 가져오기·추출·공통 정렬 존재 | ‘자료 준비/프레임 편집’에서 원본 좌표·체형 비율을 보존해 확장 | M5 |
| `pixel-draw` 8~48px 격자·최대 64프레임·스타일·동작·시간·resume | 현재 이미지/영상 생성과 다른 실험 기능 | ‘자료 준비/동작 만들기’의 선택 제작 방식, 격자 원본도 보존 | M5 |
| `ui-kit` nine-slice·padding·fill·누락/모호한 배치 거절 | 일반 이미지 asset은 있으나 UI kit 전용 모델 없음 | 우선 자료형·가져오기·미리보기·출력 연결. 캐릭터 동작으로 위장 저장하지 않음 | M5 |
| `background-tile --axis xy`, alpha haze·checkerboard 거절 | 가져오기·알파 검사 기반 있음 | 타일/이미지 처리 옵션으로 추가. 반투명 의상·그림자·glow를 일괄 삭제하지 않음 | M5 |
| `logo` mood→lettering→matte·문자 검사, 공통 vision 질문 | 일반 이미지 생성·자료 라이브러리 재사용 가능 | 선택 자료 제작 도구. 원본·파생·문자 검사 결과를 구분하고 호출 상한 표시 | M5 |
| game-pack v2의 images/tiles/ui, audio·sound-only pack | 현재 `assets`는 이미지, `videos`는 영상. 음원·UI 메타데이터가 없음 | 먼저 이미지/타일/UI 연결, audio는 별도 자료형·백업·출력 검증을 갖춘 후 연결 | M5 |
| `sound` SFX/BGM 생성·정규화·loop·캐시·사용량 | 기존 음원 생성·자료형 경로 없음 | 음원 제작·가져오기·듣기·프로젝트 저장·프레임 이벤트·pack 출력까지 연결 | M5 |
| 영상 extend/edit·참조/종료 입력·외부 영상 경로 | 현재 단일 기준 이미지 생성과 MP4 가져오기 중심 | 영상 도구로 제공하고 요청별 원본·파생·접수 ID·복구를 분리 | M6 |
| 팔레트 교환·layer/rig 합성·호흡·그림자·atlas unpack·움직임/접지 QA | 엔진 기능과 앱 연결 상태를 항목별 확인해야 함 | 기존 편집·결과 확인의 도구로 통합, 파생 결과·검사 근거 보존 | M6 |
| 생성형 중간 프레임·ambient 영상 루프·scene 구성/렌더/검사 | RIFE 주기 맞춤과 다른 작업, 장면 자료형 연결 필요 | 개별 제작/합성 작업으로 제공하고 프레임·영상·장면 출처를 구분 | M6 |
| defaults v2·과금 경로·토큰/제한 정보·요청 옵션 충돌 규칙 | 앱에 프로젝트 설정·snapshot·인증 정책이 있음 | 필요한 정보만 앱 계약으로 변환. 전역 preferences 복사·CLI 자동 fallback 금지 | M1/M5 |
| 패키징·Windows 시험·중복 테스트 축소 등 내부 변경 | 프로젝트 설치·doctor·회귀 체계 존재 | 해당 이식 파일의 필수 의존성/시험만 반영. 프레임룸 Windows 전체 지원으로 표시하지 않음 | 각 단계 |

원본 기능 문서: [영상](https://github.com/aldegad/sprite-gen/blob/v2.45.3/docs/video-pipeline.md), [보정](https://github.com/aldegad/sprite-gen/blob/v2.45.3/docs/loop-repair.md), [비교·복원](https://github.com/aldegad/sprite-gen/blob/v2.45.3/docs/loop-comparison.md), [게임 출력](https://github.com/aldegad/sprite-gen/blob/v2.45.3/docs/game-pack.md), [pixel-draw](https://github.com/aldegad/sprite-gen/blob/v2.45.3/docs/pixel-draw.md), [UI kit](https://github.com/aldegad/sprite-gen/blob/v2.45.3/docs/ui-kit.md), [logo](https://github.com/aldegad/sprite-gen/blob/v2.45.3/docs/logo.md).

## 4. 구현 묶음과 완료 조건

### M0. 반영 목록·기준 결과 확정

**목표:** 이후 품질 차이와 회귀를 설명할 수 있는 최소 비교 기반을 만든다.

- `v2.45.3`의 공개 기능 전체·신규/변경 함수와 전이 의존성, 프로젝트의 로컬 패치·모든 호출자·시험·설정·exports를 대조한다. 위 표를 실제 파일 단위의 ‘재사용/교체/앱 연결/차단 해소’ 목록으로 구체화한다. 기존과 동등한 기능도 실제 앱 시험 근거가 있어야 완료로 기록한다.
- `engine-lock.json`의 기반 pin은 유지한다. 반영 묶음별 upstream commit·실제 파일 해시·로컬 적응과 검증 범위를 기록한다. 일부만 반영한 상태를 엔진 전체 `v2.45.3` 완료로 표시하지 않는다.
- 현재 존재하는 보존 MP4·셀·프로젝트 사본을 먼저 확인하고 해시를 고정한다. 과거 문서에 적힌 삭제된 연구 자료를 fixture로 가정하지 않는다. 부족한 유형은 합성 fixture로 보충하고 출처를 구분한다.
- recipe에 처리 정책·source mapping·보간기·색/알파 마무리 버전을 구분한다. 기존 결과는 그대로 조회하고, 새 처리는 새 결과로 만든다. 구 recipe 실행을 지원하지 못하면 재현 불가를 명시하며 조용히 최신 처리로 재개하지 않는다.

**완료:** 보존 대상·현행 결과·실제 파일별 이식 목록·재현/비교 가능한 입력이 있고, 원본이 없거나 구 recipe를 재실행할 수 없는 범위가 표시돼 있다.

### M1. 제출·조회·다운로드·저장 복구

**목표:** 생성 결과가 이미 존재할 때 새 생성 없이 회수·보존·등록을 끝낸다.

기존 `generate_video`, `/jobs/{jid}/retry`, checkpoint와 작업 상태를 확장한다. 별도 생성 API나 독립 큐를 만들지 않는다.

| 상황 | 처리 원칙 | 관측 가능한 완료 조건 |
| --- | --- | --- |
| 최초 제출 | 현재 한 작업당 외부 POST 최대 1회 보호 유지 | 거절·타임아웃에도 자동 두 번째 POST 없음 |
| ID 확보 후 429/5xx·연결 실패·잘린/비JSON 응답 | 같은 ID 조회에 제한된 backoff, 전체 잔여 시간 적용 | ID 유지, 조회 횟수·중단 이유 기록, 재개 가능 |
| ID 확보 후 401/403 | 로그인 확인 안내 후 중단, 인증 자동 전환 없음 | 자격 복구 뒤 같은 요청 조회 가능 |
| 제출 응답을 받지 못해 ID 없음 | 접수 불명 유지 | 재시도로 새 제출하지 않음 |
| 완료 후 다운로드 오류·URL 누락·MP4 검사 실패 | 기존 ID에서 회수 재개, 불완전 파일을 완료로 등록하지 않음 | 원본 검증·해시·원자적 파일 게시 완료 뒤 보존 |
| 원본 파일 확정 후 worker 중단 | 로컬 파일과 영수증 검증부터 재개 | 다운로드/생성 중복 없이 후처리 진입 |
| 결과 파일 완성 후 라이브러리 저장 실패 | 완성 결과 재사용, 저장만 재시도 | 동작·프레임·시간과 폴더 DB 재조회 일치, 중복 없음 |

현재 `guarded()`는 GET의 429/401/403도 엔진 재시도 전에 오류로 바꾼다. 최신 엔진만 갱신하지 말고 **어댑터의 오류 분류·중단/재개 경계**까지 조정한다. 엔진의 ‘접수되지 않은 POST 재시도’는 프로젝트의 더 엄격한 POST 1회 계약 때문에 가져오지 않는다.

보안·시간·과금 경계는 변경하지 않는다. 로그인/API key/provider 자동 전환은 금지하고, 영수증에는 요청 ID·실행 경로·조회/다운로드 시도·중단 이유만 공개한다. 토큰·서명 URL·인증 파일은 저장 결과에 노출하지 않는다. 사용자 취소·프로세스 종료 후에도 checkpoint가 남고, 프로젝트 폴더를 여는 것만으로 원격 작업을 재개하지 않는다.

**M0에서 발견한 보존 위험:** 프로젝트 삭제와 출력 등록을 동시에 실행하면 파일 존재 확인과 실제 읽기 사이에 프로젝트 폴더가 이동할 수 있다. 격리된 강제 실행 순서 시험으로 이 경합 경로를 재현했으나, 최초 통합 시험 실패가 같은 경로였는지는 미확정이다. M0에서는 제품 코드를 수정하지 않았다. M1에서 삭제·출력·작업 등록의 잠금/수명 계약을 함께 확인해 보존 실패를 막고, 동시성 회귀를 추가한다. 이 항목을 검사 재실행 통과만으로 해결된 것으로 기록하지 않는다.

**완료:** 실제 앱 transport 경로에서 실패 시나리오별 POST 수·동일 ID 재개·저장 전용 재시도를 검증한다. 단순 모듈 mock으로 끝내지 않고 잘린 HTTP body·read timeout·잘못된 MP4를 로컬 서버로 재현한다. 실제 provider의 일시 장애를 실측했다고 표현하지 않는다.

### M2. 루프 품질·보간 안전·캐시

**목표:** 한 주기를 올바르게 고르고, 선택 보정의 최종 픽셀·시간·출처와 비용을 통제한다.

- `_select()` → `_gait_fallback()` → `_repair_selection()` → `_align_selected_cycle()` → 정규화·GIF 마무리 → worker 저장의 실제 경로에 연결한다. 기존 함수와 최신 public helper를 재사용하고 두 번째 처리 파이프라인을 만들지 않는다.
- 두 걸음 판정은 원본의 관측 가능한 발 교차와 신체 구조에 맞춰 적용한다. 숨은 발·네 발형·다리 없는 형태를 이족 확정으로 표시하지 않는다. 관측이 불확실하면 근거와 기존 픽셀 기반 선택을 남긴다.
- lead-in·장비 독립 주기·안전 여백·실제 clipping을 구분한다. 명시한 수동 범위를 자동으로 넓히거나, 8장 축소에 보간을 추가하지 않는다.
- ghost 화면 검사, flow 보정·급가속 완화·몸통 보행 보호, 상대 윤곽 검사를 함께 연결한다. `filmed-ghost`는 재촬영 권고일 뿐 자동 생성 허용이 아니다. `repairMode=off`는 픽셀 변경 없이 필요한 진단만 제공한다.
- `v2.45.0` 단독 이식은 피하고 `.1`의 보행 보호, `.2`의 overlap-wrap 제어/탐색 최적화, `.3`의 실제 재생 프레임 이음새 판정을 관련 묶음으로 검토한다. 진단의 측정 대상이 source인지 최종 rendered인지 기록한다.
- RIFE TTA는 실제 실행 binary·model·옵션과 함께 recipe에 기록한다. GPU/CPU·원본 크기별 시간 측정 뒤 새 보정 경로에 적용하고 기존 저장 작업의 설정을 바꾸지 않는다. overlap-wrap은 프로젝트 실행 예산 안에서 사용하며, 끄거나 예산으로 중단한 경우 해당 단계를 성공한 것처럼 보고하지 않는다.
- 보간 캐시는 source RGBA·순서·비율·전처리 버전·실제 binary/model/TTA/필요 host identity를 포함한다. 현재 앱은 엔진 `align_set()` 전체를 호출하지 않으므로 CLI 플래그 추가만으로 완료 처리하지 않는다. cache hit에도 최종 품질 gate를 현재 정책으로 실행한다.
- 캐시는 프로젝트 범위의 재생성 가능한 데이터로 둔다. 원본·채택 셀·계보는 캐시 밖에 보존하고, 캐시 누락/손상은 로컬 재계산으로 복구한다. 외부 경로를 요청값으로 받아 쓰지 않으며 동시 작업의 부분 파일은 원자적 게시로 차단한다.

**완료:** 같은 MP4로 현행/신규 결과를 비교하고 최종 셀·PNG/GIF/WebP·개별 시간·원본/보간/대체 계보가 일치한다. RIFE 없음·캐시 hit/miss/손상·모델/옵션 변경·중단에서 보존과 시간 예산을 확인한다. 실제 RIFE 시험과 대역 시험, 합성 이미지와 실제 생성 영상을 구분한다. 품질 기준을 통과한 묶음만 새 작업에 적용한다.

### M3. 비교·원본 복원·후속 보정

**목표:** 잘못 만들어진 프레임을 근거 있는 원본으로 복원하고, 부위 보정이 실제 무엇을 옮기는지 보여준다.

- source(영상·준비 이미지·keyed 원본·추출 기록), origin(최초 복원 전 결과), baseline(현재 비교 기준)을 별도 ID·해시로 연결한다. 후속 복원에서 origin을 최신 baseline으로 바꾸지 않는다. 과거 증거가 부족하면 해당 비교/복원만 `unknown`으로 표시하고 일반 편집·출력은 유지한다.
- 비교는 **최종 셀의 픽셀·좌표·시간·sample mapping**으로 수행한다. 다른 구간·다른 시간·다른 crop을 seam 숫자 하나로 우열 판정하지 않는다. `improved/non_regressing/regressed/unknown`을 나눠 보여주고 미술적 완성도 점수로 부르지 않는다.
- upstream 복원 계약 `source-restoration-v5`, repair schema 4, comparison schema 6과 정책 identity를 함께 다룬다. 일반 비교 `same-sample-defects-v1`의 schema와 혼동하지 않는다. 구 증거를 최신 의미로 읽지 않는다.
- 복원은 입력 원본으로부터 가능한 셀만 대상으로 하고 jump·ghost 회귀를 확인한다. 비교 화면은 원래 결과와 후보를 유지하며, 선택한 결과를 새 동작으로 저장한다. 사용자 픽셀 편집은 source 원본으로 간주하지 않는다.
- 기존 follow preview/apply에 영역별 검사·stretch floor·`read-on` 대응을 붙인다. 잘못된 strip hash·구간 변경·보간으로 대응이 증명되지 않는 경우 `uncertain` 사유를 보여주고 영역을 추정 적용하지 않는다.
- preview 이후 동작 revision/설정이 바뀌면 기존 preview로 저장하지 못하게 한다. 실패하면 모든 기존 동작·별도 출력은 유지한다.

**완료:** 비교 불가 자료·변경된 origin·잘못된 증거 버전·stale preview·저장 실패·백업 복원을 포함해 false improvement와 데이터 덮어쓰기를 막는다. 복원 파일과 라이브러리에 동일한 셀·순서·시간이 기록된다.

### M4. 재생 의미·방향 세트·게임 출력

**목표:** 새 동작을 프레임룸에서 만든 그대로 게임용 파일에 전달한다.

M4a에서 재생 계약·동작 제작/미리보기를 먼저 마치고, M4b에서 방향 세트·game-pack을 연결한다.

| 재생 요청 | 제품 의미 | 필요한 호환 처리 |
| --- | --- | --- |
| loop | 반복, 닫히는 주기 필요 | 기존 `loop=true`와 호환, 실패를 단발로 바꾸지 않음 |
| once-return | 한 번 수행 후 시작 자세로 복귀 | 마지막 복귀 셀을 보존. 기존 ‘루프 시작/끝 중복 제거’를 일괄 적용하지 않음 |
| once-hold | 한 번 수행 후 종료 자세 유지 | 기존 `loop=false`, `hold-last` 활용 가능. 처음과 다른 안정 자세인지 검사 |
| lifetime | 효과가 생겼다가 끝남 | 종료 뒤 숨김 의미가 필요. 현재 hold-last 전용 재생기·runtime으로 성공을 가장하지 않음 |

`playMode`는 제안 필드명이다. 기존 state preset의 의미는 유지하고, 새 명시 모드·사용자 동작 문장·선택 종료 이미지의 검증과 저장을 함께 정의한다. 이름만으로 mode를 추정하거나 기존 `loopMode`(구간 선택 방식)와 섞지 않는다. 임의 문자열은 prompt 길이·지원 조합·경로와 분리해 검증한다.

현재 `Clip.endBehavior`, `render.ts:validateRuntime()`, `pipeline.py:_clip_gates()`와 편집 allowlist는 hold-last만 지원한다. **플레이어·편집·job 검증·작업 snapshot·runtime·GIF/WebP·backup/restore를 함께 바꾼다.** 새 종료 의미가 필요한 출력은 명시적 runtime 차기 버전으로 추가하고 기존 v1을 계속 읽는다. v1로 표현할 수 없는 내보내기는 사유를 표시하며 의미를 손실 변환하지 않는다. 전체 프로젝트 schemaVersion까지 올릴 필요가 있는지는 이 단계의 호환 fixture로 판단한다.

`video-stop`은 원본 도입부를 역방향으로 재사용하는 파생 동작이다. 별도로 촬영한 자연스러운 정지라고 소개하지 않는다. 접합·되돌아오는 다른 동작·너무 긴 도입부·원본 근거가 불합격이면 생성 없이 거절하고 수동 자료 선택을 안내한다.

방향 세트는 여러 clip ID/revision·방향·기준·지면선·anchor·공통 크기를 묶어 출력한다. 개별 clip은 보존하며 프레임 수·주기 시간 차이를 숨기지 않는다. 기준 지면선과 몸의 부유/그림자 영역을 구분한다.

game-pack은 **현재 편집 결과의 canonical bake**를 입력으로 삼는다. upstream packing·manifest helper를 재사용하되 원본 strip을 다시 읽어 사용자 픽셀 편집·외곽선·앵커·시간을 우회하지 않는다. 별도 크기 출력이 필요하면 명시한 출력 recipe로 한 번 변환하고 변환한 anchor·manifest·픽셀을 검증한다. 기존 atlas/runtime/PNG/Aseprite/animations ZIP은 유지한다.

**완료:** 재생 모드별 시작·끝·반복 횟수·종료 화면이 앱과 runtime 및 각 형식의 표현 한계 안에서 일치한다. 방향·occurrence·프레임 이벤트가 pack의 출력 순서와 연결되고, 같은 입력의 pack은 결정적이며 기존 출력은 덮어쓰지 않는다. GIF로 종료 숨김을 표현할 수 없다면 한계를 메타데이터/화면에 표시한다.

### M5. 신규 자료·음원 제작·게임 자산 통합

**목표:** pixel-draw·UI kit·tile·logo·sound 제작과 자료형·출력을 모두 제품 기능으로 연결한다. 도구별 중간 출시는 가능하지만 M5 전체는 흡수 완료의 필수 조건이다.

1. **추출·배치부터:** sheet 전체 배율·contain·추출 manifest·행 anchor 수정, alpha/checkerboard 진단을 기존 가져오기/추출에 연결한다. 원본 비율·부분 알파·그림자·사용자 편집을 보존한다.
2. **pixel-draw 실험 도입:** 기존 생성 화면의 별도 방식으로 제한한다. `grid.txt`·palette·원문 응답·후보·수정 내역과 재생 시간을 보존한다. 최대 64프레임을 1회 호출로 표시하지 않는다. 후보 수·4프레임 묶음·행 복구·재작성·선택 판단의 호출 상한을 실행 전에 표시하고, 암묵적 추가 호출은 끈다. 구독/API 경로는 사용자가 선택한 정책으로 고정하고 자동 유료 fallback은 도입하지 않는다. Batch 접수 ID와 resume은 새 제출 없이 이어받는다.
3. **UI kit·tile·logo:** 이미지 asset 위에 필요한 typed metadata를 추가한다. UI inset/padding/fill, 타일 양축 반복, logo 텍스트·matte 검사와 출처를 보존한다. logo는 기본 파이프라인에서 이미지 2회+문자 검사 2회의 호출이 있으므로 ‘이미지 1장=1회’로 안내하지 않는다. 자동 재생성으로 문자 오류를 해결하지 않는다.
4. **sound 제작·pack v2 자료형:** images/tiles/ui와 함께 오디오 자료형을 추가한다. upstream `sound`의 SFX/BGM 생성 provider·인증·비용 계약을 조사해 프로젝트 연결을 구현한다. 생성뿐 아니라 가져오기·듣기·정규화·loop/crossfade·원본 요청 캐시·샘플 단위 재생 시간·프레임 이벤트·Opus/AAC 출력과 sound-only pack까지 포함한다. 음원을 기존 이미지 assets에 바이너리로 억지 등록하지 않으며 파일 검증·폴더 저장·백업·복구를 함께 지원한다. provider가 없으면 필요한 설정을 안내하되 해당 기능을 완료로 집계하지 않는다.

이미지는 자료 asset으로, 애니메이션은 동작·프레임·시간으로, UI kit/타일/오디오는 전용 메타데이터와 파일로 저장한다. CLI로 만든 결과도 대상 프로젝트를 먼저 연결하고 등록을 확인한다. 업로드 manifest의 외부 경로·symlink 이탈·과대 크기·파일 누락을 접수/출력 경계에서 검사한다.

**완료:** 각 자료형의 import→preview/edit→별도 output→project folder→backup/restore→game-pack 경로를 확인한다. 실험적 pixel-draw의 품질과 logo glow의 키색 혼합 한계를 표시한다. 지원하지 않는 자료는 명시적으로 거절하며 빈 동작으로 변환하지 않는다.

### M6. 제작·편집·장면 도구의 전체 연결

**목표:** 앞선 신규 기능 표에 없던 공개 기능까지 기능 대장과 대조하여 앱 연결 누락을 없앤다. M6도 필수 구현 범위다.

- **이미지·방향 제작:** gen-set/방향 anchor·시트 행 생성·추출·curation·완성 atlas unpack/recompose를 기존 후보·동작 라이브러리에 연결한다. 팔레트 변형은 원본 색·사용자 편집을 보존하는 새 변형으로 저장한다.
- **영상 제작 도구:** extend/edit·시작/끝 그림·참조 입력·prompt helper와 외부 영상 제작물 가져오기를 지원한다. 외부 도구가 필요한 경로는 명세 전달과 결과 등록·출처 기록까지 제공한다. 각 신규 생성 작업의 요청 ID·원본·파생 관계와 복구는 M1 계약을 따른다. 인증이 없는 도구를 실행 가능하다고 표시하지 않는다.
- **후처리·검사:** compose-layers/rig, breathing, projected shadow, motion/contact QA, handed-check, 원본의 후보 비교·수동 구간·보정 지시를 현재 편집·결과 확인에 흡수한다. 이미 구현한 기능은 중복 제작하지 않고 공개 기능과의 차이를 보완한다. 결정적 팔레트 변형은 과거 제외된 ‘의미를 추정하는 부위별 색 복원’과 구분한다.
- **생성형 중간 프레임:** 두 프레임 사이를 AI가 새로 그리는 작업으로 제공한다. RIFE 영상 보간과 별도 기능이며 생성 원본/take·입력 identity·요청·사용 경로를 보존한다. 기존 프레임을 대체하거나 모델 호출을 숨기지 않는다.
- **ambient loop:** 일반 배경 영상의 반복 구간·RIFE seam bridge·수치/영상 검증을 제공한다. 캐릭터 두 걸음 주기 판정으로 처리하지 않고 별도 영상 자료로 저장한다.
- **scene:** 기존 스프라이트·이미지·타일·음원의 배치, plane·camera·lighting·이동 명세·렌더/검사와 결과 보존을 지원한다. scene spec과 참조 asset revision을 저장하고, 원본 자산 수정 없이 장면 결과를 새로 만든다. 캐릭터 전용 기준 입력을 음원·장면에 강제하지 않으며 기존 6단계 흐름 안에서 자료형별 도구 진입점을 설계한다.
- **workflow·출력 연결:** 기본 설정·사용 경로·옵션 우선순위·Phaser/Flame 메타데이터·편집/합성 webview 기능을 기존 앱과 대조한다. 같은 기능을 앱이 제공하면 그 경로를 대장에 기록하고 독립 webview를 중복 띄우지 않는다. 사용자 선택이 필요한 provider 대체 기능은 명시적 선택으로 연결하고 기존 작업의 암묵적 재제출로 바꾸지 않는다.

**완료:** 고정 버전의 공개 기능 대장에 미조사·구현 예정·검증 대기·차단 항목이 없고 모든 항목에 실제 앱 진입·저장·출력·복구·검증 근거가 있다. 함수나 CLI가 존재하는 것만으로 완료 처리하지 않는다. provider 실측이 필요한 기능은 승인된 실행 범위에서 별도 확인하며 모의 시험만으로 실제 생성 성공을 표시하지 않는다.

## 5. 코드·계약·검증이 함께 도달할 곳

| 묶음 | 구현 지점 | 호출자·저장/계약·검증 범위 |
| --- | --- | --- |
| M0 | `engine/engine-lock.json`, `engine/upstream-files.sha256.json`, `scripts/doctor.py`, 필요한 엔진 파일 | 로컬 패치·license/NOTICE·설치/잠금 의존성, `test_engine_guard.py`, 변경 모듈의 upstream 시험 |
| M1 | `adapters/spritegen/video_provider.py`, `services/worker/video_task.py`, `services/worker/main.py`, `services/api/main.py` | `VideoStep.tsx`, JobCard/ProviderConnections, VIDEO/OpenAPI/types, `test_video_jobs.py`, `test_worker_recovery.py`, `test_video_batches.py`, 저장 회귀 |
| M2 | `engine/sprite-gen/sprite_gen/video/`, `video_processing.py`, `video_normalization.py`, `video_finish.py`, `frame_selection.py` | VideoDiagnostics/videoDiagnosticMessages·원본 선택 경로·관찰/규칙 선별과의 조합, `test_video_processing.py`, `test_video_quality_upgrade.py`, `test_frame_selection.py`, 실제 RIFE·캐시 시험 |
| M3 | `adapters/spritegen/clip_tools.py`, `services/worker/clip_tools_task.py`, `CandidateComparison.tsx`, `ClipToolsPanel.tsx`, `clipTools.ts` | 새 job operation은 실제 필요할 때 기존 registry에 추가, revision/hash 검증, `test_clip_tools.py`, `test_clip_tool_processing.py`, 저장·복원·백업 시험 |
| M4 | `video_prompt.py`, `video_provider.py`, `video_task.py`, `VideoBatchPlan.tsx`, `VideoStep.tsx`, `render.ts`, `types.ts`, `services/api/edits.py`, `alignment/pipeline.py`, `alignment/animation_exports.py` | runtime validator·출력 verifier·ZIP·도움말·guide, 프롬프트/방향·편집·재생·animation export·기존 v1 fixture 회귀 |
| M5 | 기존 `provider.py`·`GenerationStep.tsx`·`AssetsStep.tsx`·extract 경로와 자료 등록/backup/restore | library 모델·project scope·신규 자료 validator·pack export, `test_asset_generation.py`, 자료/추출/API·프로젝트 폴더 회귀 |
| M6 | upstream gen/video/effects/compose/qa/scene 도메인과 기존 앱의 대응 adapter·worker·편집/출력 진입점 | M0 기능 대장으로 누락된 호출자·자료형·계약·시험을 확정하고 도구별 저장·출력·복구 회귀 연결 |
| 모든 동작 | worker 저장 트랜잭션, `scripts/project_library.py`, 프로젝트 폴더 flush | `test_standalone_library.py`, `test_animation_publication_guard.py`, 원본/시간/중복/저장 실패 회귀 |

계약 변경은 기존 `packages/contracts/VIDEO.md`, `IMPLEMENTATION.md`, `openapi.json`과 웹 타입을 함께 갱신한다. 동작 의미가 추가되는 시점에 요청 예시·이전 요청 fixture·잘못된 조합을 먼저 확정한다. 기획만을 위해 별도 Postman workspace·중복 스펙·새 서버를 만들지 않는다.

## 6. 검증 순서와 출시 기준

| 검증 | 확인할 결과 | 구분할 한계 |
| --- | --- | --- |
| 보존 | 기존 프로젝트 사본의 원본/출력 해시·revision·편집·개별 시간 유지 | 사용자 원본에 시험을 직접 쓰지 않음 |
| 복구 | POST ≤1, 같은 ID GET 재개, local-only 저장 재개, 중단/중복/충돌 안전 | 로컬 HTTP 모의와 실제 provider 장애 실측 구분 |
| 품질 | 같은 MP4의 현행/신규 구간·한 주기·발/장비·이음새·잔상·outline·alpha·시간을 비교 | 서로 다른 MP4의 차이를 엔진 개선으로 단정하지 않음 |
| 성능 | 장치·원본 크기·RIFE 옵션·cold/warm 캐시별 시간·peak memory·호출 수, timeout/취소 | upstream의 성능 수치를 이 장치의 실측으로 재사용하지 않음 |
| 저장 | 별도 파일 + library + 폴더 DB 재조회, 폴더 이동·재열기·backup/restore | 캐시가 있어야만 열리는 결과 금지 |
| 출력 | canonical 최종 셀·anchor·occurrence·ms timing·playback·pack manifest 정합 | GIF 시간/팔레트·종료 표현 한계 별도 기록 |
| UI | 기존 ego TaskSpace에서 오류/복구/비교/저장/출력·키보드 흐름 | Chrome/별도 Chromium 실행·사용자 제어 공간 탈취 금지 |

회귀는 영향 묶음의 engine·integration·web 시험부터 수행하고, 단계 출시 전 전체 필수 검사·웹 빌드·diff 리뷰를 마친다. 앱과 엔진 pytest는 import 충돌을 피하도록 각각의 cwd에서 실행한다. `scripts/doctor.py`는 현재 소스 무결성 확인이며 해당 변경으로 새 동작이 연결됐다는 증거는 아니다. 실패/skip은 원인·영향을 기록한다.

출시 순서는 **1차 M0–M2(보존·복구·루프 품질), 2차 M3(복원·후속 보정), 3차 M4(새 재생·세트·게임 출력), 4차 M5(자료·음원 제작), 5차 M6(나머지 제작·편집·장면 도구)**로 잡는다. 의존성이 풀린 도구는 먼저 제공할 수 있지만 M0–M6 전체를 마치기 전에는 ‘전체 흡수 완료’라고 보고하지 않는다. M5·M6을 선택 백로그로 돌리거나 별도 필요성 판단으로 삭제하지 않는다. 기존 작업/결과는 새 설정으로 다시 쓰지 않고 새 recipe는 검증된 새 작업에만 적용한다. 문제 발생 시 새 기능 노출·신규 실행을 중단하되 기존 파일·이력·이미 접수된 요청 ID는 보존한다.

전체 완료 판정은 **공개 기능 전 항목의 대응표 + 앱 실행 경로 + 자료형별 저장/복구 + 결과/출력 정합 + 실제 검증 근거**를 모두 요구한다. 보호 계약과 충돌하는 기본 동작은 기존 정책에 맞게 적응한 기능과 원본과의 차이를 명시한다. 실험적 품질·플랫폼·인증 제약은 표시하되 기능 자체를 범위에서 제거하지 않는다.

## 7. 역할·의존성·착수 전 결정

- **PM — GPT 6.1 Sol · xHigh:** 범위·인수 조건·반영 목록·진행 문서·검수 지적 조율과 완료 보고.
- **구현 — GPT 6.1 Sol · xHigh:** 코드·회귀 시험·계약·도움말 구현과 검수 수정. PM과 별도 세션으로 실행한다.
- **검토 — GPT 6.1 Sol · xHigh:** 변경 영향·실제 앱 연결·원본/비용/저장 보호·실행 증거 검수. 구현과 독립된 세션으로 실행하며 PM은 제품 코드를 직접 수정하지 않는다.
- 2026-10-22 사용자 변경 지시: 모든 역할은 Orca CLI `--agent codex --model gpt-6.1-sol --effort xhigh`로 실행한다. **Opus 5.5는 사용자 재허용 전까지 금지**다. 아래 M0 실행 기록의 모델명은 당시 이력으로 보존한다.
- 세션·위임·메시지·진행 확인은 Orca CLI만 사용한다. 동일한 `video_processing.py`/엔진 공통 파일의 병렬 수정은 피하고, 독립 fixture/계약 조사와 읽기 전용 검수만 병렬화한다.
- 의존성: M0→M1/M2, M2→M3, M1+M2→M4a→M4b. M5의 도구는 각 자료형 계약과 M1 저장 보호를 확보한 후 나눠 진행한다. M6의 영상 작업은 M1, 편집 파생은 M3/M4, scene은 필요한 M4/M5 자료형·출력 계약을 선행한다. M6을 마지막까지 조사하지 않고 M0에서 전체 대장과 담당을 확정한다. 코드 소유가 겹치는 통합은 순차 수행한다.

현재 확정: **전체 기능 흡수, 품질·복구부터 구현, M0–M6 필수, 프로젝트 전용 통합과 기존 데이터 보존**이다. 기존 기본값과 6단계 제작 흐름은 유지하면서 자료형별 도구를 확장한다. 착수 시 M0에서 확인할 사항은 공개 기능 전체 대응표, 사용 가능한 실제 회귀 영상 유형, legacy recipe 재현 범위, RIFE 장치별 실행 예산과 source 증거를 기존 결과에서 확보할 수 있는 범위다. 이 정보가 없으면 해당 품질 효과를 완료로 주장하지 않는다. 재생/pack/음원/scene 스키마 및 제작 도구의 provider·호출 상한은 각 단계 시작 전에 정한다.

## 8. 이번 기획의 실제 확인 결과

- GitHub API로 `v2.45.3`·tag commit·`main` 동일성·버전 차이 401커밋을 확인했다.
- 현재 엔진 lock, 6단계/영상/저장 계약과 provider·선별/보정·worker·clip 도구·runtime/출력 검증의 연결 지점을 읽었다.
- 문서만 추가하고 제품 문서 목록에 연결했다. 엔진·앱 코드, lock, 사용자 자료, 인증, 공용 스킬은 변경하지 않는다.
- Orca 검수 Run 생성이 `no_active_sender_terminal`로 실패해 지정 모델 독립 검수는 미실행이다. 다른 세션의 handle을 빌리거나 다른 하위 에이전트로 대체하지 않았다.
- 실제 앱/엔진 시험·브라우저·RIFE 성능·유료 생성은 실행하지 않았다. 과거 문서의 통과 수를 이번 결과로 재사용하지 않는다.
- 사용자 후속 지시에 따라 선택 확장 범위를 전체 필수 기능으로 변경하고, 공개 기능 목록과 대조해 sound 생성·영상 extend/edit·생성형 중간 프레임·후처리/장면 도구를 추가했다. 이번 수정도 기획 문서에 한정하며 구현 완료를 뜻하지 않는다.

## 9. M0 착수 기록

2026-10-21 사용자 요청으로 구현에 착수했다. 과거의 `no_active_sender_terminal` 문제는 이 작업 전용 Orca PM 터미널을 생성하고 그 터미널에서 Run을 만들어 해결했다. 다른 세션의 핸들을 사용하지 않았다.

| 역할 | 모델·추론 | 이번 작업 |
| --- | --- | --- |
| PM | GPT 6.1 sol · High | 범위·위임·결과 통합·완료 보고, 제품 코드 직접 수정 없음 |
| 구현 | Claude Opus 5.5 · High | 전체 기능 대장·파일별 이식 조사·실제 회귀 자료 manifest·검증 명령/시험 |
| 검수 | GPT 6.1 sol · High | 독립 누락/보존 위험 조사 후 구현 결과의 최종 검수 |

Orca 시작 영수증의 requested/effective 모델·추론 일치와 두 작업의 turn start를 확인했다. Run은 `run_fa25d7306241`, 구현 Task는 `task_b0a40e2559d4`, 검수 준비 Task는 `task_d09881521e8c`다. M0 준비 검수와 최종 결과 검수는 구분한다. 이 식별자는 실행 이력이며 다른 채팅이 해당 세션의 권한을 갖는 근거가 아니다.

이번 구현 범위는 M0다. 사용자 자료·DB·인증·공용 스킬은 보존하고 유료 생성·commit/push/PR/merge/배포는 수행하지 않는다. M0 완료와 검수 결과가 확인되기 전에는 M1 이후 기능을 구현 완료로 표시하지 않는다.

첫 구현 후 출력 경로·임시 파일·함수별 이식 근거·보고서 보장 범위를 검수하고 Claude Opus 5.5 · High 수정 작업을 추가했다. 최초 구현 세션이 사용자 제어 상태로 전환돼 재사용하지 않았으며, 새 작업 전용 세션에서 수정했다. 수정 Task `task_0e13b1c40dd8`와 최종 검수 Task `task_9a0c7b9cd503` 모두 성공으로 완료했다. 구현·수정 결과와 한계는 [M0 보고서](absorption/M0_REPORT_2026-10-21.md)에 기록한다.

**M0 완료 판정:** GPT 6.1 sol · High 검수자가 M0/engine guard 47건, 전체 통합 2,521 통과·1 skip(연구 원본 부재), 고정 upstream·대장·파일/함수 이식계획·baseline 검사와 독립 replay 2/2를 직접 확인했다. 검수 구간 DB·project JSON 9파일 해시는 동일했다. 최초 접근 이전의 DB 해시가 없어 작업 시작 전부터의 모든 바이트 불변을 소급 증명하지는 않는다. 원인 미확정 삭제/출력 경합은 M1 보존 작업으로 남긴다. 기능 대장 84항목의 상태는 모두 구현 예정이며, M0 기준 구축 완료를 전체 기능 흡수 완료로 해석하지 않는다.

## 10. M1 완료 기록

2026-10-22 새 PM이 Run `run_5dbba83351d2`를 생성했다. PM·구현·독립 검수는 모두 GPT 6.1 Sol · xHigh이며 두 worker의 requested/effective와 turn start를 확인했다. 구현 Task `task_55937e2c26b7`, 검수 Task `task_fcce5da0fbd5`를 유지해 검수 수정까지 같은 두 세션에서 수행했다. PM은 제품 코드를 수정하지 않았다.

**M1 완료:** POST 최대 1회, 같은 ID 조회/다운로드 제한 재시도, 절대 수신 deadline, 검증 후 원자적 MP4 게시, 원본 우선 복구, 저장만 재시도, 삭제/출력/작업 등록 강제 경합 보호를 구현하고 독립 검수에 합격했다. 검수에서 찾은 느린 body 시간 초과·토큰 반사·다운로드 재시도 누락·symlink 원본 덮어쓰기·legacy receipt 비밀 재노출을 수정하고 재현 시험으로 확인했다.

최종 전체 integration 2,577 통과·1 skip(저장소에 없는 연구 원본), 영향+엔진 235건, 웹 541건·빌드, doctor 407파일·diff 검사 통과다. 독립 검수는 안전 transport 54건·TLS 4건과 ego smoke/DOM을 확인했다. 사용자 파일은 구현 1,029개·검수 970개의 전후 해시가 일치한다. 상세 명령·실패 이력·검증 범위는 [실행/인수](absorption/M1_RUN_2026-10-22.md), [구현](absorption/M1_IMPLEMENTATION_2026-10-22.md), [독립 검수](absorption/M1_REVIEW_2026-10-22.md)에 기록한다.

M0 JSON·baseline과 원본/DB/인증/공용 스킬은 보존했다. M1 엔진 차이는 lock의 전후 해시로 명시하며 M0와 같은 결과라고 주장하지 않는다. M2–M6 및 영상 참조/종료 입력은 아직 미구현이다. 유료 생성·Git 게시·배포는 하지 않았다. 실제 provider 인증/일시 장애·RIFE 성능·전체 UI 여정은 미검증이다. M2 착수 전 새 PM에게 이관하며 미커밋 M1을 승인 없이 커밋하거나 되돌리지 않는다.


## 11. M2 완료·기능 경계 인계

2026-10-22 새 PM `term_33b48ee3-9f56-4528-a4bb-a346b368d768`가 M1 기능 경계 인계를 수락했다. 이전 PM의 확인 `msg_a97a9e1ed596`에 따라 이후 M2 배정·문서 소유권은 새 PM이다. Run `run_70d73cc5d001`의 구현·독립검수를 각각 GPT 6.1 Sol xHigh로 시작했고 requested/effective 일치·turn_started를 확인했다. 범위·완료 조건·실제 증거는 [M2 실행 기록](absorption/M2_RUN_2026-10-22.md)에 남긴다.

M1 미커밋 변경과 역사적 M0 기준을 보존하고, VERSION/engine digest/legacy retry 제품 보호를 M2 선행 범위로 수행한다. 실제 provider·유료 생성·Git 게시·배포는 승인 범위가 아니다. M2 9개 대장 항목은 실제 앱 호출·저장·검증 근거와 대조하며 엔진 코드 존재만으로 완료 처리하지 않는다.


**M2 완료:** 새 recipe VERSION·실제 엔진/보간 identity와 구 recipe 재개 차단, 관측 두 걸음/불확실 근거·ghost/flow/torso·최종 rendered seam·프로젝트 캐시·TTA/overlap 명시 선택을 기존 앱 호출열에 통합하고 독립 검수에 합격했다. 완성 결과의 저장만 retry·원본/채택 셀/계보·기본8장 비보간·기존 시간과 수동 범위는 유지한다. M0 대장의 M2 9항목에 실제 호출·저장·시험 근거를 보고서에 매핑했다. 전체84항목 완료를 뜻하지 않는다.

최종 앱2598passed/1skipped, 엔진video/util762passed(15markerwarnings), 웹543passed/build, doctor433/diff통과. 독립 core103·guard47·cache교체2·enginecache31 및 자체 실제영상 API/worker/출력/library/폴더DB·ego smoke/DOM을 확인했다. 같은 MP4의 M1/M2 구간33–59·8셀·개별ms·PNG/GIF/WebP가 일치하고 사용자1029파일은 변경·누락·추가0이다. 양 worker는 succeeded 후 transcript captured·released2/reclaimable0으로 정리했다. 자세한 근거는 [M2 실행](absorption/M2_RUN_2026-10-22.md), [구현](absorption/M2_IMPLEMENTATION_2026-10-22.md), [독립검수](absorption/M2_REVIEW_2026-10-22.md)다.

실제 RIFE544px off/on cold/warm 실행은 확인했으나 overlap은 실제60초예산에서 중단돼 성공/품질개선으로 집계하지 않는다. CPU/다른장치성능·TTA미술품질우월성·전체UI여정은 미검증이며 ego추가펼치기click은timeout이다. 실제auth/config·공용스킬·자료는 동일하지만 넓은사후manifest의Grok런타임4파일변화는 원인미확정으로 분리했다. 기반pin·qualityVersion 및 M0역사JSON/M1변경을 보존했고 M1+M2는 미커밋이며 유료생성·Git게시·배포는 하지 않았다. M2→M3 기능 경계에서 새PM으로 이관한다.


## 12. M3 제품 최종 수용·세션 결산

2026-10-22 새 PM `term_6a03edc7-a106-4325-8d75-23aaa0ea7c12`가 M2→M3 소유권을 인수하고 Run `run_db69615cf19f`에서 구현1·독립검수1을 GPT 6.1 Sol xHigh로 운영했다. 두 requested/effective와 실제 turn start를 확인했고 PM은 제품 코드를 수정하지 않았다. M1+M2 미커밋 사본 대비 M3 제품/계약/시험34파일을 구분하며 역사M0 JSON/baseline·M1/M2 원문을 보존했다.

source/origin/baseline 콘텐츠 ID·최종 셀/좌표/개별ms/sample mapping, source-restoration-v5 repair4/comparison6와 same-sample-defects-v1 schema1·정책 identity, 불확실/legacy·stale preview 차단, 새 동작 저장·별도 출력/library/폴더DB·저장만 retry/ZIP/cold 재열기를 기존 경로에 통합했다. 일반 비교와 원본 복원 제약을 분리하고 실제 nonzero follow의 portable 계보를 검증하며, read-on 원본12/대상8 SHA의 열수 경계도 보완했다. M0의 M3 6항목별 실제 연결은 [구현 보고서](absorption/M3_IMPLEMENTATION_2026-10-22.md)에 매핑한다.

최종 고정509 SHA·tested-source-subset-start가 일치하고 앱2653pass/1skip, engine876/web545/build(동일SHA 재사용), doctor442/diff가 통과했다. 독립14경계·영향227·실제보존MP4/출력/library/폴더DB·ZIP/fresh 인덱스 재열기와 source2/unknown21·origin23legacy를 확인했다. 인수차단R1의 보고서/실identity 바인딩과 no-op 부모증거·follow비교·read-on 경계는 같은 구현 세션에서 수정했으며 최종ego7의stale·복원실제저장·파일/폴더DB 일치와보고서를수용했고 두worker_done succeeded를확인했다. 검수release는captured/closed, 구현release는retained/user_takeover로사용자확인중이다. [실행·검증·정리](absorption/M3_RUN_2026-10-22.md), [독립 검수](absorption/M3_REVIEW_2026-10-22.md). M3 제품은합격·미해결finding0이며 세션결산은위실제상태와구분한다. 전체84항목완료를뜻하지않는다.

기존1029 사용자자료·공용skill/auth/config의 SHA/크기 변경·누락0, 별도 M1/M2 세션정리아카이브10추가를 분리해 보존했다(메타는사용자요청정리라고기록하나원요청/생성주체/승인원문은이Run에서직접미확인). 실제영상의 accepted 복원 제안·미술 우월성·유료/provider/observer·다른장치 성능·전체UI/screenshot은 미검증이며, 기존 엔진 문서10링크 실패는 시작 사본에서도 같은 문제다. 누적10MB 검수프로젝트의 CPU지연을 일반성능 개선으로 주장하지 않는다. Git게시/배포는 수행하지 않았다. M3 완료·정리 뒤 사용률 수치가 없는 환경의 기능 경계 규칙에 따라 M4a 새PM으로 이관하며, M0–M6 전체 진행 승인과 M4b/M5/M6 필수 범위는 유지한다.
