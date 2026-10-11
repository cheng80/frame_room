# 구현·검증 현황

> 2026-10-06 자료 정리: 아래 조사·실험의 원본, 비교 결과와 전용 스크립트는 사용자 요청으로 삭제했다. 제품 결정·구현 기록은 보존하며 과거 경로를 현재 실행 가능한 자료로 해석하지 않는다.

## 2026-10-11 후속: 번들 크기와 테스트 클라이언트 의존성 경고 해결

데스크톱 편집 작업을 기준으로 번들·의존성 경고를 정리했다. 모바일 실기와 VoiceOver 검증은 이번 수용 범위에 추가하지 않았다.

- Vite의 기본 500kB 경고 기준을 유지하고 React·React DOM client 런타임을 별도 청크로 분리했다. 기존 단일 JS **512.86kB**에서 앱 **288.16kB**, 런타임 **222.41kB**로 나뉘어 production build에 크기 경고가 없다. 전체 JS gzip 합계는 약 **155.37kB**로 기존 **155.74kB**와 거의 같으며, 초기 다운로드량 감소를 주장하지 않는다. 앱 코드 변경 시 런타임 캐시를 별도로 재사용한다.
- 설치된 Starlette `1.7.0`의 TestClient는 `httpx2`를 먼저 사용하고 기존 `httpx` 대체 경로에 deprecation 경고를 발생시킨다. 별도 `httpx` 호출이 없는 것을 확인한 뒤 선언과 설치 lock을 `httpx2==2.13.1`로 정리하고 `engine-lock.json`의 설치 목록·lock 해시를 함께 갱신했다. 경고 필터나 라이브러리 소스 수정은 사용하지 않았다.
- 웹 전체 **442 PASS**, 앱 전체 통합 **2,316 PASS / 1 SKIP** (`-W error`), TypeScript/Vite production build, `uv pip check`, lock/설치 버전·SHA 일치, 전용 엔진 **407파일 무결성**, `git diff --check`가 통과했다. SKIP은 기존 연구 원본 자료가 없는 시험이다. 앱과 별도 Pixi 데모의 `npm audit`는 취약점 **0건**이다.
- 사용자 허가로 기존 ego Space 37을 재개해 실제 production 두 JS 파일 로딩·편집 화면 렌더링·API/worker/engine 연결 smoke를 확인했다. localStorage 전체 문자열이 재로딩 전후 동일하다. 사용자 프로젝트 저장이나 새 생성은 실행하지 않았다. 증거는 `output/dependency-cleanup/browser-before.json`, `browser-after.json`이다.

아래 과거 검증 기록의 번들·Starlette 경고는 이 변경으로 해결됐다. 장시간 부하 시험은 이번 검증에 포함하지 않았다.

## 2026-10-11 후속: 비교 이동·속성 도움말과 공통 처리 정리

**두 이미지 크게 비교**에 이전·다음 프레임 이동을 추가했다. 확대창·비교 기준·배율은 유지하며 재생 슬롯과 후보 목록의 순서를 구분한다. 반복 슬롯, 양끝 이동 제한, 숨긴 후보를 보고 있을 때 필터를 꺼도 다른 후보로 이동하는 경우를 처리한다. 두 이미지의 제목·이미지 영역·파일 정보를 같은 행에 배치하고 작은 후보도 패널 맞춤으로 확대한다. 속성 주요 제목 오른쪽의 물음표는 해당 제목 옆에 간단한 설명을 열며 바깥 클릭·Escape·닫기를 지원한다.

- 비교 표시·배율·확대창을 `CandidateComparison`, 자료/기준 이름의 공백 정리·Enter·한글 조합·Escape·충돌 차단을 `EditableNameInput`, 제목 설명을 `PropertyHelp`/`PropertyHeading`으로 공유한다. 거절 사유는 후보별로 초기화하고 비교창 상태는 프레임 이동 시 유지한다.
- `SourceSteps`의 가져오기·외형 기준·생성·추출을 각각 분리하고 공통 레이아웃은 `SourceToolLayout`에 둔다. 기존 재내보내기 경로와 다섯 컴포넌트의 본문을 그대로 보존했다. 비교 CSS도 해당 컴포넌트에 모았다.
- API·worker·영상/이미지 adapter·정렬 파이프라인을 함께 검토했다. 프로젝트 전용 엔진의 출처 검사를 기존 `alignment.pipeline._engine`으로 통합하고 기존 오류 코드를 유지한다. SQLite 조회 context가 종료 시 연결을 닫도록 보완했다. 수동 영상 구간의 정수 변환과 안전 여백 범위를 후처리/렌더의 기준에 맞췄다.
- 출력 job과 exports 접수는 기존 `enqueue(connection=c)`로 같은 트랜잭션에서 처리한다. 접수 기록이 누락된 과거 출력 job은 `EXPORT_MISSING`으로 실패 처리해 다음 작업을 막지 않는다. 중복 요청·동시 삭제·rollback·커밋 후 폴더 동기화 실패·원본 및 snapshot 보존을 격리 시험으로 확인한다.

웹 전체 **442 PASS**, 앱 전체 통합 **2,316 PASS / 1 SKIP**, TypeScript/Vite production build·설명서 HTML/ZIP 생성·실행/저장 OpenAPI 30경로 일치·전용 엔진 407파일 무결성·ego 연결 smoke·`git diff --check`가 통과했다. SKIP은 기존 연구 원본 자료가 없는 시험이다. 중간 통합에서는 동시 삭제 후 자료 확인의 정상 `ASSET_MISSING`(424) 응답을 새 시험이 허용하지 않아 1건 실패했다. 정상 거절 응답을 반영한 관련 API **128 PASS** 후 최종 전체 실행에서도 통과했다.

기존 ego Space 37에서 8개 슬롯 왕복·비교 기준/배율 유지·도움말 열기/닫기·자료 확대와 이름 입력 취소를 확인했다. 1678px 데스크톱 및 390px/320px 화면 에뮬레이션에서 같은 높이의 나란한 이미지와 가로 넘침 없음을 확인했다. 좁은 화면의 숨겨진 속성 패널 때문에 모달까지 사라지던 문제는 body portal로 해결했고, Tab/Shift+Tab이 본문으로 잠시 빠지는 구간을 공통 `EditorDialog`에서 보완했다. 실제 브라우저 접근성 트리에서는 비교 모달과 이름 붙은 컨트롤만 접근 가능했다.

