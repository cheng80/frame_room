# 제품 수용 테스트와 추적성

작성일: 2026-10-03 KST · 최종 MVP 수용 계약 · **TEST-01–TEST-34 전부 `NOT_RUN`**.

## 1. 검증 범위와 완료 의미

[사용자 합의](../planning/USER_DECISIONS.md), 연구의 [README](../../research/hero-inc/2026-10-03-implementation-design/README.md), [ui-flow](../../research/hero-inc/2026-10-03-implementation-design/ui-flow.md), [data-contract](../../research/hero-inc/2026-10-03-implementation-design/data-contract.md), [acceptance-plan](../../research/hero-inc/2026-10-03-implementation-design/acceptance-plan.md), [validation](../../research/hero-inc/2026-10-03-implementation-design/validation.md)를 통합했다. 화면 동작과 gate는 [UX_DESIGN.md](UX_DESIGN.md)를 따른다. 최신 데이터/API·수치 범위는 [DATA_API_SPEC.md](DATA_API_SPEC.md)가 정본이며 연구 제안보다 우선한다.

기준 환경은 React + Vite + TypeScript, FastAPI, SQLite, 로컬 독립 Python worker다. 엔진은 프로젝트 전용 포크 **v2.12.1 / `b058341f7543f3adcbea227bd4e6b7587895b1bc`**로 고정하고 포크 patch revision도 실행 보고서에 남긴다. 공용 `/Users/cheng80/.codex/skills/sprite-gen`은 제품 실행·쓰기 대상이 아니다. `LICENSE`·`NOTICE`를 유지한다.

연구의 19개 관찰 pass에는 자세별 확대, 성공 종료 뒤 잘림, 발 후보 오판을 **재현한 성공**이 포함된다. 앱·provider·복구·브라우저 완주 19개가 통과했다는 뜻이 아니다. 연구 결과는 fixture 기대값과 위험 회귀의 근거로만 사용한다. 이 문서 작성 중 앱 수용 시험, 실제 provider 호출, 유료 생성, 앱 코드 변경은 수행하지 않았다.

기존 34개 ID와 P0/P1 우선순위를 유지한다. P0 23개는 기존 이미지 편집·출력의 필수 기준, P1 11개는 실제 생성과 전체 UI의 필수 기준이다. 둘 다 최종 MVP에 포함한다. FPS+hold는 초기 중간 단계만 허용하고 **가변 duration 저장·재생·최종 출력이 없는 상태는 P0 최종 완료가 아니다**. 테스트의 하위 시나리오를 일부 통과해도 해당 ID 전체를 PASS로 올리지 않는다.

이번 확정 사항은 애니메이션의 per-pose normalization 금지, fit 전 raw 보존, manual anchors, immutable originals, 저장 revision ACK, 빈 timeline 출력 차단, native alpha, no paid fallback이다. 연구의 선택적 입상별 키 맞추기/거너 독립 fit는 이번 MVP에서 disabled로 결정했다. TEST-11/13은 해당 비활성 이유와 공통 배율 정책을 검사한다. 최종 픽셀 oracle은 TEST-22의 전체 RGBA 동일성으로 고정한다.

PXF/effect_editer, 영상, 보간, 자동 다방향 생성, 협업, 공개 배포는 수용 범위 밖이다. 이를 위한 미설치 도구를 이미지 MVP 실패로 처리하지 않는다.

## 2. REQUIREMENT → test 추적성

각 ID의 전체 시나리오는 아래 본표와 6절의 보강 시나리오를 함께 의미한다. TEST-34는 전 요구의 UI 통합 경로이며 개별 시험을 대신하지 않는다.

| 요구 ID | 고정 요구명 | 수용 테스트 |
| --- | --- | --- |
| R01 | 프로젝트·로컬 실행 | TEST-02, TEST-05, TEST-18, TEST-28, TEST-34 |
| R02 | 참조·승인 기준 | TEST-03, TEST-04, TEST-29, TEST-33, TEST-34 |
| R03 | 생성 설정·실제 provider 연동 | TEST-03, TEST-06, TEST-24, TEST-30, TEST-31, TEST-34 |
| R04 | 작업 상태·취소·재시도·복구 | TEST-24, TEST-25, TEST-26, TEST-27, TEST-28, TEST-29, TEST-30, TEST-31, TEST-34 |
| R05 | 가져오기·배경 제거·추출 | TEST-01, TEST-05, TEST-06, TEST-07, TEST-08, TEST-11, TEST-12, TEST-16, TEST-30, TEST-34 |
| R06 | 공통 배율·발 정렬 | TEST-09, TEST-10, TEST-11, TEST-12, TEST-13, TEST-14, TEST-15, TEST-16, TEST-29, TEST-34 |
| R07 | 후보·동작·비파괴 편집 | TEST-01, TEST-04, TEST-08, TEST-17, TEST-18, TEST-29, TEST-34 |
| R08 | 재생·검수·가변 시간 | TEST-07, TEST-14, TEST-18, TEST-20, TEST-21, TEST-22, TEST-33, TEST-34 |
| R09 | 팀 아웃라인 | TEST-22, TEST-32, TEST-34 |
| R10 | 최종 출력·독립 뷰어 | TEST-13, TEST-16, TEST-17, TEST-19, TEST-20, TEST-21, TEST-22, TEST-23, TEST-32, TEST-34 |
| R11 | 저장·이력·백업 | TEST-01, TEST-02, TEST-04, TEST-05, TEST-10, TEST-17, TEST-18, TEST-19, TEST-23, TEST-28, TEST-34 |
| R12 | 환경·원본·공용 엔진·입력 보호 | TEST-01, TEST-02, TEST-05, TEST-25, TEST-31, TEST-34 |

## 3. fixture provenance와 실행 종류

### 3.1 증거 종류

| 분류 | 실행에서 입증하는 것 | 입증하지 못하는 것 |
| --- | --- | --- |
| `REAL_ASSET` | 실제 공개/사용자 이미지의 로컬 처리·정렬·저장·출력 | 현재 provider 인증·생성 성공 |
| `SYNTHETIC` | 수학적으로 정답을 아는 형상·알파·좌표·경계·손상 입력의 회귀 | 실제 캐릭터 외형과 배경 제거 품질 |
| `MOCK_PROVIDER` | 제어된 작업 상태·실패·취소·응답 유실·중복 접수 로직 | 외부 접수·취소·quota·실제 생성 품질 |
| `REAL_PROVIDER` | 허용된 실제 연결에서 요청·응답·원본 결과를 확보한 호출 | 다른 provider의 capability 또는 보편적인 생성 품질 |

실제 이미지를 입력한 mock 작업은 `REAL_ASSET + MOCK_PROVIDER`로 표기한다. 저장된 샘플 복사나 응답 재생은 `MOCK_PROVIDER`이며 실제 호출로 승격하지 않는다. 실제 파일 처리와 실제 provider 연동을 별도 집계한다. 실제 작업이 성공해도 자동으로 외형 검수 PASS가 되지 않는다.

### 3.2 보존된 연구 입력과 후속 제작 입력

