# 결정과 근거

2026-10-03 KST · 최종 제품 명세 v1.0. 직접 관찰·사용자 요구·새 설계를 구분한다.

| ID | 결정 | 근거와 영향 |
| --- | --- | --- |
| D01 | 캐릭터 제작 전체를 React 웹앱으로 구현 | 사용자 요구. 큐레이션만 보여주는 UI로는 완료되지 않음. PXF는 별도 |
| D02 | React+Vite + FastAPI + SQLite + 독립 worker | [아키텍처 조사](../../research/hero-inc/2026-10-03-implementation-design/architecture.md). 로컬 canvas·Python 처리가 중심이며 SSR/BFF가 필요하지 않음 |
| D03 | engine2.12.1 commit `b058341f7543f3adcbea227bd4e6b7587895b1bc` 고정 | [소스 비교](../../research/hero-inc/2026-10-03-implementation-design/baseline.json): 릴리스 파일360개 일치. main2.18.0은 버전만 확인했으므로 회귀 전 업그레이드하지 않음 |
| D04 | 애니메이션은 pre-fit crop + 공통 scale | [실험](../../research/hero-inc/2026-10-03-implementation-design/validation.md): 실제 자산 재조합 입력에서 웅크림320→471, 조준378→471로 확대. alpha 밴드 중심도 이동. `slice-sheet` 기본 사용 금지 |
| D05 | overflow를 별도로 차단 | 같은 실험의 합성650px 무기는 정상 종료했으나 알파2070픽셀 유실. exit code와 시각적 성공은 다름 |
| D06 | bbox와 몸 체고, 자동 발 후보와 수동 승인 분리 | 실제/합성 측정 및 공개 노트. 장비가 bbox/하단 밴드를 바꾸고 공중 자세는 바닥 고정하면 안 됨 |
| D07 | immutable asset + working base + revision | [엔진 감사](../../research/hero-inc/2026-10-03-implementation-design/engine-audit.md): 일부 기준 이미지 편집은 working base를 직접 바꿈. 앞선 조사에서 모든 편집을 비파괴로 뭉뚱그린 표현을 정정 |
| D08 | occurrence ID와 최종 가변 duration 구현 | engine selected 중복 제거, 임의 duration 필드 무시를 실험으로 확인. clone mapping과 composer/serializer 명시 지원 필요 |
| D09 | 한 번의 확정 bake가 모든 최종 출력의 근거 | export-pngs 기본 전체 후보·호흡 효과 차이, 저장 실패 후 출력 흐름의 위험을 감사. 앱 PNG는 확정 atlas에서 추출 |
| D10 | 빈 타임라인 차단·save ACK 검사 | engine 빈 selected는 전체로 해석될 수 있음. 새 API 정본에서 빈 상태/저장 실패를 숨기지 않음 |
| D11 | 실제 생성·모의 테스트·인증 준비 분리 | 연구는 provider 무호출 probe만 수행. Codex login-ready는 실제 생성 성공·quota 보장이 아님 |
| D12 | 정렬된 실제 이미지와 합성 반례를 별도 fixture로 유지 | 연구는 공개 WebP를 동일 decoded pixel PNG로 보존. 공개 PNG 원본 복원이나 실제 raw 체크무늬 제거 성공이라는 뜻이 아님 |
| D13 | 문서 완료 뒤 새 로컬 구현 채팅 생성 | 사용자 명시 요청. 조사 채팅의 범위를 바꾸거나 중복 앱 구현을 시작하지 않음 |
| D14 | provider·동시성 명시, 내부 timeout 재시도도 통제 | 엔진 감사에서 기본provider fallback, gen-set 기본6, Codex timeout 재시도1회 확인. 앱 큐만으로 외부 중복 요청 방지를 보장할 수 없으므로 adapter/포크까지 시험 |

## 초기 명세에서 바로잡은 부분