로컬 API·worker 갱신 전후 저장된 4개 프로젝트와 작업 목록은 동일하며 전체 localStorage 문자열과 기존 미저장 초안 18개가 유지된다. 비교창은 원래 화면 크기로 복원해 사용자에게 남겼다. 증거는 `output/healer-walk/ego-refactor-verification.json` 및 실제 ego 캡처다. 검증 단계에서 새 생성과 사용자 프로젝트 저장은 실행하지 않았다. 실제 모바일 기기/VoiceOver 발화·장시간 부하 시험은 실행하지 않았고, 고정된 상류 엔진 전체를 리팩터링하지 않았다. 기존 Starlette/httpx 경고와 500kB 초과 단일 JS chunk 경고가 남는다.

## 2026-10-11 커밋·푸시 전 최종 검증

사용자가 누적 변경의 커밋·푸시를 요청해 전체 통합을 다시 실행했다. **2,300 PASS / 1 SKIP**, 웹 전체 **432 PASS**, TypeScript/Vite production build·설명서 HTML/ZIP 생성·OpenAPI 저장본/실행 schema 일치·`git diff --check`가 통과했다. 변경 소스·문서의 개인 키/인증 토큰 패턴 검사에서 일치 항목이 없었다. 선택 회귀 1개는 기존 연구 자료 부재로 제외됐고 기존 Starlette/httpx 경고 및 JS 단일 chunk 505.76kB 경고가 남는다. 기존 브라우저 검증 결과를 재사용했으며 새 모델 생성과 사용자 프로젝트 저장은 실행하지 않았다.

## 2026-10-11 후속: 자료 이미지 확대와 표시 이름 편집

자료 목록과 접힌 영상 처리 결과의 썸네일을 누르면 **자료 이미지 크게 보기** 창에 원본 URL의 이미지를 표시한다. 카드와 확대창의 **자료 이름**은 Enter 또는 입력칸을 벗어나면 `renameAsset` 초안에 적용하고 상단 저장으로 확정한다. 빈 이름은 원본 파일명으로 돌아간다. 이미지 선택 목록과 기준 그림의 자동 이름에도 자료 표시 이름을 반영하며, 원본 파일명·내용·해시·출처·연결 및 승인 상태는 보존한다. 표시 이름은 프로젝트 snapshot에만 저장하고 재조회·이력 복원·복제·ZIP 백업 복원을 지원한다.

확대창 닫기·Escape 이벤트가 바깥 자료 창까지 닫던 문제는 공통 `EditorDialog`에서 자기 자신의 이벤트만 처리하도록 수정했다. 확대창만 닫히며 원래 썸네일로 포커스를 복원한다.

- 웹 전체 **432 PASS**, 관련 API·프로젝트·파이프라인 통합 **269 PASS / 1 SKIP**, TypeScript/Vite production build·설명서 HTML/ZIP 생성·`git diff --check` 통과. 단일 JS chunk 505.76kB 경고와 기존 Starlette/httpx 경고가 남는다.
- 전체 통합 최초 실행은 **2,299 PASS / 1 FAIL / 1 SKIP**였다. 추가 중인 백업 회귀 시험이 게시 후 이동된 staging 파일을 읽어 실패했다. 게시된 artifact URL로 읽도록 수정하고 위 관련 269개를 다시 실행해 통과했다. 해당 기능 완료 시에는 전체 통합을 반복하지 않았으며, 이후 커밋 전 최종 전체 실행에서 **2,300 PASS / 1 SKIP**를 확인했다.
- 격리 API 시험에서 타입·200자 한도·빈/중복 이름·없는/다른 프로젝트 자료 ID·batch 원자성·저장 버전 충돌·원본 metadata/파일 보존과 실제 ZIP 복원을 확인했다. 실행·저장·실제 서비스 OpenAPI가 일치하고 Postman 계약 assertion **1 PASS / exit 0**다. 처음에는 재시작 전 서버에 `RenameAsset` schema가 없어 실패했으며, 진행 작업이 없음을 확인하고 서비스를 갱신한 뒤 통과했다.
- 기존 ego Space 37에서 원본·영상 기준 캔버스 확대, 한글 이름 변경·공백 정리·빈 이름 fallback·되돌리기, 확대창 닫기·Escape 후 바깥 창과 포커스 유지 등을 확인했다. 최종 localStorage 전체 문자열과 성직자 프로젝트 저장 snapshot이 동일하며 사용자 미저장 편집 **18개**를 보존했다. 증거는 `output/healer-walk/ego-asset-name-before.json`, `ego-asset-name-verification.json`, `ego-asset-name-preview.png`다.

실제 사용자 프로젝트를 저장하거나 새 이미지·영상을 생성하지 않았다. 상단 저장은 이름뿐 아니라 현재 편집 초안 전체를 저장한다. 모든 화면 크기는 반복 검사하지 않았다.

## 2026-10-11 후속: 자료 목록의 영상 처리 결과 접기

자료 가져오기에서 원본·생성 이미지 등 주요 자료를 기본 목록에 유지하고 `video-input`, `video-frame-raw`, `video-frame` 출처의 자료만 **영상 처리 결과 N개**에 기본으로 접어 표시한다. 펼치면 기존 썸네일·크기·역할·출처·알파 정보를 그대로 확인한다. 영상 기준 캔버스에는 같은 이름의 출처 표시를 추가했다. 파일명이나 `derived` 역할만으로 숨기지 않으며, 영상 외 파생 이미지와 출처 불명 자료는 기본 목록에 남긴다. 저장 자료·기준 연결·후보·파일은 변경하지 않는다.

- 웹 전체 **422 PASS**, TypeScript/Vite production build·설명서 생성·`git diff --check` 통과. 기존 단일 JS chunk 크기 경고는 503.93kB다. 초기 신규 시험 2건의 JSX 문구 배열·자료 수 기대값을 수정한 뒤 최종 전체 실행에서 통과했다.
- 기본/영상 자료의 중복·누락 방지, 출처 기반 분류, 기본 접힘, 빈 목록과 영상 결과만 있는 목록, 생성·편집 호출 부재를 단위 테스트로 검증했다.
- 기존 ego Space 37의 성직자 프로젝트에서 기본 이미지 **2개**와 접힌 영상 처리 결과 **65개**를 확인했다. 마우스로 펼치기와 Enter로 접기, 390px 화면에서 펼치기·접기를 확인했다. 저장 프로젝트·작업 목록의 전체 응답과 localStorage 문자열이 동일하고 미저장 편집 **18개**가 보존됐다. 증거는 `output/healer-walk/ego-asset-groups-before.json`, `ego-asset-groups-verification.json`, `ego-asset-groups-collapsed.png`, `ego-asset-groups-mobile.png`다.

