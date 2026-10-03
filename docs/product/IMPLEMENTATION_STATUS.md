# 구현·검증 현황

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

실행 API schema는 `packages/contracts/openapi.json`, 구체 계약은 `packages/contracts/IMPLEMENTATION.md`. Codex 품질/해상도 지정·외부 취소/조회는 미지원이며 유료 fallback은 활성화하지 않는다. 공용 스킬·연구 자료·다른 프로젝트는 보존했고 commit/push/PR/merge/배포는 하지 않았다.


## 2026-10-03 후속: 제작 이력·승인·다음 작업

실제 추출 실행별 후보 묶음과 출처·사용처 이동, 수동 승인/자동 검사/변경 후 재확인 상태, 선택 동작의 다음 작업 안내를 추가했다. 웹 96개·Python 통합 209개 PASS, TypeScript/Vite 빌드 및 ego 복제본 저장·재승인·출력 여정을 확인했다. 원본 예제 v37과 14개 에셋은 보존했다. 상세 범위와 증거는 [WORKFLOW_REVIEW.md](WORKFLOW_REVIEW.md)를 참조한다.

설명서의 작업 공간·승인 본문과 화면을 갱신했다. 새 화면은 ego 화면 스타일 PDF의 렌더 결과이며 스크린샷 성공으로 표시하지 않는다. 기존 캡처·문서는 보존했다.