아래 경로의 `연구/`는 `research/hero-inc/2026-10-03-implementation-design/`를 뜻한다. 공개 자산의 원본 URL·SHA-256·bytes·변환 이력은 [provenance.json](../../research/hero-inc/2026-10-03-implementation-design/artifacts/source-assets/provenance.json)이 정본이다. 실행 전 해당 파일의 bytes hash를 다시 확인해 보고서에 복사한다. 공개 접근 가능 여부를 재배포 허가로 해석하지 않으며 연구 자산을 제품 기본 에셋에 자동 포함하지 않는다.

| fixture ID | 분류·확보 상태 | 정확한 입력·기대값·제약 |
| --- | --- | --- |
| REAL-GUNNER-0 | REAL_ASSET · 보존됨 | `연구/artifacts/source-assets/pose-0-aligned.webp`, `pose-0-aligned.png`. PNG는 WebP decoded RGBA를 무손실 저장한 파생본. bbox `[128,23,505,494)`, 377×471, alpha>=16 픽셀 53,630, 발 밴드 x=256 |
| REAL-GUNNER-1 | REAL_ASSET · 보존됨 | 같은 폴더 `pose-1-aligned.webp/.png`. bbox `[148,116,486,494)`, 338×378, 45,197픽셀, 발 밴드 x=256 |
| REAL-GUNNER-3 | REAL_ASSET · 보존됨 | 같은 폴더 `pose-3-aligned.webp/.png`. bbox `[113,174,442,494)`, 329×320, 40,920픽셀, 발 밴드 x=256.5. ratio 320/471 |
| REAL-GUNNER-RAW | REAL_ASSET · 보존됨 / 제거 품질 미검증 | 같은 폴더 `pose-{0,1,3}-raw.webp/.png`, 384×512, 불투명 배경. aligned 자산으로 대체해서 raw 배경 제거를 통과시키지 않음 |
| REAL-GUNNER-SHEET | REAL_ASSET · 보존됨 | 같은 폴더 `gunner-keyposes.png`, 1536×1024, 모든 alpha=255인 체크무늬 시트. 추출·배경 제거 별도 필요 |
| REAL-GUNNER-SINGLE | REAL_ASSET · 보존됨 | 같은 폴더 `gunner.png`, 512×512, 실제 alpha 0/255. 이미 처리된 입력 |
| REAL-GUNNER-MONTAGE | 실제 이미지의 테스트 재구성 · 보존됨 | `연구/artifacts/local-validation-run-v2/real-assets-green-montage.png`. 실제 공개 포즈를 초록 배경에 배치한 파생 시트. 원작의 원본 생성 시트 아님 |
| REAL-REFERENCES | REAL_ASSET · 후속 준비 | 외형/스타일이 구별되는 실제 참조 2장. TEST-03 전 사용자 제공 또는 사용 가능한 출처·hash·역할을 등록. 확보 전 PASS 금지 |
| SYN-GEOMETRY | SYNTHETIC · 후속 제작 | 서기 471px·웅크림 320px, 몸/머리·경계 marker, alpha=16, 양·음수 및 .5 반올림 사례. generator version·seed·정답 mask 보존 |
| SYN-WEAPON | SYNTHETIC · 일부 보존 / 나머지 후속 제작 | 기존 `연구/artifacts/local-validation-run-v2/synthetic-overflow-green.png`는 650px 무기 반례. 분리 총구·격자 경계 sentinel은 별도 제작. 실제 거너의 2,070px 유실로 오인 금지 |
| SYN-ALPHA | SYNTHETIC · 후속 제작 | 불투명 체크무늬, 실제 투명, alpha=1/15/16/255, 반투명 RGB, 1px 잔여, 빈 알파, alpha=0 숨은 RGB. 예상 배열을 생성 코드와 독립적으로 명시 |
| SYN-ANCHOR | SYNTHETIC · 일부 보존 / 나머지 후속 제작 | 기존 `연구/artifacts/local-validation-run-v2/synthetic-prop-below-feet.png`: 수동 정답 (250,451), 잘못된 후보 (341.5,497). 망토·다중 접지·공중·root trajectory는 추가 제작 |
| STATE-FAULTS | SYNTHETIC · 후속 제작 | 정상 fixture의 격리된 사본에 손상 PNG, 누락 hash, 상위 schema, 충돌 revision, 저장 중단, archive 경로 탈출, 악성 문자열을 적용. 원본/연구를 손상시키지 않음 |
| MOCK-JOBS | MOCK_PROVIDER · 미구현/후속 제작 | 성공, 부분 실패, 늦은 응답, 응답 유실, 취소 불가, 조회 미지원, 강제 종료, 동일 key 접수 카운터를 제어하는 adapter. seed·요청 ledger·실제 호출 0을 기록 |
| REAL-PROVIDER | REAL_PROVIDER · 미실행 | 실제 job/request ID, 요청 시각, provider/model/capability, 승인 참조 ID/hash, 비밀값 제거한 요청/응답, 원본 결과 bytes/hash, 비용 확인 범위를 보존 |

WebP→PNG 변환은 decoded RGBA 보존을 뜻하며 WebP 이전 원본 색 복원이나 배경 제거 성공을 뜻하지 않는다. 실제 fixture의 몸 체고·총구·발·외형 정답은 별도 사람의 landmark/영역 승인과 함께 보존한다. 연구의 alpha bbox 471/320을 해부학적 몸 체고 정답으로 대체하지 않는다.

### 3.3 provenance 필수 필드

각 입력에 `fixtureId`, `kind`, `sourceUri`, `acquiredAt`, `originalSha256`, `decodedFingerprint`, `derivation`, `generatorVersion/seed`(합성일 때), `approvedLandmarks`, `rightsNote`를 기록한다. 파생 입력은 부모 hash와 변환 인자·도구 버전을 남긴다. hash 불일치는 먼저 fixture 실패로 기록하고 테스트가 최신 파일로 기대값을 자동 갱신하지 않게 한다.

## 4. 공통 oracle·실행 전제

