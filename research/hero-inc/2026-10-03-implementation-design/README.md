# 캐릭터 스프라이트 웹앱 후속 조사·구현 설계

2026-10-03 UTC · 조사/역분석/설계 완료 · **앱 구현·원격 포크 생성·배포 미수행**

기존 문서를 덮어쓰지 않고 새 폴더에 공개 원본 대조, 코드 감사, 실제 PNG 실험, 구현 계약을 모았다. 기존 README·연구·구현명세·작업지시문 4개는 [해시 대조](sources/preservation.json)에서 변경 없음을 확인했다.

## 중요한 발견

1. **공통 배율과 발점이 필수다.** 공개 거너의 대기377×471, 웅크림329×320은 둘 다1배·바닥494다. 실제 파일로 확인했다. 같은 자산에 `slice-sheet`를 적용하면 웅크림은320→471px(1.471875배), 수평 조준은378→471px로 커지고 발의 가로 기준도 바뀐다. 애니메이션 기본 경로에서 제외해야 한다.
2. **성공 종료만으로 잘림을 판정할 수 없다.** 합성650px 무기 fixture는512px 셀에서2,070개 알파 픽셀을 잃고도 성공했다. 별도 셀 초과 검사가 필요하다. 실제 거너가 같은 잘림을 겪었다는 주장은 아니다.
3. **Python 큐레이션과 출력은 재사용할 가치가 있다.** 실제 PNG 가져오기→큐레이션 저장·순서·복제·이동·픽셀 편집→atlas/PNG/Aseprite 호환 출력이 작동했다. 소스 SHA는 불변이었다. 다만 최종 PNG는 선택·호흡 효과 차이를 피하도록 같은 baked atlas에서 추출하는 설계를 권한다.
4. **현재 기능과 신규 계약을 나눠야 한다.** 기준 파일 편집은 working base를 바꾸므로 별도 immutable 원본이 필요하다. 임의 duration 배열은 현재 composer가 읽지 않는다. 빈 선택은 전체로 해석될 수 있고, 저장 실패 뒤 다운로드가 진행될 가능성도 코드에서 확인했다.
5. **기준 엔진을 확인했다.** 설치본2.12.1의360개 파일이 공개 commit `b058341f7543f3adcbea227bd4e6b7587895b1bc`와 일치한다. Apache-2.0 LICENSE/NOTICE 포함. 원격 main은 이미2.18.0이므로 본 결과를 최신 main 검증으로 읽으면 안 된다.
6. **제품 구조는 React+Vite + Python API/worker를 추천한다.** 업로드·참조 승인·동작 설정·작업관리·정렬을 새 UI로 만들고 기존 큐레이션/bake를 연결한다. 사용자가 명령어나 JSON을 편집하는 단계가 남으면 완주가 아니다.

## 문서와 증거

| 읽을 파일 | 내용 |
|---|---|
| [sources.md](sources.md) | URL·페이지 위치·영상 시간·관찰/추론/미확인, 접근 경위 |
| [research-analysis.md](research-analysis.md) | 참조 분리·8포즈/6동작·체고·발·배율·아웃라인 근거별 분석 |
| [engine-audit.md](engine-audit.md), [baseline.json](baseline.json) | 라이선스·commit·로컬 변경·환경·provider 준비상태와 함수/줄 근거 |
| [validation.md](validation.md) | 실제/합성 이미지 구분, 수치·실행 경로·테스트 한계 |
| [시각 비교](artifacts/validation-comparison.html) | 실제 공통 배율 이미지와 slice-sheet 결과. 연구용 비교물 |
| [19개 관찰 검사](artifacts/local-validation-run-v2/results.json) | 위험 재현을 포함한 로컬 실험 원시 결과 |
| [ui-flow.md](ui-flow.md) | 프로젝트부터 출력까지 화면 흐름·각 화면 필드/행동 |
| [cli-api-matrix.md](cli-api-matrix.md) | 단계별 현재 CLI/함수·입출력·신규 API·진행/실패/취소/재시도 |
| [architecture.md](architecture.md) | Vite/Next 비교, Python 긴 작업, 전용 fork 구조·취소/복구 |
| [data-contract.md](data-contract.md) | API 정본, 안정ID·원본·generation·occurrence·timing·저장·출력 계약 |
| [project.example.json](project.example.json) | 실제 측정 자산을 참조하는 **미승인 설계 예시**, 제품 저장 파일 아님 |
| [acceptance-plan.md](acceptance-plan.md) | 우선순위 구현 계획과34개 수용 테스트. 현재 전부NOT_RUN |
| [재현 스크립트](tests/validate_local_engine.py) | 생성 호출 없이 같은 로컬 실험을 다시 실행 |
| [산출물 점검](artifacts/deliverable-check.json) | 상대 링크·JSON·실험 개수·수용 상태·원본/예시 해시 검사 |

