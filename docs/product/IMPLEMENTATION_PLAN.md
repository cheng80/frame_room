# 구현 계획

앱 구현은 새 세션에서 시작한다. 각 단계는 완료된 제품의 일부이며 M0/M1만으로 최종 MVP 완료를 선언하지 않는다. R01–R12 전체와 [수용 테스트](ACCEPTANCE_TESTS.md)가 최종 기준이다.

## 단계와 완료 조건

| 단계 | 구현 내용 | 검수 가능한 결과 | 다음 단계 조건 |
| --- | --- | --- | --- |
| M0 환경·포크 | 고정 소스 복사, engine-lock, 독립 venv, React/FastAPI 뼈대, 실행기, 계약 타입, fixtures | 하나의 로컬 실행 진입점·health·한국어 프로젝트 화면. 공용 설치본 해시 보존 | 빌드·환경 검사 성공, upstream/소재 고지 보존 |
| M1 프로젝트·원본 | SQLite/assets/revisions, 업로드, 참조 역할·승인, 프로젝트 열기·복제·백업, 편집 저장 | 원본 등록→기준 승인→재열기. API로 실제 파일 저장 | 원본 해시 불변, ACK/충돌 처리, 손상 입력 방어 |
| M2 이미지·정렬 | cutout·pre-fit extraction, component 검수, 공통 scale/manual anchor/공중/overflow | 실제 기존 PNG와 자체 시트에서 비율·발·무기 유지 | 웅크림471로 확대하지 않음. 650px 무기 잘림을 감지. source mapping 보존 |
| M3 동작·검수·출력 | candidates/occurrences, 비파괴 편집, duration, loop, canvas, outline, 고정 bake, ZIP/runtime/호환 JSON, 독립 뷰어 | 가져오기 여정이 UI에서 끝까지 동작 | 전체 RGBA parity·시간·저장/복원·빈 timeline·save failure 게이트 통과 |
| M4 생성 앞단·작업 | provider capabilities, 상태별 prompt/참조 설정, dispatcher/worker/SSE, 취소·재시도·복구, 부분 생성·채택 | 모의 job과 실제 엔진 단계를 UI에서 추적 | 모의/실제 구분. 중복 제출·불명 결과·강제 종료 회귀. 기존 승인 프레임 보존 |
| M5 실제 생성 완주 | 사용 가능한 기존 승인된 provider 경로 실제 실행, 결과 검수, 실패 수정, 새 프로젝트 생성 여정 | 실제 생성 artifact와 요청 lineage, 출력 bundle·재열기 | 실제 provider 및 UI E2E 증거. 접근 제한은 미검증으로 기록하고 나머지 구현 완료 |
| M6 납품 | 깨끗한 재실행, 브라우저·접근성, 전체 필수 테스트, 사용 안내, 최종 상태 | 실행 URL/실행법·출력 예제·테스트 보고·알려진 한계 | 미해결 필수 결함이 없고 실제/미검증 범위를 정확히 설명 |

M4 작업 실행기의 공통 기반은 M1/M2와 함께 먼저 만들 수 있다. 복잡한 파이프라인을 HTTP 요청 안에서 임시 구현한 뒤 전체를 다시 작성하지 않는다. 순서는 사용자가 검수할 수 있는 결과의 우선순위이며 의존성을 거슬러야 한다는 뜻이 아니다.

## 첫 작업

1. `HANDOFF.md`, PRD, 기술/API·테스트 문서와 조사 baseline을 읽는다. 현재 파일/Git 상태를 확인하고 사용자 변경을 보존한다.
2. 연구 fixture와 프로젝트 소스의 역할을 분리한다. 공용 스킬은 읽기만 하고 버전 고정 사본을 `engine/sprite-gen/`에 마련한다.
3. engine-lock과 라이선스를 보존하고 앱/엔진 의존성을 각각 lock한다. 실제 엔진 import 경로가 새 사본을 가리키는지 검증한다.
4. API/worker/React를 실행한 뒤 프로젝트 저장·실제 이미지 업로드·다시 열기를 하나의 수직 기능으로 만든다.
5. 정렬과 최종 bake 경로를 연결해 기존 PNG 여정을 먼저 완주한다. 계속해서 생성 앞단 UI와 실제 실행을 연결한다.

## 병렬 작업과 소유권

작업 분리는 지원되는 하위 에이전트를 사용하고 동일 파일의 동시 수정을 피한다. 사용자는 병렬 위임을 허용했다. 계약 책임자는 주 구현 세션이다.

| 작업 묶음 | 독립 쓰기 범위 | 선행 계약 |
| --- | --- | --- |
| 웹 화면 | `apps/web/` | 생성된 API 타입, R01–R12, UI 상태 |
| API·저장 | `services/api/`, `packages/contracts/` | revision·asset·job schema |
| 엔진·정렬 | `engine/sprite-gen/`, `adapters/spritegen/`, `alignment/` | pre-fit geometry, immutable inputs, bake contract |
| 작업 실행 | `services/worker/` | job lease·checkpoint·status/events |
| 회귀·통합 | `tests/` | 실제 fixtures와 결정된 endpoints |

통합 책임자는 lockfile·root 설정·문서·실행기를 관리한다. 하위 작업의 성공 메시지에만 의존하지 말고 실제 변경을 검토하고 해당 경로를 실행한다. 사용자 소유의 새 채팅은 이번 최종 구현 채팅 하나이며, 내부 하위 작업을 별도 사용자 채팅으로 무분별하게 늘리지 않는다.

## 검증 실행 원칙

- 단계마다 해당 기능의 단위/통합 검증을 실행하고, UI 흐름은 실제 브라우저에서 확인한다. 엔진 mock만으로 이미지 처리 완료를 선언하지 않는다.
- 고정 research fixtures 재실행은 가설 재현이다. 제품 UI/worker를 통과하는 regression tests를 별도로 둔다.
- 테스트 범위는 [수용 테스트](ACCEPTANCE_TESTS.md)의34개 연구 연계 항목과 추가 운영 항목을 적용한다. 실패를 숨기는 skip·경고 변경으로 통과시키지 않는다.
- 생성 테스트는 기존 연결의 허용 범위에서 실제 결과 한 건부터 시작한다. 새로운 유료 API로 자동 전환하지 않는다. 인증·quota 문제가 있으면 같은 실패 호출을 반복하지 않는다.
- implementation progress에 완료 단계·실행 명령·테스트 결과·알려진 결함을 기록한다. 새 세션은 계획 제시에 그치지 말고 구현·실행·검증·발견한 문제 수정을 이어간다.

## 개발 명령의 납품 계약

현재 앱/명령은 아직 없으므로 아래는 **구현해야 할 실행 계약**이다. 파일을 만든 뒤 실제 성공한 명령으로 README와 핸드오프를 갱신한다.

| 목적 | 기대 진입점 |
| --- | --- |
| 최초 환경 준비 | `scripts/setup.sh` 또는 동등한 로컬 설치기 |
| 개발 API/worker/UI 실행 | `scripts/dev.sh` |
| 일반 사용자 실행 | `scripts/start.sh` 및 macOS에서 쉽게 여는 실행기/안내 |
| 프런트 빌드 | 앱 디렉터리 package script `build` |
| Python/엔진 통합 검사 | 전용 venv의 pytest, 공용 엔진 경로 import 금지 |
| 브라우저 여정 검증 | 로컬 서버를 대상으로 한 E2E와 저장된 출력 독립 재생 |

공개 배포·원격 저장소 변경은 이번 납품 조건이 아니다. 코드와 앱은 사용자의 로컬 프로젝트에서 실행되도록 완성한다.