이번 변경에서는 새 이미지·영상 생성과 기존 자료 삭제를 실행하지 않았다.

## 2026-10-11 후속: GPT·Grok 개별 연결 상태

하단에 로컬 서비스와 GPT 이미지·Grok 영상의 준비 상태를 각각 표시한다. 각 제공자 상태를 누르면 **모델 연결 확인** 창에서 로그인 확인, 실패 이유, 모델 목록과 실제 생성 성공 이력을 별도로 볼 수 있다. 조회 중·조회 실패·서버 연결 끊김·제공자 누락은 준비됨과 구분하고, 제공자 조회 실패 시 로컬 서버 상태는 유지하면서 이전 제공자 상태를 지운다. 상태 확인은 기존 조회를 재사용하며 생성·로그인·초안 저장을 실행하지 않는다.

- 웹 전체 **418 PASS**와 TypeScript/Vite production build·설명서 생성·`git diff --check` 통과. 초기 테스트 1건은 조회 오류와 현재 로그인 실패를 혼합한 기대값으로 실패했으며, 두 상태를 별도 검사한 최종 실행에서 통과했다. Vite는 단일 JS chunk 503.05kB 경고를 표시한다.
- GPT 준비됨/Grok 미준비 혼합, 미정·누락·오프라인·조회 중, 이전 성공과 현재 로그인 실패 분리, 조회 실패 후 복구, 중복 확인 방지, 로컬 서비스/제공자 조회 실패 분리를 단위 테스트로 검증했다.
- 기존 ego Space 37에서 실제 두 제공자 상태·확인창·재확인·Escape 닫기·390px 화면 진입을 확인했다. 현재 실제 조회는 두 제공자 모두 준비됨이며 로그인 실패를 만들기 위해 실제 자격증명을 변경하지 않았다. 기존 성직자 프로젝트의 전체 localStorage와 미저장 편집 18개가 유지됐다. 증거는 `output/healer-walk/ego-provider-*.json`, `ego-provider-connections.png`, `ego-provider-footer.png`, `ego-provider-mobile.png`다.

이번 상태 표시 검사에서는 새 이미지·영상을 생성하지 않았다. 로그인 준비는 실제 서버 권한·사용량이나 이후 생성 성공을 보장하지 않는다.

## 2026-10-11 후속: 신체 구조 선택과 첫 자료 이미지 생성

신체 구조의 직접 입력을 제거하고 기준 그림·영상 생성에 같은 한글 드롭다운을 사용한다. **기준 그림의 구조 그대로 유지**는 목록 밖 형태도 원본 부위 수·부착 위치를 유지하도록 지시한다. 대표 형태는 두 발형·네 발형·다리 없음·여덟 다리형·두 발과 날개·네 발과 날개다. 거미·새·드래곤의 다리와 날개를 구분하며 인간형 팔·자세를 강제하지 않는다. 기존 빈 값의 이족 기본 동작과 저장된 복합 명세는 원문을 유지한다. 복합 값의 새 직접 입력은 없고 선택 시 해당 형태로 교체한다. 이는 프롬프트 제약이며 골격 강제 기능은 아니다. 비행 동작은 추가하지 않았다.

**라이브러리 → 자료 → 자료 가져오기 → AI로 이미지 생성**은 승인 기준 없이 GPT ImageGen으로 자료 한 장을 만드는 별도 모드다. 기존 생성 작업의 `scope: asset`을 사용하며 명시적인 **자료 이미지 1장 생성**에서만 요청한다. 원본·요청·영수증은 기존 자료/생성 이력에 보존하고 외형 기준을 자동 승인하지 않는다. 자료 모드는 동작 생성 설정을 덮어쓰지 않으며 기존 동작 생성의 승인 기준 요구와 재전송 방지를 유지한다.

- 웹 전체 **405 PASS**, 마지막 안내 문구 수정 후 관련 **17 PASS**. 통합 전체 **2,286 PASS / 1 SKIP**, 기존 Starlette/httpx 경고 1건. TypeScript/Vite production build·설명서 HTML/ZIP·`git diff --check` 통과. Vite는 JS 단일 chunk 500.08kB 크기 경고를 표시하며 빌드는 성공했다.
- 신체 구조의 모든 동작·시점·모델, 기존 prompt 바이트 보존, 구조별 발 정체 미확정, 이미지 metadata→영상 전달을 검증했다. 자료 생성의 기준 없는 접수·잘못된 입력 접수 전 거절·모의 단일 호출·원본 및 provenance 보관·체크포인트 재사용을 격리 시험에서 확인했다. OpenAPI 저장본은 실행 schema와 일치한다.
- Postman 실제 API의 자료 이미지 2장 요청은 의도한 **422 / provider.invalid_frame_count**, assertion **1 PASS**이고 작업 목록은 유지됐다. CLI는 4xx 응답으로 exit 1을 반환한다. Origin 헤더를 직접 지정한 앞선 CLI 검사 2건은 403으로 assertion 실패했으며, 선택 Origin 헤더 없이 session token으로 수행한 최종 검사만 정상 판정됐다. 서버의 Origin·session 보호는 변경하지 않았다.
- 기존 ego Space 37 `p1`에서 두 신체 구조 드롭다운·직접 입력 부재·새 형태의 실제 요청 설명·자료 생성 진입과 복귀·설명 입력을 확인했다. 연결 smoke **EGO_SMOKE_PASS**. 성직자 프로젝트 v15 snapshot·작업 3건·사용자 미저장 편집 18개를 포함한 전체 localStorage 문자열이 유지됐다.

위 자동·초기 브라우저 검사에서는 실제 GPT/Grok 생성을 실행하지 않았다. 모의 생성 PNG는 시험 자료이며 실제 생성 원본으로 소개하지 않는다. 신체 구조 지시 순응은 미검증이다. 브라우저 결과는 `output/healer-walk/ego-body-plan-presets.json`, `ego-asset-generation-verification.json`, `ego-asset-generation.png`에 보관한다.

