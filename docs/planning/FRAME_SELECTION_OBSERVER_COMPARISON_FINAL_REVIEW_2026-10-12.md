> 보관 안내(2026-10-13): 이 문서는 2026-10-12~13 프레임 선별 실험·검수 당시의 기록이다. 여기 적힌 Laya·Jev·관찰 모델 비교 등의 선택지와 실행 방법은 현재 기본이 아니다. 현재 기본은 로컬 Codex catalog의 최신 Luna 관찰과 규칙 판정이며 [FRAME_SELECTION_RULES_CLEANUP_2026-10-13.md](FRAME_SELECTION_RULES_CLEANUP_2026-10-13.md)를 따른다. 시험 수, `output/`·`/tmp` 증거 경로와 작업 ID는 당시 작업 폴더 기준이며 이 저장소에 포함되지 않는다. 키 값과 비밀 파일 해시는 기록하지 않았다.

# 프레임 선별·관찰 모델 비교 최종 독립 검수

결론: **no blocking findings**. PM 최종 freeze 이후 현재 코드, 실제 입력·출력 이미지, 프로젝트 라이브러리, 재생 파일과 원본 보존을 독립 확인했다. 구현자 요약만으로 판단하지 않았다. 코드·설정·기존 문서·프로젝트 데이터는 수정하지 않았으며 검수 파일만 `/tmp`에 기록했다.

## 검수 대상과 freeze

- 작업 `task_4a50f684b4d0`, dispatch `ctx_260836d69eb0`, 읽기 전용 GPT-6.1 Sol Medium 검수. 실제 GPT observer 실험과 이 검수는 별개다.
- 기본 구현 및 최종 Opus 후속 수정 diff와 현재 코드, 호출자·계약·테스트·제품 문구를 확인했다. PM이 최종 freeze와 구현 종료를 통보한 뒤 검증했다.
- `output/frame-selection-observer-comparison/followup/freeze-code.sha256` 9개 모두 일치. 최종 `adapters/spritegen/frame_selection.py` SHA256: `370d24d8c68d7400e34a6c903c8aa93b4d41268b82ce50375bf510bd15713296`.
- 최초 발견한 P2 두 건은 Opus가 수정했다: 양축·짧은 변 크기 제한 및 극단 종횡비 반올림, `frameObserver=[]/{}` 등 잘못된 타입의 안전한 API 거부. 최종 회귀 시험에서 통과했다. 미해결 blocking finding은 없다.

## 직접 확대 검토: F023 / F024 / F025

기존 프로젝트 `5f83bfb7-a661-4fdc-a495-8a05c6df8dcc`의 실제 448px 관찰 입력 `candidates.sheet.png`, pirate reference와 추출 raw·키잉 원본을 찾고 비교했다. F 번호는 0 기반 sourceFrameIndex이므로 F024는 추출 파일 `frame-0025.png`다. 새 결과의 raw/keyed/final 비교 이미지와 실제 최종 셀도 직접 봤다.

- F023: 화면 오른쪽 부츠 정강이·발등의 넓은 올리브 녹색 얼룩. 기준 이미지의 갈색 부츠와 다르다.
- F024: 같은 위치의 얼룩이 F023보다 약하지만 확대 raw·키잉 후보·최종 64×128 셀에서 남아 있다. 보이는 의상 색 불일치라는 판단이다. raw 배경이 마젠타인데도 있으므로 배경 제거가 만든 녹색 잔여라고 단정하지 않는다.
- F025: 두 부츠가 기준처럼 갈색이며 해당 얼룩이 실질적으로 사라진 깨끗한 이웃이다. 해적 F024→F025 교체 개선 근거는 실제 이미지로 확인했다.
- F027 버클 주변은 정상 금색 하이라이트와 경미한 녹황 tint가 구분 어려우며 F036 역시 mild 경계다. 성직자 F049의 뒤쪽 다리·부츠 얼룩은 명확하지만 F048/F050의 약한 색조는 clean 확정이 어렵다. 성직자 교체를 깨끗한 이웃 교체 성공으로 확대 해석하지 않는다.

사람 검토 기준 제안: reference에 원래 있는 녹색 의상·금색 장식·음영은 유지하고, 같은 부위의 raw/키잉/최종 셀과 양쪽 이웃을 함께 본다. 정상 팔레트 밖의 국소 얼룩이 명확할 때만 reject하고 약한 tint·해상도 부족·형상 불확실성은 review로 남긴다. 이 문서의 시각 판단도 모델 검수이며 정식 사람 정답 라벨이 아니다.