1. **좌표:** 왼쪽 위 0, bbox 오른쪽/아래 exclusive. `bottom=494`는 마지막 픽셀 y=493·512 셀의 바닥 여백 18이다. 512/18/2는 거너 프리셋이다.
2. **알파:** 형상 support·잘림 검사는 `alpha>0`; 자동 발 후보는 기본 `alpha>=16`. alpha=1/15 픽셀 유실을 발 임계값으로 숨기지 않는다. true native alpha는 파일 확장자가 아니라 채널 통계로 판정한다.
3. **배율:** 동일 정렬 그룹은 정확히 같은 `sharedScale`. `s=1` 정수 이동에서 높이 471/320 정확 보존, ratio `320/471≈0.6794055`. 소수 s에서 각 높이 `abs(outputHeight-sourceHeight*s)<=1px`. alpha 픽셀 수 보존은 s=1 무손실 이동에만 요구하고 소수 축소에 그대로 적용하지 않는다.
4. **앵커:** raw/crop/canvas 좌표계를 명시한다. round는 양·음수 모두 `floor(v+0.5)`, 자동 밴드 높이는 `max(4,floor(h*0.12+0.5))`. 저장된 소수 anchor·authored offset은 정확 복원하고 raster 접지 오차는 ≤1px. 공중 프레임의 의도된 높이는 오차가 아니다.
5. **raw 보존:** normalize/fit 이전 crop·mask·sourceRect·sourceToFrameTransform·해시를 확보한다. 이미 확대된 웅크림을 발만 맞춰 복구했다고 판정하지 않는다. per-pose normalization과 숨은 단일 프레임 축소는 0건이다.
6. **시간:** 명시적 정수 duration1–60000ms가 기본 FPS보다 우선. 기본값은 `floor(1000/fps+0.5)`ms이고 유효 FPS는1–60이다. 최종 manifest에 누락 시간 없음. `[80,120,200]`의 누적 경계는 `[80,200,400]`. 제어 clock에서는 정확히 일치, 실제 화면에서는 refresh 1회 이내. catch-up 재생은 누적 시간 기준이며 callback 지연을 영구 누적하지 않는다.
7. **픽셀:** 원본 불변은 파일 bytes SHA-256, 출력 parity는 전체 decoded RGBA 배열로 비교한다. PNG 압축 bytes가 같아야 한다는 요구는 아니다. 브라우저 screenshot·색 보정 화면을 원본 bitmap oracle로 쓰지 않는다. 최종 bitmap에서 alpha=0 RGB 정규화를 완료한 뒤 동일 atlas에서 PNG를 추출한다.
8. **revision:** 저장 ACK 없이 bake/새 export 시작 0건. artifact·manifest·QA는 같은 잠긴 revision/recipe. 저장 실패나 충돌에서 기존 정상 export를 열 수는 있지만 이를 최신 결과로 표시하지 않는다.
9. **UI와 API:** 빈 timeline·누락 원본·미승인 anchor·overflow·지원하지 않는 timing·저장 충돌의 gate를 양쪽에서 검사한다. 직접 API로 UI 제한을 우회해도 성공하면 안 된다.
10. **독립성:** 새 임시 프로젝트와 지정 출력 폴더에서 실행한다. 연구·사용자 원본·공용 엔진·다른 프로젝트를 변경하지 않는다. 공용 엔진의 설치 경로가 없어도 앱은 프로젝트 전용 환경으로 동작해야 한다.

최초 실행 때 앱/포크 commit 또는 source fingerprint, dependency locks, Python·이미지 라이브러리·브라우저·OS·DPR, fixture hashes를 기록한다. 이 문서의 수치/필수 동작은 구현 목표이며 이미 동작한다는 주장이 아니다.

## 5. 기존 34개 수용 기준의 최종 제품 매핑

본표의 상태는 작성 시점 값이다. 구현 후 실행 결과는 별도 실행 보고서에 남기고 근거가 있을 때만 갱신한다. 6절 하위 시나리오도 각 부모 TEST의 현재 `NOT_RUN`을 상속한다.

### 5.1 원본·기준 승인·프로젝트

| ID / 우선순위 | 요구 ID | fixture | UI 작업 | 합격 기준 | 현재 상태 |
| --- | --- | --- | --- | --- | --- |
| TEST-01 / P0 | R05, R07, R11, R12 | REAL-GUNNER-RAW, REAL-GUNNER-SHEET | 업로드→배경 제거→편집→후보 삭제→저장→출력→재열기 | 업로드 시와 마지막 원본 SHA-256 일치 `100%`. 원본 path를 파생 파일 출력 대상으로 사용할 수 없음. 삭제한 후보의 원본은 보존되고 참조 해제만 기록 | NOT_RUN |
| TEST-02 / P0 | R01, R11, R12 | 같은 이름의 서로 다른 PNG, 동일 PNG 중복 | 같은 이름 업로드·중복 업로드·프로젝트 복제 | 서로 다른 content hash는 덮어쓰지 않음. 같은 content hash를 공유하더라도 asset ID/사용 관계를 복원. 공용 엔진·다른 프로젝트 파일 변경 `0`건 | NOT_RUN |
| TEST-03 / P0 | R02, R03 | 외형과 스타일이 다른 실제 참조 2장 | 외형/스타일을 별도 등록, 얼굴·의상·무기·몸 비율·방향을 고정하고 승인 | 두 역할·원본 hash·approval revision이 명시적으로 저장. 생성 요청과 후보에서 해당 승인 버전을 확인. 스타일 교체가 외형 기준을 자동 교체하지 않음 | NOT_RUN |
| TEST-04 / P0 | R02, R07, R11 | 승인 revision A/B와 후보 | A 승인→후보 검수→기준 변경 B→저장·복원 | B 승인 전 생성 불가 또는 A 유지 여부를 명시. A 기반 후보에 이전 기준 배지. 기존 승인 상태를 B 검수 완료로 자동 승격하는 항목 `0`건 | NOT_RUN |
| TEST-05 / P0 | R01, R05, R11, R12 | 손상 PNG, 누락 asset, 잘못된/상위 버전 상태 파일 | 가져오기·프로젝트 재열기 | 실패 asset/단계와 복구 동작 표시. 이전 성공 snapshot 및 원본 hash 보존. 알 수 없는 schema를 조용히 재저장해 필드를 삭제하는 사례 `0`건 | NOT_RUN |

### 5.2 알파·추출·공통 배율·앵커