후속 사용자 요청으로 기존 ego Space 37에서 **자료 생성 실제 확인 · SD 여성 힐러** 프로젝트를 만들고 자료 생성 UI를 통해 GPT ImageGen 한 장을 실제 생성했다. 작업 `93c99faa-1d98-44ef-9550-b3c9444dd74f`는 오류 없이 `needs_review`로 완료됐고 자료 1개·생성 이력 1개가 저장됐다. `scope: asset`, Codex · ChatGPT 구독, 모델 `gpt-6-sol`, 단일 호출 약 43초이며 기준·후보·동작은 자동 추가하지 않았다. 원본과 등록 PNG의 SHA-256은 같고 1222×1287 이미지에 실제 알파 채널이 있다. 효과 없는 정면 SD 여성 성직자와 황금 스태프가 자료 목록에 `AI 생성 원본 · Codex` 썸네일로 표시됨을 확인했다. 기존 성직자 프로젝트의 미저장 편집 18개 문자열은 그대로 보존했다. 실제 원본 사본은 `output/healer-walk/gpt-imagegen-asset-real.png`, 요청·결과·브라우저 증거는 `ego-real-generation-*.json`, `ego-real-generation-library.png`에 보관한다. Grok 영상 생성과 게임용 픽셀·알파 경계 품질 검수는 수행하지 않았다.

## 2026-10-11 후속: 보기 방향 변경과 이전 측면 지시 정리

영상용 기준 그림 생성에서 보기 방향을 선택하면 설명과 승인 기준의 알려진 이전 방향 표현을 실행 요청에서 정리한다. 외형·의상·장비를 든 손·효과 금지는 유지하고 원래 설명·승인 참조·생성 원본은 보존한다. **방향이 반영된 생성 설명 보기**로 확인하며 정면·뒷면에서는 보기 좌우를 적용하지 않는다. 새 이미지 요청의 방향·신체 구조·장비는 생성 snapshot에 기록하고, 영상의 기준 이미지 변경 시 해당 그림의 기록을 불러온다. 이전 그림은 기존 생성 설명에 기록된 시점을 지원하고 기록이 없는 그림은 방향을 확인하도록 안내한다. Grok 추가 지시의 이전 긍정 방향 문구도 실행용 문자열에서 같은 규칙으로 정리한다.

- 웹 전체 **380 PASS**, TypeScript/Vite production build·설명서 HTML/ZIP 성공. 통합 전체 **823 PASS / 1 SKIP**, 기존 Starlette/httpx 경고 1건. 마지막 정면·뒷면 좌우 문구 정리 후 관련 통합 **229 PASS**로 재확인했다.
- 이미지 선택 방향·잘못된 값의 접수 전 거부·원본 snapshot 불변·최종 제공자 prompt·다섯 Grok 방향·손/효과/동작 보존·한/영 공유 규칙·원래 설명 복원·그림별 방향 전환을 검증했다. 저장 OpenAPI와 실행 schema가 일치한다.
- Postman schema assertion **1 PASS / exit 0**. 잘못된 방향의 실제 API 요청은 의도한 **HTTP 422**로 작업 접수 전에 거절됐다. Postman assertion **1 PASS**이나 CLI는 HTTP 오류 상태에 **exit 1**을 반환했으며 성공 종료 코드로 취급하지 않았다. 최초 파일 본문 전달은 일반 body 검증 오류로 실패했고 파일에서 읽은 JSON을 직접 전달한 후 방향 거절을 확인했다.
- 기존 ego Space 37 `p1`에서 실제 성직자 설명의 다섯 방향·측면 문구 제거·오른손 유지·정면/뒷면 좌우 비활성·앞 대각선/왼쪽 설정 재열기·영상 기준 이미지 전환·Grok 추가 지시 정리를 확인했다. ego 연결 smoke PASS.
- 점검에서 추가한 설정 명령 1개만 되돌려 사용자 미저장 편집 **16개 전체 문자열**, 저장 프로젝트 v15 snapshot과 기존 작업 **3건**을 보존했다. 실제 사용자 저장·이미지/영상 생성은 실행하지 않았다. 증거는 `output/healer-walk/ego-view-direction-*.json`, `ego-view-video-ui.json`, `ego-view-preservation.json`, 실제 ego 캡처와 정제한 Postman 로그다.

자동 정리는 등록된 한국어·영어 표현만 지원한다. 기존 그림을 설정만으로 회전하지 않으며, 다른 방향의 동작에는 그 방향으로 새로 만든 기준 그림을 사용해야 한다. 실제 제공자 결과의 방향·외형 품질은 이번 변경에서 새 생성으로 검사하지 않았다.

## 2026-10-11 후속: 기준 그림 직접 이름 지정

슬롯 속성의 **기준 그림 이름**과 외형 기준 → 승인의 기준별 이름 입력을 추가했다. Enter 또는 입력칸을 벗어날 때 하나의 `renameReference` 초안을 적용하고 상단 저장으로 확정한다. 새 기준을 만들 때도 이름을 지정할 수 있다. 목록·비교·생성 기준·수동 검수·확대창은 지정한 이름을 우선 표시하며, 이름을 비우면 기존 번호·외형 설명·파일명 표시로 돌아간다. 같은 이름은 기준 번호로 구분한다.

optional `Reference.name`을 기존 snapshot과 edits 계약에 추가했다. 이름은 최대 200자 문자열이고 앞뒤 공백을 제거한다. 이름 변경은 기준/동작 승인·clipRevisionId·연결 ID·자산/원본 파일명·프레임·정렬·생성 설정을 그대로 보존한다. 새 endpoint·DB migration·생성 호출은 추가하지 않았다.

- 웹 전체 **360 PASS**, 앱 통합 **740 PASS / 1 SKIP**, TypeScript/Vite production build·설명서 HTML/ZIP·`git diff --check` 통과. SKIP과 Starlette/httpx 경고는 기존 항목이다.
- 격리 API 검증: 생성 시 이름·변경 저장/재조회·이력 복원·기존 이름 없는 기준·한글/이모지·빈/중복 이름·길이/타입/추가 필드 거절·없는 기준 batch 원자성·revision 충돌·승인된 기준/동작 보존을 확인했다. 실행 OpenAPI와 저장 계약 일치, Postman CLI 계약 assertion **1 PASS**.
- 기존 ego Space 37 `p1`에서 “효과 없는 오른쪽 측면” 입력 후 Enter·목록/확대창 이름·원본 그림 일치·빈 이름 fallback·승인 탭 이름 변경/blur·기준 승인 상태 유지·되돌리기를 확인했다.
- 사용자 미저장 편집 **14개 전체 문자열**, 저장 프로젝트 v15 snapshot과 작업 목록이 그대로 유지된다. 점검 중 실제 사용자 프로젝트 저장·추가 생성은 하지 않았다. 로컬 증거는 `output/healer-walk/ego-reference-name-verification.json`, 이름 입력/확대창 캡처와 Postman 계약 기록이다.