## 동일 입력 비교와 판정 해석

- 실제 두 영상 × 두 모델 호출의 9개 첨부 이미지, 순서·후보 ID·reference, prompt/schema SHA를 대조했다. 같은 영상의 Luna/Sol 입력은 동일하다. 실제 rollout의 모델과 effort도 요청대로 각각 `gpt-6-luna`, `gpt-6.1-sol`, `medium`이다.
- 모델별 cache key가 분리되고 model/effort/schema/prompt version 및 이미지·reference 내용 해시가 포함된다. Laya 단계는 기존 관찰을 재사용한다. 실제 실험 4회 관찰 호출과 4회 cache hit 기록을 확인했으며 검수자가 새 호출을 만들지 않았다.
- 최종 freeze 코드로 저장된 실제 후보에서 관찰 입력을 다시 구성한 18장 모두 실제 실험 첨부 이미지와 바이트 단위로 일치했다.
- 사전 라벨은 Claude Opus 구현자의 모델 시각 판단이다. 독립 사람 정답이 아니다. 해적의 사전 clean 8개에 대한 Sol 결과는 **reject 5개 + review 1개(F032, extra_or_missing_parts)**다. 6개 모두 색 결함 reject라는 뜻이 아니다. mild 경계 판단 차이가 있으므로 확정 오탐 숫자로 읽으면 안 된다.
- 사전 라벨 원본 SHA `36c1f332f100611ea52e0236e9faaa5bb41b4656738dcb616d70b92cf191cdd2`는 유지됐다. 잘못 적힌 추정 recordedAt은 별도 metadata correction에 정정됐다. 원본 mtime 21:57:10은 실제 첫 관찰 호출보다 앞선다.
- 이전 v1과 v2는 입력 크기뿐 아니라 schema/prompt도 달라 F024 검출 개선을 확대 이미지 하나의 인과 효과로 확정할 수 없다. 모델 품질 우열·일반 정확도·반복성·Laya 우월성은 입증되지 않았다.

## 실제 교체·저장·재생 검증

새 프로젝트 `c314768d-2492-4a2e-97b8-fe3676826912`의 `project.sqlite3`를 읽기 전용으로 열었다. revision 15, clip 10개, frame 94개(사용 80개·균등 대체 후보 14개), 각 8슬롯, `walk`, loop 유지, 원본 인덱스 증가와 양의 duration을 확인했다. 이미지 파일이 실제 존재하며 사용자 review/hidden 필드도 보존됐다.

- 해적 균등 `18,21,24,27,30,33,36,39` → Luna 규칙/Laya `18,21,25,27,30,33,36,39`. 총 1000ms와 8슬롯 유지. 교체된 F024는 슬롯 없는 `uniform-alternative`로 원본 이미지와 함께 보존됐으며 사용 횟수 0이다.
- 표시 시간은 `125,167,83,125,125,125,125,125ms`. 원본 시각을 따르므로 오염이 남은 F021(review)의 표시가 125→167ms로 늘었다. 문서에 공개된 품질 비용이며 전체가 clean이라는 의미는 아니다.
- 성직자 결과 총 1083ms 유지. 약한 이웃 tint와 일부 review가 남으며 자동 선정 applied 상태가 모든 프레임의 결함 해결을 뜻하지 않는다.
- 10개 클립의 GIF/WebP 총 20개 해시를 SQLite artifact·작업 publication 기록과 직접 대조했다. 80개 WebP 프레임 전부를 저장된 라이브러리 alignment로 메모리 렌더한 RGBA와 비교해 정확히 일치했다. 실제 이미지·재생 결과가 라이브러리와 연결됨을 확인했다.
- WebP 시간 합은 해적 1000/성직자 1083ms, GIF 성직자는 기존 10ms tick 반올림으로 1080ms다. 모든 재생물은 8프레임·무한 루프다.
- 기존 실제 비교 프로젝트와 신규 uniform strip/GIF/WebP 6개 SHA가 모두 동일하다. uniform 호환성이 실제 결과로 보존됐다.

## 코드 및 제품 흐름