| ID / 우선순위 | 요구 ID | fixture | UI 작업 | 합격 기준 | 현재 상태 |
| --- | --- | --- | --- | --- | --- |
| TEST-06 / P0 | R03, R05 | REAL-GUNNER-SHEET, REAL-GUNNER-SINGLE, SYN-ALPHA | 가져오기 후 원본/알파/합성 배경 보기 | 불투명 체크무늬는 `실제 투명 아님`으로 표시. `alpha<255` 픽셀 수가 0인 입력을 투명 완료로 표시하지 않음. 진짜 알파 자산은 수치가 일치 | NOT_RUN |
| TEST-07 / P0 | R05, R08 | SYN-ALPHA 및 실제 배경 제거 결과 | 배경 제거→검정·흰색·마젠타·체크 배경 비교 | 합성 fixture의 알려진 배경 위치 `alpha=0`, 보존 대상 RGB/알파는 기준값 일치. 실제 이미지의 halo·잔여물·장비 손실은 확대+실제 크기 수동 승인 전 `미검수`. 체크무늬를 아웃라인으로 숨겨 통과시키지 않음 | NOT_RUN |
| TEST-08 / P0 | R05, R07 | REAL-GUNNER-RAW, SYN-WEAPON | 연결 성분 추출→총구·떨어진 장비 병합/제외→되돌리기 | 선택한 성분의 유효 픽셀 합집합 보존. 미할당 성분 수와 마스크를 표시. 총구 sentinel 손실 `0`개. 자동 분리가 확정과 동일하게 표시되지 않음 | NOT_RUN |
| TEST-09 / P0 | R06 | REAL-GUNNER-0, REAL-GUNNER-3, SYN-GEOMETRY | 거너 512/18/2 프리셋, 공통 `s=1`, 발 정렬 | 실제 대기/웅크림 높이 `471/320`, ratio `0.679406` 보존. 목표 바닥 `494`, raster 오차 `≤1px`. 웅크림을 `471px`로 확대한 결과는 실패 | NOT_RUN |
| TEST-10 / P0 | R06, R11 | SYN-GEOMETRY 및 실제 포즈 3장 | `s=0.75`, `s=1`, `s=1.25` 적용·저장·복원 | 모든 포즈 저장 scale 정확히 동일. 각 높이 오차 `≤1px`. 머리/몸 표식이 같은 s로 변환. 재열기가 원본에 새 정규화를 추가 적용하지 않음 | NOT_RUN |
| TEST-11 / P0 | R05, R06 | 같은 셀의 서기/웅크림 시트 | fit 전 crop/변환 이력 확인→애니메이션 추출→입상별 키 맞추기 옵션 확인 | 애니메이션 경로의 셀별 높이 정규화 사용 `0`건. raw crop·sourceRect·sourceToFrameTransform과 원본 hash를 fit 전에 보존. 이번 MVP의 입상별 키 맞추기는 disabled이며 체형 영향과 이유 표시. 이미 정규화된 입력은 원본 lineage 없이 복구 완료로 표시하지 않음. 기존 slice-sheet 위험 재현 결과와 별도 판정 | NOT_RUN |
| TEST-12 / P0 | R05, R06 | SYN-WEAPON, 실제 무기 자세 | 격자를 넘는 무기와 몸/발 기준으로 추출·정렬 | 몸/발 앵커가 weapon bbox 중심 이동을 따라가지 않음. support 픽셀/총구 표식 보존. 격자 밖 무기를 자동 절단한 결과는 실패. 실제 자세는 원본/결과 비교 승인 필요 | NOT_RUN |
| TEST-13 / P0 | R06, R10 | SYN-WEAPON 중 셀 초과 입력 | 큰 셀 선택 또는 캐릭터 공통 축소→재출력 | 조치 전 frame ID와 네 변 초과량 표시. 셀 확대 또는 그룹 전체 축소 뒤 support가 경계 안에 있음. 포즈 하나만 몰래 축소 `0`건. 거너 호환 0.85 규칙을 제공하는 후속 모드라면 독립 보정값 표시·0.85 미만 오류가 필요하지만 이번 MVP에서는 해당 모드 disabled; 전역 임계값으로 적용하지 않음 | NOT_RUN |
| TEST-14 / P0 | R06, R08 | SYN-ANCHOR | 자동 발 추정→검토→수동 앵커·공중 설정 | 망토/무기/다중 접지 후보를 자동 확정하지 않고 `미확인` 유지 가능. 수동 좌표 정확히 저장. 공중 자세는 기준 앵커+의도된 높이 offset을 보존하고 바닥에 강제로 붙이지 않음 | NOT_RUN |
| TEST-15 / P0 | R06 | `alpha=15/16` 경계와 바닥 좌우 표식 | 자동 앵커 계산→수동 수정→reset | `>=16`과 아래 12%·최소 4px 규칙 결과를 알려진 oracle과 비교. alpha cutoff를 변경하면 후보 갱신과 검수 상태 변경. 자동 계산이 수동 앵커를 덮어쓴 횟수 `0` | NOT_RUN |
| TEST-16 / P0 | R05, R06, R10 | 완전 빈 알파, 몸과 장비가 서로 다른 배율의 입력 | 추출·자동 정렬·출력 시도 | 빈 결과는 유효 frame으로 승인/출력되지 않음. 체고 측정 불가를 `0`이나 정상값으로 저장하지 않음. 자동 판정이 어려운 체형은 수동 검수로 표시하며 알고리즘 보장이라고 보고하지 않음 | NOT_RUN |

### 5.3 큐레이션·저장·게임용 출력

| ID / 우선순위 | 요구 ID | fixture | UI 작업 | 합격 기준 | 현재 상태 |
| --- | --- | --- | --- | --- | --- |
| TEST-17 / P0 | R07, R10, R11 | 기존 큐레이션 fixture + 포즈 3장 | 후보 채택/숨김/복제/이동, `[A,B,A,C]` 순서, 개별 offset, undo/redo, 마지막 occurrence까지 제거 후 저장·재열기·출력 시도 | 순서와 중복 occurrence의 ID 보존. frame ID와 generation version은 인덱스 이동에 따라 바뀌지 않음. **빈 timeline은 빈 상태로 유지하고 출력 차단**; 엔진에 `selected=[]`를 내려 전체 후보를 자동 채택하는 fallback `0`건. 기존 `curation.json` 원본을 보존한 어댑터 변환; 지원하지 않는 필드는 누락시키지 않고 경고/차단 | NOT_RUN |
| TEST-18 / P0 | R01, R07, R08, R11 | TEST-17 저장 프로젝트 | 저장→앱/worker 종료→재열기→다른 위치에 복제해 열기 | 승인 기준, 후보·순서·offset·앵커·공통 scale·loop·duration·검수 상태·출력 옵션이 의미상 완전히 동일. 절대 임시 path 의존으로 누락된 asset `0`개 | NOT_RUN |
| TEST-19 / P0 | R10, R11 | 저장 도중 중단하는 fixture | 새 수정 저장 중 프로세스 종료→재시작 | 구 snapshot 또는 새 snapshot 중 하나만 읽힘. 부분 JSON/manifest를 정상 프로젝트로 열지 않음. 성공한 저장 revision 손실 `0`건, 복구 UI에서 마지막 확정 revision 표시 | NOT_RUN |
| TEST-20 / P0 | R08, R10 | 반복 대기/단발 공격 각 3프레임 | FPS와 개별 지속 시간 설정, 저장·출력·재로드 | 예: 기본 `fps=10`, 개별 `[80,120,200]ms`, 총 `400ms`, loop 여부 정확히 보존. 우선순위는 명시적 duration→없으면 `1000/fps`. 가변 지속 시간 미지원 출력 형식은 경고/차단하며 조용히 균등화하지 않음. 균등 FPS+hold 중간 단계만으로 이 시험을 PASS 처리하지 않음 | NOT_RUN |
| TEST-21 / P0 | R08, R10 | TEST-20 출력 | 독립 뷰어에서 저장 파일만으로 재생 | 제어 clock에서 frame 전환 `80/200/400ms`; 단발은 마지막 프레임 유지, 반복은 `400ms`에 처음으로 복귀. 실제 화면은 refresh 1회 이내 오차. 순서/offset/loop는 편집 세션 상태 없이 재현 | NOT_RUN |
| TEST-22 / P0 | R08, R09, R10 | 알파·정렬·순서·아웃라인 적용 프로젝트 | 검수한 revision에서 최종 승인 미리보기와 PNG/atlas 출력 | 동일 immutable bake와 baked bitmap을 최종 승인 preview·PNG·atlas의 단일 입력으로 사용. preview가 읽은 소스 bitmap 대 개별 PNG, atlas rect 대 개별 PNG의 **전체 decoded RGBA 차이 `0`픽셀**. 숨은 RGB 정규화는 공통 bitmap 확정 전에 한 번만 수행. frame ID/version/occurrence/order/duration/anchor 일치. 연구의 visible RGBA 비교로 대체 금지 | NOT_RUN |
| TEST-23 / P0 | R10, R11 | TEST-22와 출력 중 새 편집 | 출력→동시에 후보 순서 수정→이전 출력 열기 | 출력 manifest에 잠근 project revision/bake hash/엔진 버전 존재. 서로 다른 revision 혼합 `0`건. 결과 path는 `exports/<exportId>/…`와 같은 독립 묶음으로 UI에 표시; 중간 `frames/`가 최종 출력으로 오인되지 않음 | NOT_RUN |