실제 저장·재조회·복원은 격리 통합 시험에서 실행했다. 사용자 프로젝트 저장과 모든 화면 크기·전체 제작 여정은 반복하지 않았다. 상단 저장은 이름 변경뿐 아니라 현재 편집 초안 전체를 저장한다.

## 2026-10-11 후속: 동작 기준 그림 확인

슬롯 속성의 **동작에 사용할 승인 기준** 아래에 연결된 그림·전체 외형 설명과 **크게 보기** 버튼을 추가했다. 원본을 별도 native dialog에서 표시하며 Esc·닫기 후 원래 버튼으로 포커스를 복원한다. 기준 목록·외형 기준 버전·후보 비교·생성 화면·동작 검수에는 내부 ID 대신 같은 기준 번호·외형 설명·파일명을 표시한다. 번호는 초안 기준도 포함한 프로젝트 목록 순서다. ID와 저장 계약은 변경하지 않는다.

기준이 없는 동작에는 프로젝트의 활성 그림을 대신 보여주지 않는다. 동작 기준 변경은 기존 편집 명령과 재검수 동작을 유지하고, 후보 비교의 기준 변경은 화면만 바꾼다. 선택으로 이미지·영상을 생성하지 않는다.

- 웹 전체 **353 PASS**, TypeScript/Vite production build·설명서 HTML/ZIP 성공, `git diff --check` 통과. 이름이 같은 파일 구분·자료 없음·그림 열기·실제 ID로 기준 전환·미연결 동작·비교 전용 전환을 검증했다.
- 기존 ego Space 37 `p1`에서 실제 기준 2 원본과 썸네일 일치·확대창 화면 내 표시·Esc와 포커스 복원·기준 1로 그림 전환 후 되돌리기·후보 비교만 전환을 확인했다.
- 사용자 미저장 편집 **14개 전체 문자열**, 저장 프로젝트 v15 snapshot과 작업 목록이 그대로 유지된다. 실제 생성·저장은 하지 않았다. 로컬 증거: `output/healer-walk/ego-reference-verification.json`, 실제 ego 확대창·썸네일 캡처.

이번 변경은 웹 표시만 수정했다. API·엔진 통합 검사를 다시 실행하거나 모든 화면 크기·전체 제작 여정을 반복하지 않았다.

## 2026-10-11 후속: 라이브러리 동작 삭제·확인창 높이

라이브러리 동작 탭 하단에 **선택 동작 삭제**를 추가했다. 확인창에서 이름·슬롯 수를 확인하고 **삭제 초안에 적용 → 상단 저장**으로 확정한다. 현재 동작과 재생 슬롯만 제거하며 후보·원본·정렬·다른 동작·이전 출력·저장 이력을 보존한다. 마지막 동작도 삭제할 수 있다. 저장 전 되돌리기와 저장 후 과거 버전 복원을 지원하며, 이력 복원은 프로젝트 전체 상태에 적용된다. 열린 출력 설정에서 삭제된 동작을 요청하지 않도록 선택 대상을 필터링했다.

확인창의 `height:auto`가 native modal의 위·아래 inset 사이를 채우던 문제를 `fit-content`로 수정했다. 삭제·목록 제거 확인창에 공통 적용하며, 안내는 두 문단으로 줄였다.

- 웹 전체 **348 PASS**, 최종 안내 메시지 정리 후 관련 **89 PASS**, TypeScript/Vite production build·설명서 HTML/ZIP 성공. 앱 통합 **722 PASS / 1 SKIP**. SKIP과 Starlette/httpx 경고는 기존 항목이다.
- `deleteClip`의 OpenAPI·실행 schema 일치, 삭제 후 재조회·마지막 삭제·충돌/없는 ID 거부 원자성·원본 보존·이력 복원 검증. 엔진 무결성 407파일 통과, `git diff --check` 통과.
- 기존 ego Space 37 `p1`에서 취소·삭제 초안·다른 동작 선택으로 전환·되돌리기를 확인했다. 실제 확인창은 높이 963px에서 약 207px로 줄고 화면 중앙에 배치된다. 연결 smoke도 확인했다.
- 성직자 프로젝트 v15 snapshot·작업 목록, 기존 2개 프로젝트 버전·209파일 해시와 사용자 미저장 편집 13개가 유지된다. 사용자 동작 삭제를 저장하거나 추가 생성하지 않았다. 로컬 증거는 `output/healer-walk/ego-clip-delete-verification.json`과 실제 ego 캡처다.

저장·재조회·이력 복원은 격리된 API 시험에서 실행했다. 실제 사용자 프로젝트의 삭제 저장과 전체 브라우저 여정은 실행하지 않았다.

## 2026-10-11 후속: 셀 경계·안전 여백 표시

편집 캔버스에 민트 실선의 셀 경계, 노란 점선의 안전 영역, 노란 띠의 사방 여백을 추가했다. 가이드는 출력 픽셀과 분리하며 켜고 꺼도 캔버스 이미지와 프로젝트 설정을 바꾸지 않는다. 기존 **테두리 보기**는 캐릭터 외곽의 색상 효과임을 알 수 있도록 **팀 테두리 보기**로 바꾸고, 팀 테두리 사용이 꺼져 있으면 비활성 상태와 설정 위치를 안내한다.

- 웹 단위 **335 PASS**, TypeScript/Vite production build·설명서 HTML/ZIP 성공, `git diff --check` 통과. API·엔진은 이번 표시 수정에서 변경하지 않아 기존 통합 검사를 반복하지 않았다.
- 실제 저장 렌더의 안전 영역은 셀 안쪽 사방 2px다. 64×128 초안은 4·8번 슬롯의 왼쪽이 안전 영역을 4px 초과하며, 96×128 동작의 8개 슬롯은 모두 영역 안에 들어간다.
- 기존 ego Space 37의 `p1`에서 두 셀의 경계 좌표·중앙 배치·가이드 토글 전후 동일 픽셀, 꺼진 팀 테두리 상태, 팀 테두리를 켰을 때의 실제 색상 표시·표시 토글을 확인했다. 설정 시험은 저장하지 않고 되돌렸다. 연결 smoke PASS.
- 성직자 프로젝트 v15의 전체 snapshot·작업 목록, 기존 2개 프로젝트 버전·209파일 해시 불변. 추가 생성과 저장 작업은 없다. 로컬 증거는 `output/healer-walk/ego-margin-verification.json`과 실제 ego 캡처다.