참조의 정상 의상 색을 결함으로 보지 않는 observer prompt/schema, unknown+defect→review, 오류·불확실성의 보수 처리, 요청 타입 검증, sequence rollback, 균등 선택 fallback, 대체 원본 보존 경로를 확인했다. UI의 “기준과 다른 색 얼룩”, review 표시, 대체 후보 설명·선택 제어는 판정을 사용자가 확인할 수 있는 문구다. 기존 저장된 ego UI 스크린샷도 직접 검토했다.

일반 녹색 의상에 대한 전역 녹색 제거 규칙은 도입되지 않았다. 정상 녹색 합성 입력과 fake observer를 사용한 offline self-check가 모두 keep·교체 없음으로 통과했다. 이는 코드 정책 회귀 확인이며 실제 모델의 녹색 의상 오탐률 검증은 아니다. 극단 종횡비에서 입력 크기 제한을 맞추면 미세 결함이 안 보일 수 있고 unknown/review 처리에 의존한다.

## 실제 독립 검증과 데이터 보존

- Python `tests/integration/test_frame_selection.py`: **40 passed, 1 deselected**. 실제 Laya checkpoint smoke를 제외하고 capability를 offline 처리해 외부 호출·실제 추론을 차단했다.
- UI `candidateHistory.test.ts` 및 `videoWorkflow.test.ts`: **91 passed, 2 files**.
- `git diff --check`: 성공.
- 잘못된 observer 타입과 양축/짧은변/극단 종횡비 제한의 최종 회귀 시험 통과. 구현자의 실제 API 422·프로젝트 revision/job 개수 불변 receipt도 읽었지만 독립 실제 HTTP 호출은 수행하지 않았다.
- baseline `.data/output` 기존 **13,553개**, missing 0, changed는 실험 등록 대상 `.data/app.sqlite3`만. 원본 프로젝트·이미지·영상·출력 baseline 파일은 모두 보존됐다.
- 기존 worktree baseline 105개 missing 0, 변경 7개는 해당 기능 코드·UI·테스트·계약 범위다. 기존 사용자 변경을 임의로 되돌린 흔적은 없다. 신규 실험 출력은 baseline 이후 추가분이다.
- freeze 9개 및 사전 라벨 내용 변경 없음. 실제 manifest 결과는 `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-observer-comparison/review/frame-selection-observer-review-final-preservation.json`에 있다.

검증 중 최초 시스템 Python은 numpy 부재로 중단되어 기존 engine venv를 사용했다. 최초 원본 crop과 최종 셀 크기 비교는 좌표계가 달라 실패했고, 라이브러리 alignment 렌더로 올바르게 비교한 80개가 전부 일치했다. 이 초기 실패를 제품 결함이나 통과 시험으로 계산하지 않았다.

## 증거 파일

- 실제 입력/rollout 대조: `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-observer-comparison/review/frame-selection-observer-review-fairness.json`
- 최종 입력 18장·정상 녹색 정책: `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-observer-comparison/review/frame-selection-observer-review-final-input-identity.json`
- SQLite·duration·재생 파일: `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-observer-comparison/review/frame-selection-observer-review-playback-library.json`
- 라이브러리와 WebP 80셀: `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-observer-comparison/review/frame-selection-observer-review-webp-exact.json`
- uniform 전후 동일성: `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-observer-comparison/review/frame-selection-observer-review-uniform-real-compatibility.json`
- 최종 보존·freeze: `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-observer-comparison/review/frame-selection-observer-review-final-preservation.json`
- 독립 실행 로그: `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-observer-comparison/review/frame-selection-observer-review-pytest.txt`, `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-observer-comparison/review/frame-selection-observer-review-vitest.txt`
- 원본 시각 증거: `output/frame-selection-observer-comparison/inspection/`, `replacement/`, `playback/`
- 현재 구현 보고 및 fix 기록: `docs/planning/FRAME_SELECTION_OBSERVER_COMPARISON_2026-10-12.md`, `output/frame-selection-observer-comparison/followup/fix-report.md`

전체 빌드·전체 회귀 시험·실제 observer/Laya 추론·브라우저 조작은 재실행하지 않았다. 새 영상 생성·외부 관찰·모델 설치·Git 게시도 하지 않았다. 남은 위험은 mild 색조의 판단 차이, 유지된 review 프레임과 극단 입력 가독성, 사람 라벨 없는 모델 품질 일반화다.