### 5.4 생성·실패·취소·복구

| ID / 우선순위 | 요구 ID | fixture | UI 작업 | 합격 기준 | 현재 상태 |
| --- | --- | --- | --- | --- | --- |
| TEST-24 / P1 | R03, R04 | MOCK-JOBS | 생성 설정→실행→단계별 진행 보기 | 기준 approval revision, provider, 동작, frame 수, 요청 hash, job ID를 추적. 대기/실행/완료/실패/취소 대기를 구분. provider가 진행률을 주지 않으면 가짜 % 없이 현재 단계 표시. mock 배지가 결과·이력·보고서에 유지 | NOT_RUN |
| TEST-25 / P1 | R04, R12 | 일부 단계 성공 후 실패하는 mock | 생성 성공→배경 제거 실패→실패 단계 재시도 | 성공한 생성 결과 hash 불변. 새 생성 호출 수 `0`; 재시도는 해당 파생 단계만 수행. 원인·실패 단계·재시도 가능 여부 표시. 허용되지 않은 작업 인자를 shell 코드로 실행하지 않음 | NOT_RUN |
| TEST-26 / P1 | R04 | 지연/취소 불가 mock | 생성 중 취소→worker 재시작→늦은 결과 수신 | `취소 요청`과 `upstream 취소 확인`을 구분. 늦은 결과는 이력에 보존하되 자동 채택하지 않음. 원본과 기존 승인 후보 손실 `0`. 외부 처리·요금이 멈췄는지 미확인이면 취소 성공/환불 완료라고 표시하지 않음 | NOT_RUN |
| TEST-27 / P1 | R04 | 더블 클릭, 응답 유실 mock | 같은 논리 요청 2회 실행→연결 끊김→재시도 | 같은 idempotency key의 로컬 제출 `1`회. 외부 요청 접수 여부 불명일 때 자동 재전송 `0`. provider job ID 조회/재연결로 먼저 확인. provider가 idempotency/조회 미지원이면 상태 `미확인`으로 남기고 새 호출을 분리 | NOT_RUN |
| TEST-28 / P1 | R01, R04, R11 | 실행 중 프로젝트, 재시작 mock | 앱 또는 worker 강제 종료→재열기 | 저장된 ledger로 job 식별. 로컬 단계는 확정 artifact 존재 시 이어가기 가능. 이미 성공한 유료 생성 단계 재실행 `0`. 상태 복구가 불가능하면 원인·수동 확인 경로 표시 | NOT_RUN |
| TEST-29 / P1 | R02, R04, R06, R07 | 승인된 A/B/C 중 B만 재생성 | B 선택→새 generation version 생성→비교→승인/되돌리기 | A/C hash·승인·앵커·offset 불변. B의 논리 frame ID는 유지하고 generation version 증가; B 이전 버전 보존. 새 B 승인 전 미채택. 이전 B 앵커를 검수 없이 새 B에 확정 적용하지 않음 | NOT_RUN |
| TEST-30 / P1 | R03, R04, R05 | REAL-PROVIDER | provider 설정 확인→허용된 실제 생성 1건→후보 등록 | 실제 응답의 provider job/request ID·원본 output hash·사용한 참조/동작 설정 연결. 인증 확인만으로 완료 처리하지 않음. mock 배지 없음은 실제 성공 증거가 아니며 실제 artifact 확인 필수 | NOT_RUN |
| TEST-31 / P1 | R03, R04, R12 | MOCK-JOBS, 이후 REAL-PROVIDER | 설정 화면의 사용 불가 provider 선택·실패·재시도 | 미설정/인증 필요/사용 가능/실행 실패/접수 불명 상태를 구분. 실패 시 다른 유료 provider로 자동 전환 `0`건. 실제 상태 확인의 범위와 시각 표시, 로그·화면·출력에 비밀키 `0`건 | NOT_RUN |

### 5.5 완주·검수 기능

| ID / 우선순위 | 요구 ID | fixture | UI 작업 | 합격 기준 | 현재 상태 |
| --- | --- | --- | --- | --- | --- |
| TEST-32 / P1 | R09, R10 | 실제 캐릭터+알파 잔여 fixture | 아군/적군 아웃라인, 두께·불투명도·4/8방향, preview-only/bake 전환 | 원본 hash 불변. preview-only는 출력 RGBA 변경 `0`; bake는 TEST-22와 동일 픽셀. 아웃라인 사용 여부와 단위 저장. 끈 상태에서도 알파 잔여 경고/미검수 상태 유지 | NOT_RUN |
| TEST-33 / P1 | R02, R08 | REAL-GUNNER 포즈 | 1:1 실제 크기/확대, 이전·다음 겹침, 배경 변경, 키보드로 프레임 이동 | 얼굴·의상·무기·몸 비율·방향을 승인 기준과 나란히 확인할 수 있음. 사람이 고른 실패 frame ID가 저장·복원. 축소 미리보기만으로 원본 알파·잘림 승인을 대체하지 않음 | NOT_RUN |
| TEST-34 / P1 | R01, R02, R03, R04, R05, R06, R07, R08, R09, R10, R11, R12 | 새 프로젝트; 기존 PNG 경로와 REAL-PROVIDER 경로 각각 | 기준 이미지→기준 승인→동작·설정→생성/가져오기→배경 제거→추출→정렬→큐레이션→검수→출력 | 두 여정을 개별 기록. 사용자가 터미널 명령 또는 JSON을 편집해야 하는 단계 `0`개. 기존 PNG 경로 성공만으로 실제 생성 여정 성공 처리하지 않음. 실패·취소·재개도 UI에서 완료 | NOT_RUN |

## 6. 제품 명세를 완성하는 필수 하위 시나리오

아래는 테스트 수를 부풀리는 별도 ID가 아니라 기존 34개 기준의 상세 조건이다. 모두 미실행이며 부모 TEST의 `NOT_RUN`을 상속한다. 실제 provider가 필요한 분기는 모의 분기로 대체할 수 없다.

### 6.1 로컬 실행·입력·원본 보호 — TEST-01, 02, 05, 25, 31, 34