- 엔진 요청 파일의 실제 이름은 `sprite-request.json`이다. 추출 메타는 `frames/frames-manifest.json`이다.
- 거너471/320은 alpha bbox 높이이며 해부학적 체고 측정이 아니다. 512/18/2는 선택형 거너 preset이고320셀/16여백은 다른 설명 예시다.
- `unpack-atlas`의 가변 크기 PNG 중앙 배치는 발 정렬이 아니다. 앱 정렬 이후 동일 셀로 materialize한다.
- FPS 기반 균등시간을 가변 duration 지원으로 표현하지 않는다. 최종 MVP에는 별도 timing 계약과 소비자 구현을 포함한다.
- PNG/Aseprite 호환 JSON이 출력된다고 loop/anchor까지 각 포맷 단독으로 복원된다는 뜻이 아니다. runtime companion을 제공한다.
- Threads 자체 편집기 답변의 상위 글은 VFX 작업이다. 원작 캐릭터 통합 UI 전체를 확인했다는 근거로 쓰지 않는다.
- mydot 전달은 사용자가 직접 완료했다. 과거 문서의 미전달 기록은 당시 상태이며 현재 차단 사항이 아니다.

## 연구 제안에서 제품 결정으로 좁힌 항목

[DATA_API_SPEC.md](DATA_API_SPEC.md)가 최종 정본이다. 다음 변경은 관찰 사실이 아니라 구현 선택이다.

- 프로젝트 head 이름은 API `revision`으로 통일한다. 최초 저장소는 `.data`로 관리하여 미구현 native folder picker token에 의존하지 않는다.
- image upload는 원본 등록만 수행하고 처리는 명시적 job으로 나눈다. 백업/복원도 큰 파일 작업이므로 같은 실행기의 별도 operation으로 관리한다.
- 앱 FPS 범위1–60과 duration 정본을 명시했다. 기존 큐레이션 UI의1–30 범위와 다르므로 adapter 회귀로 소비자 간 일치를 검증한다.
- bake 이후 alpha0 RGB를0으로 통일해 최종 preview/atlas/PNG의 전체 decoded RGBA 일치를 검증한다. 원본 바이트에는 적용하지 않는다.
- outline 두께는 원본 셀의 정수 픽셀, opacity는 복제당 값으로 정의한다. 화면상1.65px 예시를 원본 픽셀 값으로 섞지 않는다.
- 단일 사용자의 SQLite 큐와 worker부터 구현한다. 불필요한 원격 큐/서버/계정 시스템은 첫 MVP에 넣지 않는다.

## 미확인과 처리 방법

| 미확인 | 구현 영향 / 처리 |
| --- | --- |
| 원작 내부 에디터 UI·분리 알고리즘·모든 offset | 공개 규칙 기반 새 설계. 원작과 동일하다고 주장하지 않음 |
| 실제 provider 생성·부분 생성·취소 기능 | capability와 실제 실행을 분리. 기존 허용 경로에서 테스트하고 미지원은 명시 |
| 실제 raw 체크무늬/복잡 배경 제거 품질 | 자동 성공 가정 금지. alpha 검사, 수동 보정, 재생성 경로와 실제 품질 검수 |
| 새 앱 브라우저 완주·worker 복구 | 앱 구현 단계 수용 테스트로 확인. 연구19개 결과를 대체 증거로 쓰지 않음 |
| 목표 게임 엔진별 loader 세부 | MVP 독립 manifest 뷰어로 최소 계약 검증, 필요시 Phaser/Unity/Flame adapter는 후속 |
| 공개 거너 이미지 재배포 권한 | 연구 증거로 보존, 기본 배포 소재는 자체/사용 허가 이미지로 구성 |

검증된 기존 엔진 능력과 새 앱 요구의 간극을 숨기지 않는다. 미확인 중 일반 구현 판단은 자율 처리하고, 계정 접근처럼 실제 사용자 입력이 필요한 지점만 구체적으로 보고한다.
