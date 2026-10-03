# 캐릭터 스프라이트 에디터 제품 문서

2026-10-03 KST · v1.0 · **조사와 제품 설계 완료, 앱 구현 전**

사용자가 요청한 `sprite-gen` 포크 기반 웹앱의 제작 기준이다. 기존 조사와 대화의 요구를 통합했다. 기술 구성은 React+Vite+TypeScript, FastAPI, SQLite, 독립 Python worker다. 엔진은 검증된2.12.1 commit을 고정하고 프로젝트 안에서 수정한다.

| 문서 | 내용 |
| --- | --- |
| [PRD.md](PRD.md) | R01–R12 요구, 두 제작 여정, 범위·완료 기준 |
| [UX_DESIGN.md](UX_DESIGN.md) | 화면·편집 흐름, 빈/실패/저장/검수 상태 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 스택·포크·실행기·저장·출력 구조 |
| [DATA_API_SPEC.md](DATA_API_SPEC.md) | 데이터와 API 정본, geometry·timing·job·output 계약 |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | 구현 단계·소유권·검증·실행 진입점 |
| [ACCEPTANCE_TESTS.md](ACCEPTANCE_TESTS.md) | 요구별 수용 시험·fixture·실행 상태 |
| [DECISIONS.md](DECISIONS.md) | 사실/결정/미확인과 초기 명세의 정정 |
| [HANDOFF.md](HANDOFF.md) | 새 구현 세션이 바로 읽고 제작을 시작할 지시문 |

새 구현 세션은 HANDOFF부터 읽는다. 구현 요구는 PRD, wire/API 상세는 DATA_API_SPEC이 정본이다. 연구 제안과 충돌하면 이 제품 문서의 결정과 근거를 따른다. 계약을 바꾸면 관련 UI·테스트·결정 문서를 함께 갱신한다.

## 핵심 결정

- 큐레이션 이전의 기준 이미지·생성 설정·생성·알파·추출을 UI화하여 전체 흐름을 연결한다.
- 포즈별 높이 정규화 대신 원시 crop·공통 scale·수동 앵커를 사용한다.
- 원본 불변, 안정 frame/occurrence ID, 가변 duration, save revision, 작업 복구를 구현한다.
- 확정 미리보기와 PNG·아틀라스는 같은 bake에서 만든다.
- PXF, 영상·다방향 자동화·원격 협업·공개 배포는 첫 구현 범위에서 제외한다.

## 근거와 현재 검증 상태

[mydot 후속 조사](../../research/hero-inc/2026-10-03-implementation-design/README.md), [엔진 감사](../../research/hero-inc/2026-10-03-implementation-design/engine-audit.md), [이미지 검증](../../research/hero-inc/2026-10-03-implementation-design/validation.md), [사용자 합의](../planning/USER_DECISIONS.md)를 통합했다.

연구19개 관찰은 위험 재현을 포함하며 앱 수용 시험 통과가 아니다. 제품 테스트는 아직 NOT_RUN이다. 프레임 높이·알파·출력의 일부 engine 경로는 확인했지만 실제 provider 생성, 새 UI 완주, worker 복구 등은 구현 세션에서 검증해야 한다.

진행 상태와 새 구현 채팅 ID는 [workflow-state.json](../planning/workflow-state.json)에 기록한다. 문서 자체의 링크/JSON/요구 검사 결과는 [document-validation.json](document-validation.json)에 저장한다.
