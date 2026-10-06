# 캐릭터 스프라이트 에디터 제품 문서

2026-10-05 KST · **로컬 앱 구현, 영상 제작 보완·프로젝트 폴더 관리 반영**

다른 환경에서 이어서 작업할 때는 **[HANDOFF.md](HANDOFF.md)**부터 읽는다. 특정 커밋을 최신으로 고정하지 않으며 `git status`와 `git log`로 실제 상태를 확인한다. Git에 포함되지 않는 프로젝트 데이터·인증·선택 도구의 이전 방법도 핸드오프에 있다.

다른 프로젝트의 설명서를 만들 때는 [HTML 사용 설명서 제작 기준](../reference/user-manual/README.md)을 참고한다. 프레임룸의 스타일·구성, 과거 사용자 지시의 출처, 글자 크기·이미지 확대·패닝 조건과 재사용 요청문·검수표를 정리했다.

2026-10-06 사용자 요청으로 조사 원본·실험 산출물·비교 보고서·전용 스크립트를 정리했다. 아래에는 제품 요구·화면·계약·구현 기록을 유지한다. 과거 실험 경로는 현재 사용할 수 없다.

## 현재 상태와 실행 계약

| 문서 | 내용 |
| --- | --- |
| [HANDOFF.md](HANDOFF.md) | 새 환경 실행·프로젝트 이전·코드 탐색·비용/원본 보존·남은 제한 |
| [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) | 날짜별 실제 실행 결과와 자동/수동 검증 범위 |
| [프로젝트 폴더 적용](PROJECT_FOLDERS_2026-10-05.md) | 프로젝트 SQLite·목록 제거·없는 폴더 정리·실제 복사 검증 |
| [웹 보완 적용](WEB_QUALITY_COMPLETION_2026-10-04.md) | 영상 마무리·방향/묶음·RIFE·주기·애니메이션 출력 |
| [색상 회귀](VIDEO_COLOR_REGRESSION_2026-10-04.md) | 손/칼의 색 변화와 검수 GIF·에디터 PNG 처리 차이 |
| [영상 에디터 통합](VIDEO_EDITOR_INTEGRATION_2026-10-04.md) | Grok 로그인 생성·기존 MP4 처리·접수/재개 |
| [실행 계약](../../packages/contracts/IMPLEMENTATION.md) | 현재 데이터·편집·작업·출력 계약 |
| [영상 계약](../../packages/contracts/VIDEO.md) | 생성/처리/묶음과 마무리·출력 확장 |
| [프로젝트 폴더 계약](../../packages/contracts/PROJECT_FOLDERS.md) | 저장 구조·동기화·이전·등록 정리 |
| [OpenAPI](../../packages/contracts/openapi.json) | 실행 앱의 API schema |
| [웹 사용/검증 안내](../../apps/web/README.md) | 화면 기능, ego-browser 실행 규칙 |

기술 구성은 React/Vite/TypeScript, FastAPI, SQLite, 독립 Python worker다. 전용 엔진은 v2.12.1 기반에 공개 v2.19 영상 보완을 선별 반영한다. 코드·계약·회귀 시험으로 현재 동작을 확인하고 아래 초기 설계와 구분한다. 계약을 바꾸면 UI·시험·사용 설명서도 함께 갱신한다.

## 초기 설계와 조사 기록

아래 문서는 2026-10-03의 요구·판단·검증 계획을 보존한 것이다. 당시의 ‘영상 제외’, ‘구현 전’, NOT_RUN 또는 이 문서보다 오래된 시험 수를 현재 상태로 해석하지 않는다.

| 문서 | 내용 |
| --- | --- |
| [PRD.md](PRD.md) | R01–R12 요구와 제작 여정·수용 경계 |
| [UX_DESIGN.md](UX_DESIGN.md) | 초기 화면·편집 흐름·실패/저장/검수 상태 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 초기 스택·포크·실행기·저장·출력 설계 |
| [DATA_API_SPEC.md](DATA_API_SPEC.md) | 초기 geometry·timing·job·output 계약; 이후 변경은 실행 계약 참고 |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | M0–M5 구현 계획과 소유권·검증 계획 |
| [ACCEPTANCE_TESTS.md](ACCEPTANCE_TESTS.md) | 34개 제품 수용 기준과 시나리오 |
| [DECISIONS.md](DECISIONS.md) | 초기 명세 정정과 근거 |
| [사용자 합의](../planning/USER_DECISIONS.md) | 후속 요구·결정 |
| [구현 방향](AI_SPRITE_EDITOR_IMPLEMENTATION_2026-10-04.md) | 공개 데이터로 가능한 재구현 범위 |

연구의 19개 관찰 검사, 앱 자동 회귀 수, 34개 수용 기준은 다른 집계다. 실제 provider 생성, 모의 응답, 합성 시험 자료도 구분한다. 불필요한 검수 파일·로그는 사용자 요청으로 정리했으므로 과거 문서에 적힌 로컬 증거가 남아 있다고 가정하지 않는다.

[workflow-state.json](../planning/workflow-state.json)은 날짜가 있는 진행 스냅샷이다. 예전 채팅 ID·자동화 상태는 이력이며 새 환경의 권한이나 실행 상태를 뜻하지 않는다. [document-validation.json](document-validation.json)은 초기 문서 검사 기록이다.