- TEST-02: 공용 설치본을 import하지 않는 독립 환경에서 UI/API/worker를 시작한다. 전용 엔진 baseline SHA와 patch SHA·LICENSE·NOTICE를 확인한다. 처리 전후 공용 엔진 및 연구의 파일 hash 변경 0건, 다른 프로젝트 쓰기 0건이다. 단순히 파일 수정 함수가 없다는 코드 확인만으로 대체하지 않는다.
- TEST-05: 업로드 batch의 한 파일이 검증 실패하면 해당 batch의 asset 등록0건이고 이전 batch는 보존되는지 확인한다. 서버 설정의 허용 크기 초과, 잘못된 MIME/확장자, 손상 이미지, 없는 asset, schema 상위 버전을 UI/API에서 각각 거절하고 기존 성공 snapshot을 유지한다. 복원 ZIP의 `../`, 절대 경로, symlink 탈출과 과도한 압축 해제 크기를 거절한다. 프로젝트 범위 밖 읽기/쓰기와 공개 bind·비허용 origin 접근도 차단한다. 실제 비밀값을 fixture로 사용하지 않는다.
- TEST-25: prompt·파일명·동작 이름의 shell 특수문자/옵션 유사 문자열을 데이터로 처리한다. 고정 operation/argv 외 명령 실행 0건, 프로젝트 밖 생성 파일 0건이다. provider 실패 재시도로 새 생성이 몰래 접수되지 않았는지 요청 카운터를 검사한다.
- TEST-31: credential이 필요한 연결은 서버의 연결 상태만 UI에 전달한다. 로그·진단·DB portable snapshot·백업·export를 검사해 시험용 secret 표식 노출 0건을 확인한다. 실패한 provider 대신 다른 유료 provider 호출 0건을 모의 호출 ledger로 확인하고 실제 연결 기록도 별도 대조한다.
- TEST-34: 제공된 로컬 실행 수단에서 프로젝트 생성·열기·서비스 상태·재시작이 가능해야 한다. runtime dependency 누락은 해결 안내를 보이고 provider 미연결은 PNG 경로를 차단하지 않는다. 사용자는 개별 CLI 명령이나 JSON 편집을 요구받지 않는다.

### 6.2 native alpha·배경 제거·raw 추출 — TEST-06, 07, 08, 11, 12, 30

- TEST-06: 실제 알파 입력은 기본 배경 제거를 건너뛰며 RGB/alpha를 보존한다. alpha=1/15/16/255를 구분한다. 불투명 체크무늬와 WebP 컨테이너를 이유로 투명 완료라고 표시한 건수 0건이다.
- TEST-07/08: REAL-GUNNER-RAW를 사용해 실제 배경 제거→추출→정렬→출력까지 수행한다. already-aligned 자산 실행을 raw 경로 성공으로 보고하지 않는다. 공개 raw의 복잡 배경을 자동 제거하기 어려우면 UI의 수동 mask 복구/삭제·성분 병합으로 수정하고 검수자가 잔여물·halo·총구·얼굴·발을 원본과 비교한다. 자동 성공률은 추정하지 않는다.
- TEST-08/12: 연결된 긴 무기, 떨어진 총구, 접촉한 두 포즈, 격자 경계 너머 sentinel을 모두 시험한다. 합치기/수동 영역 분리/제외/undo 뒤 선택된 support의 합집합이 의도대로 복원된다. 미할당 성분을 자동 폐기해 프레임 수만 맞추면 실패다.
- TEST-11: 기존 canonical extract 계열을 실제로 통과하는 경로도 시험한다. fit 전 raw artifact와 원본 좌표를 확인하고 프레임별 scale을 고정 값으로 몰래 바꾸지 않았는지 증명한다. 단순 PNG import 하나만 성공해서 모든 extract 경로를 통과시킨 것으로 처리하지 않는다.
- TEST-30: provider가 native alpha를 지원하면 capability와 실제 요청·응답 alpha 통계를 대조한다. 지원하지 않으면 옵션이 disabled인 이유와 배경 제거 경로를 검증한다. 투명 요청을 무시한 응답은 검수 필요로 보내며 성공 배지를 유지한 채 투명으로 판정하지 않는다.

### 6.3 수동 앵커·배율·검수의 유효 범위 — TEST-03, 04, 09–16, 29, 33

- TEST-03/09: 몸 체고 두 점은 별도 승인값이고 bbox 471/320과 구분한다. 원본 크기 유지 모드는 몸 체고 미측정 사실을 보존한다. 같은 크기로 그려졌는지 미확인인 생성 batch를 자동으로 한 정렬 그룹에 넣지 않는다.
- TEST-10: `s=1.25`에서 원래 셀에 들어가지 않는 경우 먼저 그룹 셀을 충분히 확대한다. 의도한 배율 시험을 overflow 자동 축소로 통과시키지 않는다. 추출 사본 재열기로 두 번 배율 적용 0건이다.
- TEST-13: alpha=1 support와 baked outline까지 네 변 초과량을 검사한다. 원본 초과를 offset clamp로 숨긴 정상 exit는 실패다. 셀 확대/그룹 축소 후 최종 support 경계와 총구 표식을 확인한다.
- TEST-14/15: 수동 앵커를 저장한 뒤 임계값/자동 추정을 바꿔도 수동 확정값을 덮어쓰지 않는다. reset은 명시 동작이고 검수 상태를 되돌린다. 앵커·band의 .5, 음수 좌표, crop 원점 이동, 다중 접지, 공중 root trajectory를 검사한다.
- TEST-04/29: reference 또는 frame hash가 바뀌면 관련 QA와 수동 anchor 승인을 무효화한다. 과거 좌표는 제안값으로만 표시한다. 새 B 채택/되돌리기가 A/C의 hash·승인·offset·anchor를 변경하지 않는다.
- TEST-16/33: 빈 알파, 측정 불가, 장비/몸이 다른 배율인 입력에는 근거와 미검수/차단을 표시한다. 자동 알고리즘이 의미를 판정했다고 주장하지 않는다. 사람이 실패로 고른 frame ID·이유·기준 revision을 다시 열어 확인한다.

### 6.4 저장 ACK·충돌·백업 — TEST-17, 18, 19, 23

- TEST-17: 마지막 occurrence 삭제→저장→재열기→직접 export API 요청을 수행한다. UI와 서버 모두 빈 상태를 유지하고 차단한다. engine `selected=[]`로 전체 후보가 살아나는 fallback 0건이다. 지원하지 않는 과거 curation 필드는 원본을 보존하고 경고/차단한다.
- TEST-18: 백업을 UI로 내려받아 다른 위치에 새 project ID로 복원한다. 참조·원본·생성 lineage·mapping·occurrence·시간·검수·테두리·고지·파일 hash가 일치하고 절대 임시 경로 의존이 없다. 비밀키는 포함되지 않는다. 누락 파일 재연결과 hash 불일치를 처리한다.
- TEST-19: 저장 전 파일 쓰기, 파일 rename 후 DB commit 전, commit 후 응답 전의 중단 지점을 각각 제어한다. 재시작 후 읽는 것은 구/새 확정 snapshot 중 하나이며 acknowledged revision 손실 0건이다. orphan은 정상 파일처럼 참조하지 않는다.
- TEST-19: 동일 revision을 연 두 창에서 서로 수정한다. 두 번째 PATCH는 `409`를 받고 초안과 서버 snapshot을 모두 보존한다. 비교→최신 revision에 다시 적용 또는 서버 버전 열기를 UI에서 해결한다. silent last-write-wins 0건이다.
- TEST-19/23: 저장 HTTP 실패, 지연 ACK, engine revision 불일치, 오프라인 중 출력 버튼과 API를 실행한다. ACK 전 bake/새 export 시작 0건, 실패 상태에서 `저장됨` 표시 0건이다. ACK 도착 전 추가한 편집은 여전히 미저장으로 남는다.
- TEST-23: bake snapshot을 잠근 직후 새 순서·시간·아웃라인 편집을 저장한다. 기존 export는 잠근 revision의 결과이며 새 편집과 섞이지 않는다. 이전 결과 열기는 가능하지만 최신 결과로 표시하지 않는다.

