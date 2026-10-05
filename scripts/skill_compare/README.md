# 실제 영상 비교 도구

검증 기록: `docs/product/SKILL_AB_RESULTS_2026-10-06.md`. 아래 도구는 생성 요청을 하지 않는다. 원본은 읽고 실험 폴더에만 출력한다. 실제 사용자 프로젝트의 DB/승인 상태에 결과를 등록하지 않는다.

- `verify_upgrade.py OUT`: 보존 영상 3개를 현재 앱 경로로 8장 재처리하고 실제 RIFE/정확한 WebP 및 사용자 파일 해시 보존을 확인한다. 기록된 로컬 입력이 필요하며 새 출력 폴더만 허용한다.
- `frame_room.py`: 실제 앱 처리·정규화·마무리·렌더 함수를 호출한다. `default`, `rgba`, `repaired`를 실행하고 PNG/출처/실패를 보존한다. 새 `--out` 경로가 필요하다. 비교 당시 RGBA WebP 실패는 역사적 기록이다. 이후 앱 exact 인코딩으로 수정했으며 현재 검증은 `LATEST_SKILL_UPGRADE_2026-10-06.md`를 따른다.
- `package_upstream.py`: 정식 최신 스킬의 기존 strip을 64×128 투명 셀에 **패딩만** 해 비교용 PNG를 만든다. 제품 bake를 대신하지 않는다.
- `resample_shared.py`: `--engine`에 지정한 엔진의 실제 RIFE/resample을 동일 입력 PNG에 실행한다. `--standing-height`는 원본 영상 첫 그림의 측정 체고다. 새로운 생성 API를 호출하지 않는다.
- `build_review.py`: 이번 실험 폴더 구조에서 MP4/기준 그림/PNG가 내장된 단일 HTML을 만든다. 파일을 다른 기기에 옮겨도 외부 서버 없이 확인 가능하다.
- `summarize.py`: 저장된 JSON/해시를 읽고 기록을 갱신한다. 이번 사례의 디렉터리·실험 날짜를 사용하는 전용 도구다. 다른 실험에는 새 입력 구성과 날짜를 명시적으로 지정하도록 먼저 수정한다.
- `inspect_softness.py ROOT`: 같은 고정 구간의 마무리 후·배치 전 알파 통계와 nearest 확대 비교를 만든다. 반투명 개수는 지각 선명도 점수가 아니다.
- `inspect_color.py ROOT`: 이번 영상의 지정 장갑/소매 ROI에서 raw/keyed 픽셀을 비교하고 기준 그림·원본·키 제거·최종 축소 확대표를 만든다. 지정 ROI/프레임에 한정된 진단이며 자동 재질 판정·전체 시간축 검사를 대신하지 않는다.
- `analyze_recheck.py ROOT --latest-engine PATH`: 하늘 해적 추가 비교의 keyed 일치·출력 마무리·공통 영역 통제·WebP exact 진단·동일 입력 RIFE 수치를 기록한다. `analysis/common-finish`의 별도 통제 산출물이 먼저 필요하다. 최신 자체 진단기를 양쪽 결과에 적용한 수치이며 독립 품질 점수는 아니다.
- `build_recheck_review.py ROOT`: 두 번째 비교용 독립 HTML. 셀 크기를 실험 설정에서 읽으며 PNG·MP4를 내장한다. 기존 비교 HTML을 덮어쓰지 않는다.
- `build_frame_count_review.py ROOT`: 실제 앱 재처리 결과 `frame-room/walk-8`, `walk-12`, `default`를 8/12/24장 전용 뷰어로 만든다. 선택 프레임의 RGBA 일치·같은 1초·중복 index 없음·출력 parity를 확인한다. 자료는 같은 캐시와 `run_variant()`에 `maxFrames=8/12`, `finishMode=gif`, `repairMode=off`를 전달해 만들었다.

앱 재처리:

```sh
engine/sprite-gen/.venv/bin/python -B scripts/skill_compare/frame_room.py \
  --clip /absolute/source.mp4 --reference /absolute/input-canvas.png \
  --out /absolute/new-experiment/frame-room
```

다른 폭/방향의 캐릭터에는 `--cell-width 96 --cell-height 128 --direction front_diagonal`처럼 실제 조건을 명시한다. 기본 인자를 생략하면 기존 64×128/side 비교와 동일하다.

최신 스킬 처리(설치 루트는 실제 경로 확인, FPS는 probe 결과 사용):

```sh
/Users/cheng80/.codex/skills/sprite-gen/.venv/bin/sprite-gen video-frames \
  --clip /absolute/source.mp4 --out-dir /absolute/new-experiment/upstream/frames \
  --key magenta --spill auto --reference /absolute/input-canvas.png --decontam auto
/Users/cheng80/.codex/skills/sprite-gen/.venv/bin/sprite-gen video-loop \
  --frames-dir /absolute/new-experiment/upstream/frames/keyed \
  --out-dir /absolute/new-experiment/upstream/auto \
  --state walk --fps 24 --body-height 94 --strip-height 128 \
  --anchor motion-auto --repair on --name walk
```

같은 구간 비교는 별도 출력에 `--cycle fixed --start N --length L --anchor none --repair off --n-out L`을 사용한다. fixed/none은 기존 작은 점 제거 단계를 포함한다. 자동 선택과 같다고 간주하지 않는다. 정식 `video-cycle-align`은 출력 폴더를 갱신하므로 먼저 **실험 출력 사본**을 만들고 실행한다. 사용자 원본 폴더에서 직접 실행하지 않는다.

이번 실험 전체는 `.data/experiments/skill-ab-20261006/`이며 Git에 포함되지 않는다. 기존 프레임룸의 유효 실행은 `existing/frame-room/run-02/`, 새 영상은 `new/frame-room/`이다. 첫 하네스 실패는 역사적 진단이며 최종 품질 결과로 사용하지 않는다.