브라우저의 전체 기능 여정·재생 FPS는 이번 확인 범위에 포함하지 않았다. 프레임·앵커의 수동 검수는 여전히 대기 상태다.

## 2026-10-11 이미지 생성 전 Grok 영상 사용 선택

이미지 생성 화면에 **Grok 영상 사용** 선택을 추가했다. 사용하면 GPT ImageGen으로 방향·자세·장비와 효과 제외 조건을 반영한 기준 그림 1장을 만들고, 이후 영상 제작에서 그 그림을 Grok에 전달한다. 사용하지 않으면 기존 이미지 프레임 생성 설정을 유지한다. 선택과 설정 저장만으로 영상 생성은 호출하지 않는다. [실행 안내](../../apps/web/README.md), [설정 계약](../../packages/contracts/IMPLEMENTATION.md).

- 웹 단위 **330 PASS**, 앱 통합 **720 PASS / 1 SKIP**, TypeScript/Vite production build·설명서 HTML/ZIP 성공. SKIP은 삭제된 과거 조사 입력에 의존하는 시험이며 Starlette/httpx deprecation 경고가 남는다.
- 실행 OpenAPI 일치, 엔진 무결성 407파일 통과. 엔진 소스·공용 스킬은 변경하지 않았다.
- 실제 프레임룸 프로젝트 **SD 여성 성직자 · 효과 없음 · Grok 걷기** (`0c995ef6-9775-4347-81a4-3ef22b740e71`): Codex/ImageGen 기준 그림 1건 → Grok Pro 걷기 영상 1건. 측면 걷기는 시작 그림만 전달했다. 처음 가져온 built-in ImageGen 원본, 프레임룸 생성 원본과 Grok 원본 MP4를 각각 보존했다.
- 64×128 초안에서 안전 여백 부족을 발견해 같은 영상으로 96×128 동작을 재처리했다. 최종 동작 `87cf939b-8147-407a-a287-4862b72533b1`의 8장·1,083ms 유지, 저장 렌더와 PNG/WebP RGBA **8/8장 일치**, 안전 영역 통과. GIF는 형식 시간 단위에 따라 1,080ms다. 추가 유료 생성 없이 초안도 보존했다.
- 기존 2개 프로젝트 버전과 209파일 해시 불변. 로컬 증거는 `output/healer-walk/verification.json`과 생성 영수증·원본·미리보기이며 Git에 포함하지 않는다.

프레임·앵커 수동 검수는 대기 상태다. 원본 영상 진단에 머리의 수평 이동 경고 1건(몸 높이의 0.85%, 기준 0.75%)이 남는다.