### 6.5 시간·동일 bake·독립 뷰어 — TEST-20, 21, 22, 23, 32

- TEST-20: 기본 FPS→명시 duration→다시 기본값 사용을 전환하고 재열기한다. FPS 변경은 기본 시간 슬롯만 바꾸며 직접 지정 값을 보존한다. `[A,B,A,C]`의 중복 A가 서로 다른 duration/offset을 가져도 유지한다. 0·음수·NaN·비정수 duration은 UI/API에서 거절한다.
- TEST-20: 새 timing schema를 composer·preview·runtime manifest·PNG sequence manifest·Aseprite serializer가 함께 읽는지 검사한다. request에 알 수 없는 `durations_ms`를 덧붙였다가 기존 composer가 무시하는 경로, 균등 FPS로 조용히 대체, GCD 기반 대량 복제 근사는 모두 실패다.
- TEST-21: 프로젝트 DB·편집 상태·localStorage를 사용하지 않는 독립 뷰어에 export 파일만 넣는다. 제어 clock의 79/80/199/200/399/400ms와 여러 주기 경계에서 occurrence·offset을 비교한다. 단발 `hold-last`와 loop 주기 경계의 처음 복귀를 각각 검증한다. 다른 endBehavior는 첫 MVP에 활성화하지 않는다. 브라우저 UI는 실제 refresh 오차를 별도로 기록한다.
- TEST-22: 최종 preview가 요청한 export ID/atlas hash와 직접 디코딩한 bitmap을 캡처한다. PNG와 atlas rect의 전체 RGBA를 비교한다. alpha=0 숨은 RGB, 반투명 RGB, 복제·flip·offset·픽셀 편집·baked outline fixture를 포함한다. 빠른 JS 편집 preview나 screenshot 비교만으로 PASS 처리하지 않는다.
- TEST-22/23: dedup atlas가 같은 rect를 공유해도 occurrence 순서·duration·anchor·loop·endBehavior는 유지한다. bake artifact 하나를 손상시킨 시험용 복제본은 hash 오류로 차단하고 미완성 ZIP/manifest를 publish하지 않는다. 성공한 export는 독립 디렉터리에서 불변이다.
- TEST-32: preview-only 테두리 켜기/끄기 전후 최종 RGBA 차이 0. baked 테두리는 새 recipe/hash와 같은 최종 bitmap에 반영한다. 정수 출력 셀 픽셀 두께, alpha, 4/8방향, 팀별 설정을 복원하고 최종 overflow를 재검사한다. alpha 잔여물 경고는 테두리 표시와 독립적이다.

### 6.6 실제 provider·작업 복구 — TEST-24–31

MOCK-JOBS의 각 실패 분기는 제어된 결과와 호출 ledger로 판정한다. 실제 provider에서는 취소·조회·idempotency capability를 먼저 읽고 지원 기능의 실제 결과와 미지원 UI 경로를 구분해 기록한다.

- TEST-24: `queued/running/succeeded/needs_review/failed/cancel_requested/canceled/interrupted/provider_outcome_unknown`의 UI 문구와 가능한 행동을 확인한다. 작업 완료가 후보 채택·QA 승인으로 자동 승격되지 않는다. 정확한 진행률이 없는 외부 처리에서 임의 %를 만들지 않는다.
- TEST-25/28: 생성 성공 후 로컬 파생 단계에서 실패·worker 종료를 일으킨다. 입력 hash가 같은 checkpoint를 재사용하고 성공한 생성 단계 재호출 0건이다. 브라우저 종료만으로 worker를 취소하거나 저장 결과를 잃지 않는다.
- TEST-26: 실제 upstream 취소 확인과 로컬 종료를 구분한다. 지원하지 않는 취소를 성공·환불로 표시하지 않는다. 늦은 응답이 기존 채택 후보를 바꾸지 않는다. 확인 불가능하면 그 사실과 후속 행동을 유지한다.
- TEST-27: engine의 Codex timeout 내부 자동 재시도까지 포함해 요청 카운터를 검사한다. provider 명시와 초기 동시성1을 검증하고 외부 결과 불명 시 내부 재호출도0건이어야 한다. 동일 key 제출, 응답 유실, 앱 재열기에 로컬 job 1개가 유지된다. 외부 접수 불명에서는 자동 재전송 0건이다. 실제 provider가 조회/idempotency를 지원하지 않으면 기능을 위조하지 않고 `접수 결과 확인 필요`로 남긴다. 사용자가 의도한 별도 새 호출은 새 key·새 이력으로 구분한다.
- TEST-29/30: 실제 허용된 전체 생성 1건과 선택 범위 재생성 경로를 구분한다. 실제 부분 재생성은 실제 provider 결과와 새 generation version을 요구한다. 모의 성공만으로 실제 부분 재생성 완료를 주장하지 않는다.
- TEST-30: 로그인 확인·provider 목록 표시는 전제일 뿐이다. 실제 참조 전달·프레임 설정·응답 결과 bytes까지 연결하는 증거가 필요하다. provider가 request ID만 제공하면 job ID로 꾸미지 않고 실제 receipt 종류를 기록한다.
- TEST-31: 미지원 다중 참조·크기·native alpha·조회·취소는 사유와 대체 사용자 동작을 표시한다. 지원하지 않는 값을 활성 UI에서 입력받아 조용히 무시하면 실패다. 실제 호출을 할 수 없으면 해당 실제 분기는 BLOCKED로 보고하고 새 유료 fallback을 시도하지 않는다.

### 6.7 UI 완주·접근성·빈 상태 — TEST-33, 34

TEST-34는 두 여정의 독립 기록을 필요로 한다. PNG 여정은 provider 없이 시작하고 REAL-PROVIDER 여정은 참조 승인→실제 생성부터 시작한다. 두 여정 모두 배경·추출·정렬·큐레이션·가변 시간·팀 테두리·저장·최종 결과·ZIP·독립 뷰어를 포함한다. native alpha처럼 불필요한 처리는 UI에서 검수된 건너뛰기로 기록한다.

- 새 프로젝트, 후보 0개, timeline 0개, 결과 0개에서 원인과 다음 행동을 확인한다. 손상/실패/취소/접수 불명 상태를 빈 화면으로 숨기지 않는다.
- 1:1, 게임 표시 크기, 줌, onion skin, 배경, 승인 기준 비교를 제공하고 표시 크기와 소스 크기를 구분한다. 1:1은 CSS pixel 기준·DPR 표시이며 bitmap oracle은 별도 검사한다.
- 키보드만으로 후보 채택/제거/복제·순서 변경·anchor/offset 숫자 수정·프레임 이동·저장·충돌 해결·재시도·출력까지 수행한다. 드래그의 버튼 대안을 확인한다. 텍스트 입력 중 Space/방향키 단축키가 입력을 가로채지 않는다.
- label·단위·error association·focus-visible·대화상자 focus 복귀를 수동 확인한다. 화면리더에서 선택 frame/occurrence와 QA·저장/작업 상태를 읽고 오류 해결로 이동할 수 있어야 한다. disabled 이유는 hover 없이 읽을 수 있어야 한다.
- 일반 텍스트 대비 4.5:1, 큰 텍스트·필수 UI 경계/포커스 3:1 목표를 검사한다. 200% 확대에서 저장·오류·주요 버튼이 가려지지 않고 canvas만 자체 스크롤한다. 색만으로 승인/차단을 구분하지 않는다. 주요 클릭 대상 최소 32×32 CSS px와 감소된 움직임 설정을 확인한다.
- UX의 G01–G09를 각각 실패시켜 차단 사유와 해결 동작을 확인한다. 선택되지 않은 동작의 오류는 유효한 선택 snapshot을 불필요하게 막지 않되, 출력 선택에 빈 동작이 포함되면 전체 요청을 차단한다. 사용자가 명시적으로 제외할 수 있다.
- 화면 최종 결과가 실제 저장 artifact임을 확인하고 새 편집이 있으면 이전 결과 배지를 표시한다. 개발자가 터미널로 빠진 단계를 대신 처리하거나 JSON을 수동 보정해야 했다면 해당 여정은 FAIL이다.