신규 API/상태/필드의 정본은 `data-contract.md`, 제품 폴더 구조는 `architecture.md`다. 엔진 실제 동작은 `engine-audit.md`와 고정 commit 코드가 근거다. 앞선 문서의 개념적 `request.json` 대신 실제 엔진 파일명은 `sprite-request.json`, 추출 메타는 `frames/frames-manifest.json`을 사용한다.

## 수행한 검증과 경계

- 브라우저에서 제작 노트와 인터랙션, 두 Threads 답글의 상위 맥락, YouTube 채널/영상의07:57 화면을 관찰했다. 한국어 자동자막을 새로 받아 기존 VTT와 대조했다. 제작 노트·Threads 프로필·영상 채널·저장소 탭을 따로 유지했다.
- 실제 공개 정렬 WebP를 디코딩 픽셀 그대로 PNG에 저장하고 bbox·alpha·발점을 측정했다. 이 PNG로 import/curation/compose/export를 실행했다.
- 실제 자산을 초록 배경에 재조합한 sheet로 정규화 부작용을 시험했다. 긴 무기·발 아래 장비 실패는 별도의 합성 fixture다.
- 로컬 관찰 검사는19/19가 기대와 일치했다. 위험 동작을 재현한 경우도 성공한 관찰에 포함되며 **앱 수용19개 통과가 아니다**.
- 실행 환경·소스/해시·무호출 provider 인증준비를 확인했다. Codex login-ready는 실제 이미지 생성 성공이나 남은 quota 확인이 아니다.

**미수행:** 실제 provider 생성/부분 재생성/과금, 실제 raw 체크무늬 제거와 canonical extract 전체 품질, 새 웹 UI 완주, 브라우저 preview와 export 비교, 취소/강제종료 복구, 팀 아웃라인 bake, 목표 게임엔진 로더 검증. mock provider도 이번에는 구현하지 않았다. 연구 스크립트·시각 비교·계약 예시는 앱 구현물이 아니다.

## 남은 확인과 구현 차단 사항

| 항목 | 현 상태 | 다음 해결 |
|---|---|---|
| 원작 내부 에디터·분리 함수·전체 motion offset | 미공개/미확인 | 공개 규칙 기반으로 자체 구현하고 원작 재현이라고 과장하지 않음 |
| 원격main2.18.0과 설치본 차이 | HEAD/version만 확인 | 첫 회귀 fixture 구축 후 별도 diff/업그레이드 결정 |
| 실제 provider 결과와 취소·중복 접수 처리 | 호출 금지 범위로 미검증 | 후속 구현의 별도 실제연동 gate. mock 성공으로 대체 금지 |
| 원본 체크무늬·복잡 배경 제거 | 원본이 불투명한 것까지 확인 | cutout 지원 범위 UI와 수동 mask/재생성 경로 구현, 실제 품질시험 |
| 몸 체고·발의 의미 판정 | bbox/휴리스틱만 측정 | 사람의 landmark 승인과 미확인 상태 유지 |
| 가변 duration·빈 timeline·출력 동등성 | 현 엔진 한계 확인 | 포크/adapter 수정 후34개 수용시험 중 관련 항목 실행 |
| `img2webp` | 실행파일 없음 | 후순위 영상 WebP 기능을 켤 때 별도 준비; 이미지 MVP 차단 아님 |

PXF/effect_editer, 공용 엔진, 기존 연구 문서는 수정하지 않았다. 공개 배포·메시지 발송·유료 생성 호출도 하지 않았다.