**같은 날 ego 후속 실기:** 브라우저와 CLI는 정상 연결됐고 재사용 가능한 TaskSpace 목록이 비어 있었다. 이를 연결 장애로 해석한 초기 판단을 정정했다. [공식 안내](https://github.com/citrolabs/ego-lite/blob/main/README.ko.md)의 에이전트 Space 사용 방식으로 최초 점검 Space 37을 열고, 이후 같은 `p1`만 재사용했다. 프로젝트의 `test:e2e` 연결 smoke PASS, Grok 사용/미사용 전환과 원래 설명·8장 시트 설정 유지, 저장·새로고침 후 방향/장비 설정 복원, GPT 생성 자산이 Grok의 선택된 기준 이미지인 점, 96×128 걷기 동작 재생·정지를 실제 UI에서 확인했다. 재생 중 슬롯 전환을 관찰했으며 모든 프레임의 브라우저 재생 속도 측정은 하지 않았다.

점검 중 새 생성 작업은 0건이며 설정은 원래 값으로 정확히 복원했다. 동작·프레임·앵커와 기존 209파일은 불변이다. 성직자 프로젝트에는 설정 점검·복원의 저장 이력이 추가돼 v15가 됐다. 로컬 증거는 `output/healer-walk/ego-verification.json`과 화면 캡처 3장이다. Space 37의 `p1`은 완성 동작을 선택한 채 보존했다. 사용자가 별도 기능을 켜거나 Space ID를 찾아야 한다는 초기 안내는 적용하지 않는다.

## 2026-10-06 후속: 동작 보완·검사

기존 슬롯 속성의 접힌 **동작 보완·검사**에 부위 흔들림·새 동작 저장과 색 표식 장비 좌우 검사를 연결했다. 색 복원은 사용자 결정으로 제품 기능에서 제외했다. [구현·실제 검증 범위](CLIP_TOOLS_2026-10-06.md), [API 계약](../../packages/contracts/CLIP_TOOLS.md).

- 앱 전체 **710 PASS**(신규 58 포함), 웹 전체 **325 PASS**(신규 43 포함), TypeScript/Vite production build·설명서 HTML/ZIP 성공.
- 실행 OpenAPI 일치, 엔진 원본/승인 패치 407파일 무결성 통과. 엔진 소스는 이 후속 연결에서 변경하지 않았다.
- 격리된 실제 8장 동작으로 ego 미리보기·새 동작 저장·검수판·의심 슬롯 이동 확인. 8장·1,000ms 유지, 새 동작을 다시 렌더한 RGBA와 미리보기 **8/8장 일치**.
- 원본 동작·자산·정렬 및 사용자 데이터 1,182개 파일 불변, 신규 유료 생성 0건. 새 동작은 검수 대기이고 장비 검사는 자동 수정·승인하지 않는다.

브라우저의 일부 장비 폼 입력·제출은 DOM 이벤트로 검증했다. 상세 제한과 증거는 위 보고서를 따른다. 아래 공개 스킬 반영 수치는 이 후속 작업 이전의 기록이다.

## 2026-10-06 공개 스킬 반영 검증

걷기 기본 8장과 공개 sprite-gen v2.34 품질 기술을 반영했다. [적용 항목·실제 영상·한계](LATEST_SKILL_UPGRADE_2026-10-06.md), [재개 핸드오프](HANDOFF.md). 현재 상태는 `git status`와 `git log`로 확인한다.

| 검증 | 실제 결과 |
| --- | --- |
| 앱 통합 | 652 PASS |
| 웹 단위/production build | 282 PASS / 성공 |
| 엔진 video/frames/gen/curate/scene | 8,472 PASS / 1 SKIP |
| 추가 handed QA/compose/effects | 475 PASS |
| CLI/패키징 | 264 PASS |
| 엔진 무결성 | 407파일, 패치 80개 해시 통과 |
| 보존된 실제 MP4 3개 | 8장, 원본 한 사이클 시간 유지, PNG/GIF/WebP 출력 확인 |
| 실제 RIFE / RGBA | 24→32장 보간 11장·원본 대체 13장 / RGBA 8장 WebP 엄격 검사 통과 |
| ego 실제 앱 | 8장/12장 선택, 기존 영상 재처리·수동 시작 index 2, 진단·8슬롯·1,000ms 확인 |

신규 유료 생성 0건. 사용자 프로젝트·공용 SQLite 등 1,182개 보호 파일과 입력 해시는 유지했다. 기본 RIFE 경로의 실기 시험 1건은 skip했으나 프로젝트 RIFE는 실제 보존 영상에서 실행했다. Pillow/Starlette deprecation 경고가 남는다. 후보·앵커의 수동 검수는 대기 상태이며, 원본의 의미적 변색 복원과 비공개 웹 기능 동등성을 완료했다고 주장하지 않는다. 과거 검증 기록은 아래에 보존한다.

## 2026-10-05 인계 검증

영상 제작 보완과 프로젝트 폴더/SQLite 관리를 반영한 상태에서 아래 검증을 재실행했다. 실행·이전·작업 재개는 [HANDOFF.md](HANDOFF.md)를 따른다. 현재 브랜치/변경/커밋은 `git status`와 `git log`로 확인하며 이 문서에 특정 커밋을 최신으로 고정하지 않는다.

| 검증 | 실제 결과 |
| --- | --- |
| Python 앱 통합 | **511 PASS**, Starlette 테스트 클라이언트 deprecation 경고 1건 |
| 웹 단위 | **244 PASS** |
| TypeScript·Vite | production build 성공, 설명서 HTML/ZIP 생성 성공 |
| 엔진 영상·생성·cyan cutout | **1,752 PASS / 1 SKIP**, Pillow deprecation 경고 28건 |
| 실제 RIFE 실행 파일 | 프로젝트 설치 경로를 명시한 별도 보간 시험 **1 PASS** |
| 보행 실험 계약/선택 | **10 PASS**, 생성 호출 없음 |
| 엔진 무결성 | doctor의 원본/승인 패치 360파일과 lock의 패치 25개 해시 검사 통과 |
| 실행 계약·기존 데이터 | OpenAPI와 실행 schema 일치, API/worker ready, 5개 프로젝트 연결·버전 보존, 저장 보류/진행 작업 0, SQLite quick_check 정상 |

엔진 일괄 실행의 1 SKIP은 기본 탐색 경로에 없는 RIFE 실기 시험이다. 프로젝트 `.data/tools/rife`의 실행 파일을 명시한 후 같은 시험이 통과했다. 최초 저장소 루트에서 엔진/실험 시험을 함께 수집했을 때 `tests.video` import 충돌이 발생했으며, 아래처럼 엔진 디렉터리에서 별도 실행해 해결했다. 의존성 경고는 남아 있다.

```sh
# 저장소 루트; 임시 결과는 저장소 밖에서 관리
PYTHONDONTWRITEBYTECODE=1 engine/sprite-gen/.venv/bin/python -m pytest tests/integration -q -p no:cacheprovider
npm --prefix apps/web test
npm --prefix apps/web run build
PYTHONDONTWRITEBYTECODE=1 engine/sprite-gen/.venv/bin/python scripts/package-guide.py
PYTHONDONTWRITEBYTECODE=1 engine/sprite-gen/.venv/bin/python scripts/doctor.py
PYTHONDONTWRITEBYTECODE=1 engine/sprite-gen/.venv/bin/python -m pytest scripts/walk_experiment/test_selection.py -q -p no:cacheprovider
# 엔진 시험은 별도 프로세스/디렉터리에서 실행
(cd engine/sprite-gen && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/video tests/gen tests/frames/test_cutout_cyan.py -q -p no:cacheprovider)
# macOS에 설치된 선택 도구의 실제 시험; 다른 기기는 실제 설치 경로로 변경
(cd engine/sprite-gen && SPRITE_GEN_RIFE="$PWD/../../.data/tools/rife/rife-ncnn-vulkan-20221029-macos/rife-ncnn-vulkan" PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/video/test_rife.py::test_real_rife_makes_the_frame_between_in_colour_and_alpha -q -p no:cacheprovider)
```

이번 인계에서 새 AI 생성·유료 API 호출은 하지 않았다. 브라우저 전체 여정도 새로 반복하지 않았으며, 직전 구현 단계의 실제 ego 검증은 [프로젝트 폴더 결과](PROJECT_FOLDERS_2026-10-05.md)와 [웹 보완 결과](WEB_QUALITY_COMPLETION_2026-10-04.md)에 구분해 기록했다. 실제 프로젝트 폴더의 독립 복사/재열기/동일 bake를 확인했지만 다른 OS의 설치·네이티브 폴더 선택창까지 검증한 것은 아니다.

사용자 요청으로 임시 DB·검수 캡처·로그·중복 리소스 약 435MB를 정리하고 5개 프로젝트의 원본·이력과 기준 GIF를 보존했다. **아래 과거 기록의 `artifacts/`, `output/` 등 로컬 증거 경로는 현재 없을 수 있다.** 보존·삭제 범위는 핸드오프를 확인한다. 자동 회귀 통과는 모든 수용 시나리오나 수동 미술 검수 승인과 다르다.

## 2026-10-03 구현 당시 기록

2026-10-03 KST. 로컬 앱과 실제 GPT 생성 제작 예시를 구현·실행했다. 아래 실행 결과는 제품 수용 TEST-01–34 전체 PASS 선언과 다르다.

## 실행 결과

- 로컬 실행: `scripts/setup.sh` 설치·빌드, `scripts/start.sh` API/worker/정적 웹 실행 확인. 주소 `http://127.0.0.1:8765`.
- Python 통합 **159 PASS**: API 10, 이미지/출력 84, provider 계약 48, worker 복구 17. `artifacts/acceptance/python-tests.xml`. Starlette 테스트 클라이언트 deprecation 경고 1건.
- 웹 단위 **44 PASS**, TypeScript·Vite production build 성공.
- upstream 회귀 60 PASS. 전용 엔진 pin·패치 360파일 검사 통과. 공용 엔진 360파일 변경 0건.
- 에고 전용 `test:e2e` smoke 실제 PASS. Playwright 기본 실행은 차단했고 별도 Chromium 캐시 설치본 3개는 휴지통으로 이동했다. 자동 재설치하지 않는다.

## 에디터 화면 개편

긴 페이지를 창 높이에 맞는 라이브러리·캔버스·속성·하단 타임라인으로 바꿨다. 생성·추출·정렬·출력은 관련 이미지와 설정을 나란히 표시하는 도구로 연다. 선택한 슬롯·후보 맥락과 키보드 포커스를 유지한다. 에고에서 1152×768, 800×600, 320×700 및 도구 전환·슬롯 복제/되돌리기를 확인했다. [배치·검토 증거](EDITOR_LAYOUT_REVIEW.md).

## 실제 캐릭터 제작

프로젝트 **하늘 해적 · GPT 실제 제작** (`f29b69ab-8f8d-4dd2-ba87-37671121ff96`)의 저장 버전 37, 출력 `a6e757df-aca6-494c-ad44-25fe21d6c3cb`.

1. `image_gen.imagegen`으로 기준 캐릭터를 새로 생성. 코드로 그린 그림이 아니다. 실제 PNG와 출처 기록을 `artifacts/acceptance/real-character/sky-gunner-reference.*`에 보존.
2. 에고 TaskSpace9에서 UI로 업로드·외형 승인·프롬프트 설정. 프로젝트 SpriteGen adapter가 Codex/ChatGPT 구독 `gpt-6-sol`로 실제 시트 생성. job `549c3954-bf69-42b5-90e4-96f3b26c3176`. receipt·요청·참조 해시는 `generation-ledger.json`.
3. 실제 응답 1536×1024, 3×2 포즈. alpha=0 픽셀 1,099,012, 부분 alpha 473,852. 투명 요청은 파일 알파로 별도 확인했다. 낮은 알파의 경계 연결 때문에 자동 격자 추출 일부가 이웃 포즈를 포함했다. 해당 후보를 채택하지 않고 UI 수동 영역 6개로 다시 추출했다.
4. 공통 scale 0.8, 셀 512×512, 목표 발 (256,460), 각 포즈 수동 앵커. 프레임마다 별도 키 맞추기를 하지 않았다. 6슬롯 각100ms, 600ms 반복 동작을 편집·저장·검수·출력했다.
5. `atlas.png`, `pngs.zip`, `runtime.json`, `aseprite.json`, `qa.json`, `bundle.zip`을 에고에서 다운로드했다. 백업은 `project-backup.zip`.
6. 독립 뷰어에서 `/v1/*` API를 차단하고 내려받은 runtime+atlas만 열었다. 6개 수동 프레임의 서로 다른 bitmap, 실제 재생 샘플 7개 중 4개의 서로 다른 bitmap을 확인했다. `output/ego/independent-playback.json`. 배경 탭의 refresh throttling 때문에 이 관찰로 실제 게임 FPS 품질을 보장하지 않는다. 검사 후 API 차단은 해제했다.
7. 출력 oracle은 6 occurrence의 atlas crop↔ZIP PNG 전체 RGBA, 시간·반복, 6 frameSources와 부모 hash 계보를 PASS로 판정했다. `artifacts/acceptance/real-character/output-verification.json`. 원본·파생 14개 실제 파일 해시도 전부 일치했다.

자료 카드에 가져온 원본 / AI 생성 원본 · Codex / 추출 프레임 / AI 생성에서 파생을 실제 provenance로 구분한다. 에고에서 최신 빌드의 세 출처 표시를 확인했다. 파일명이나 그림 모양만으로 AI 생성 여부를 추정하지 않는다.

## 이전 증거와 한계

기존 로봇의 최초 `robot-idle.png`, `robot-sheet.png`는 Pillow로 만든 합성 테스트 자료다. 이후 `generated.png`는 그 로봇을 참조한 실제 GPT 결과다. 이를 처음부터 GPT로 만든 캐릭터라고 소개하지 않는다. 로봇 전체 생성·부분 재생성 실제 호출 3건은 `real-provider-ledger.json`에 따로 남겼다. 마지막 부분 재생성은 대상 crop 참조와 native alpha까지 확인했다.

이전 Playwright 가져오기·출력·충돌·복원 여정 2건은 과거 증거다. 사용자 브라우저 지시 이후에는 실행하지 않았다. 검수 거절/출력 오류 여정의 과거 세 번째 테스트는 API 사전 gate 추가 뒤 기대값을 수정했지만 Chromium으로 재실행하지 않았다. API 거절 사유·저장·출력 차단은 현재 Python 회귀에서 통과했다.

34개 수용 항목의 모든 하위 시나리오를 실행한 것은 아니다. 공개 raw 체크무늬 제거의 수동 복원 품질, 실제 스타일 참조 2장 비교, 모든 접근성/화면리더·대비·키보드 gate 조합의 수동 판정은 미완료다. 새 캐릭터의 생성 포즈는 AI 제작 예시이며 상용 애니메이션의 모든 세부 일관성이나 보간 품질을 보장하지 않는다. 자동 픽셀 시험을 사람의 최종 미술 승인으로 바꾸지 않는다.

## 구현·계약

API/SQLite revision·원본 보존·백업·복원, 단일 worker·durable checkpoint·강제 종료 복구, 결과 불명 외부 호출 자동 재시도 차단, raw crop·공통 배율·수동/공중 anchor·편집·가변 timing·outline·확정 bake·전체 RGBA parity·독립 뷰어를 구현했다. generation→cutout→crop 계보와 부분 재생성 대상 참조를 보존한다.

실행 API schema는 `packages/contracts/openapi.json`, 구체 계약은 `packages/contracts/IMPLEMENTATION.md`. Codex 품질/해상도 지정·외부 취소/조회는 미지원이며 유료 fallback은 활성화하지 않는다. 이 기록 시점에는 공용 스킬·연구 자료·다른 프로젝트를 보존했고 commit/push/PR/merge/배포는 하지 않았다. 현재 Git 상태는 직접 확인한다.


## 2026-10-03 후속: 제작 이력·승인·다음 작업

실제 추출 실행별 후보 묶음과 출처·사용처 이동, 수동 승인/자동 검사/변경 후 재확인 상태, 선택 동작의 다음 작업 안내를 추가했다. 웹 96개·Python 통합 209개 PASS, TypeScript/Vite 빌드 및 ego 복제본 저장·재승인·출력 여정을 확인했다. 원본 예제 v37과 14개 에셋은 보존했다. 상세 범위와 증거는 [WORKFLOW_REVIEW.md](WORKFLOW_REVIEW.md)를 참조한다.

설명서의 작업 공간·승인 본문과 화면을 갱신했다. 새 화면은 ego 화면 스타일 PDF의 렌더 결과이며 스크린샷 성공으로 표시하지 않는다. 기존 캡처·문서는 보존했다.