## 7. 실행 순서·gate·증거

| 단계 | 실행 범위 | 단계 완료에 필요한 증거 | 허용되는 완료 표현 |
| --- | --- | --- | --- |
| 0 | 전용 포크·환경·fixture/provenance·원본 저장 | 엔진 pin/patch/의존성, 해시 baseline, synthetic 준비 목록 | 시험 환경 준비 |
| 1 | TEST-01–16 | UI/API·실제 파일 처리, raw·알파·배율·manual anchor의 실제 결과와 사람이 승인한 검수 | 가져오기·정렬 경로 검증 |
| 2 | TEST-17–23 + TEST-32의 출력 회귀 | 저장 실패/충돌·재시작, 가변 시간·전체 RGBA·독립 뷰어 | 필수 P0 전체 PASS일 때 기존 이미지 경로 완료 |
| 3 | TEST-24–29, 31 모의 분기 | 요청 카운터·상태 전이·강제 종료/복구와 no paid fallback | 모의 작업 경로 검증 |
| 4 | TEST-26–31의 실제 capability 분기·TEST-30 | 실제 provider receipt·참조 전달·생성/재생성 결과·지원/미지원 분기 | 실제 연동 증거가 충족된 범위만 완료 |
| 5 | TEST-32–34 및 전 회귀 | 팀 테두리·키보드·두 UI 여정·새 프로젝트 복원·독립 파일 재생 | 34개 및 필수 하위 시나리오 PASS일 때 최종 MVP 완료 |

기존 이미지 경로가 성공해도 실제 생성 경로는 별도로 미검증일 수 있다. 실제 provider 입력/권한/capability가 없으면 가능한 준비와 로컬 시험을 끝낸 뒤 필요한 항목을 구체적으로 보고한다. 자동으로 유료 provider를 대체하거나 모의 결과로 완료 상태를 채우지 않는다.

### 7.1 실행 보고서 형식

실행별 보고서는 향후 `artifacts/acceptance/<runId>/` 같은 별도 출력 위치에 저장한다. 현재 문서 작성은 해당 폴더나 실행 산출물을 만들었다는 뜻이 아니다.

| 필드 | 기록 내용 |
| --- | --- |
| 식별 | runId, TEST-ID, scenario, 요구 IDs, 상태, 실행 일시·판정자 |
| 환경 | 앱 source revision, upstream/patch commit, adapter/recipe/schema version, dependency locks, OS·브라우저·DPR |
| 입력 | fixture 종류/URI/원본 hash/decoded fingerprint/provenance, project/reference/clip revisions, 승인 landmarks |
| 실행 | 실제 수행 명령 또는 UI 단계, job/attempt/receipt, 모의 여부, 설정 snapshot, 실제 호출 수 |
| 기대/실제 | 수치·상태 전이·이미지 diff·검수 의견·gate 오류와 실제 측정값 |
| 산출물 | 화면 기록·로그·원본/파생 hash·export files·manifest·bitmap diff·독립 뷰어 결과 경로 |
| 제한 | 실제 미실행 분기, 미지원 capability, 실패 원인, 다음 조치. secret 제외 |

`NOT_RUN`은 아직 실행하지 않음, `PASS`는 모든 필수 분기의 증거 충족, `FAIL`은 실행 결과가 기대를 위반함, `BLOCKED`는 실행하려 했으나 fixture/환경/실제 호출 입력이 부족함을 뜻한다. 이 문서의 현재 34개는 모두 `NOT_RUN`이다. 문서 링크·표·개수 점검은 앱 수용 시험을 PASS로 바꾸지 않는다.

### 7.2 자동화 명령 예시 — 제안·미실행

아래는 **후속 구현에서 테스트 파일·스크립트를 만든 뒤 사용할 명령 제안**이다. 현재 경로/스크립트의 존재나 실행 성공을 보증하지 않으며 이번 문서 작성 중 실행하지 않았다. 실제 구현의 package/pytest 구성이 정해지면 실행 보고서에 정확한 명령으로 교체한다.

```sh
# 제안·미실행: 합성 oracle, 데이터 계약, 저장/작업 fault injection
engine/sprite-gen/.venv/bin/python -m pytest tests/acceptance -m "not real_provider"

# 미실행: 허가된 기존 ego 탭의 읽기 전용 앱/API/worker 연결 smoke
EGO_TASK_SPACE_ID="$AUTHORIZED_SPACE_ID" EGO_PAGE_LABEL="$AUTHORIZED_PAGE_LABEL" npm --prefix apps/web run test:e2e

# 제안·미실행: 허용된 실제 provider 범위와 설정이 마련된 경우에만
engine/sprite-gen/.venv/bin/python -m pytest tests/acceptance -m real_provider
```

브라우저 시험은 ego만 허용한다. 위 smoke는 브라우저를 설치·실행하거나 탭을 만들지 않으며, 기존 CLI/브라우저/탭이 없으면 실패한다. 다른 작업이 사용하는 TaskSpace는 지정하지 않는다. UI·키보드·독립 뷰어·bitmap parity 수용 기준은 이 연결 smoke만으로 PASS 처리하지 않는다. 구체적인 설정은 [웹 README](../../apps/web/README.md)를 따른다.

실제 provider 테스트는 기본 회귀 명령과 분리하고 명시적으로 허용된 provider·호출 범위가 없으면 실행하지 않는다. 연구 재현 스크립트 실행도 제품의 수용 명령을 대체하지 않는다. 기존 연구 산출물은 덮어쓰지 않고 새 제품용 시험 공간에서 증거를 만든다.

## 8. 현재 판정

설계 입력과 연구 증거를 12개 요구 ID, 34개 기존 수용 기준, 필수 하위 시나리오에 연결했다. **앱 수용 34개: NOT_RUN 34 / PASS 0 / FAIL 0 / BLOCKED 0**. 이는 문서 작성 시점의 상태이며 연구의 19개 관찰 pass와 합산하지 않는다. 실제 provider 생성·부분 재생성, raw 제거 품질, 브라우저 preview parity, worker 강제 종료 복구, 팀 아웃라인, 독립 뷰어의 제품 실행 결과는 후속 구현에서 확보해야 한다.
