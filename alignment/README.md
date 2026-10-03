# 이미지 처리·확정 bake

`pipeline.py`는 `packages/contracts/IMPLEMENTATION.md`의 렌더링 함수를 구현한다. Python 실행은 프로젝트 전용 `engine/sprite-gen/.venv`를 사용한다. API/worker 파일은 이 모듈의 소유 범위가 아니다.

- `inspect_image`: alpha 0 / 1–254 / 255 통계. `decodedHash`는 API 저장소와 같은 `SHA256(decoded RGBA bytes)`다.
- `extract_regions`: whole/grid/components/regions의 fit 이전 픽셀과 원본 좌표를 반환한다. 연결 성분 엔진에는 alpha>0 마스크를 전달해 upstream의 alpha>16 임계값으로 작은 장비가 사라지지 않게 한다. `minArea` 미만 성분도 보존하고 검수 표시한다. 격자 경계를 넘는 성분은 영역을 확장해 보존하므로 제안 crop끼리 겹칠 수 있다. `warnings`, `reviewRequired`, `belowMinArea`, `crossingComponents`를 `extractionReview`에 보존한다.
- `suggest_anchor`: alpha≥16, 하단 12%/최소 4px, 밴드 x 양끝 중간, exclusive bottom. 측정 불가 시 typed 오류이며 자동 승인은 하지 않는다.
- `cutout_image`: 실제 알파가 있으면 전체 RGBA를 유지한다. 불투명 입력은 전용 엔진 cutout을 사용하고 수동 검수 필요 상태를 반환한다. 원본/기존 출력은 덮어쓰지 않는다.
- `render_occurrence`: 수동 raw/crop 앵커, 공통 nearest scale, JS 반올림, grounded/airborne root, canvas pixel edits, pivot/flip/scale/shear/rotation, 4/8방향 outline 순이다. 변형은 엔진의 화면 좌표 반시계 양수 회전을 따른다. 셀로 자르기 **전** 전체 alpha>0 support와 safeRect의 네 변 초과량을 검사한다. 단계별 input/output/recipe hash와 residual을 반환한다.
- `build_bundle`: 선택 동작의 reference/frame/anchor/clip 승인, 그룹 revision, 파일 hash, 빈 alpha/timeline, timing, overflow, 저장 상태를 검사한다. snapshot을 복사해 고정하고 이미 존재하는 산출물은 덮어쓰지 않는다. 비엄격 preview는 항상 `needs_review`다.

최종 파일은 `atlas.png`, `pngs.zip`, `runtime.json`, `aseprite.json`, `qa.json`, `bundle.zip`이다. alpha=0 RGB를 0으로 정규화한 셀을 pack하고, 저장한 atlas를 다시 읽어 PNG를 잘라 전체 RGBA를 대조한다. ZIP의 모든 파일 bytes까지 검증한 뒤 staging 디렉터리를 원자적으로 게시한다. Aseprite JSON은 편집 원본 `.aseprite`가 아니며 loop/endBehavior/anchor는 `runtime.json`에 있다.

중복 bitmap은 atlas rect를 공유할 수 있지만 occurrence ID/순서/duration/frameVersionId/anchor는 각각 보존한다. runtime 변형은 이미 bake되어 있으므로 다시 적용하지 않는다. preview-only outline은 bitmap과 recipe에 영향을 주지 않는다. source pin은 `b058341f7543f3adcbea227bd4e6b7587895b1bc`이며 엔진 lock/사용한 소스 fingerprint/adapter 소스 fingerprint도 결과에 기록한다.

## 검증

2026-10-03 실행:

```sh
engine/sprite-gen/.venv/bin/python -m pytest tests/integration/test_pipeline.py tests/integration/test_api.py -q
```

**71 passed**: pipeline 62개 + API 9개. Starlette/httpx deprecation 경고 1개. 실제 provider 호출 0회. 실제 aligned 거너 PNG 0/3의 provenance SHA-256과 471/320px 높이 보존을 확인했다. 이는 raw 복잡 배경 제거 품질·사람의 외형 승인·브라우저 완주 검증을 뜻하지 않는다.

통합 확인: worker의 `extractionReview` 메타데이터 저장, faint-only 성분의 pending 중앙 앵커 fallback, 저장소 `AppError` 전달, API를 통한 실제 bundle 생성이 통과했다.

통합 담당에게 보고한 남은 사항: 확인 시점 `services/worker/task.py`의 `params.get('clipIds') or ...`는 명시적 빈 목록을 전체 동작 선택으로 바꾼다. 이 모듈은 빈 목록에 `EMPTY_TIMELINE`을 반환한다. worker에서는 키 부재와 빈 목록을 구분해야 한다. 해당 파일은 수정하지 않았다.

## 저장된 최종 산출물의 독립 검사

`alignment/verify_artifacts.py`는 렌더러/API/DB/provider를 import하지 않고, 이미 저장된 6개 파일만 읽는다. 파일을 생성하거나 수정하지 않는다. 기본 검사 위치는 repository의 `artifacts/acceptance/real-character/output/`이다.

```sh
PYTHONDONTWRITEBYTECODE=1 engine/sprite-gen/.venv/bin/python -m alignment.verify_artifacts
# 다른 최종 산출물 경로 지정
PYTHONDONTWRITEBYTECODE=1 engine/sprite-gen/.venv/bin/python -m alignment.verify_artifacts /absolute/path/to/output
```

stdout에 JSON 보고서를 출력한다. 종료 코드는 `0=PASS`, `1=FAIL`, `2=BLOCKED`(필수 파일 미도착)다. 저장이 필요하면 호출자가 stdout을 출력 디렉터리 **밖의** 별도 증거 파일로 리다이렉트할 수 있다.

검사 내용:

- runtime의 모든 occurrence를 순서대로 검사한다. dedup 여부와 관계없이 atlas rect의 전체 RGBA와 PNG ZIP의 각 슬롯 PNG를 비교한다. alpha=0 숨은 RGB 정규화, 반투명 RGB/alpha, 크기, decodedHash, PNG hash를 포함한다.
- runtime과 PNG sequence의 모든 슬롯/동작 메타데이터, duration/누적 경계/loop/hold-last, FPS 기본 시간, occurrence별 anchor/lineage를 비교한다. Aseprite의 순서/개별 duration/rect/tag 범위를 검증한다.
- `frameSources`의 원본·이미지·좌표 mapping과 `sourceAssets`의 SHA-256/decodedHash를 확인한다. 이미지→raw→상위 부모 자산 연결을 따라가며 부모 해시 존재, 누락, 순환, 기록된 generationVersionId를 검사한다. 선택되지 않은 과거 `parentFrameVersionId`는 외부 이력으로 따로 보고한다.
- artifact 파일 해시, bundle 내부 사본의 동일성, QA와 runtime의 revision/recipe, 모든 occurrence의 QA 픽셀 hash/anchor/overflow를 검사한다. 검사 도중 파일이 바뀌면 실패한다.

이 검사는 **저장된 산출물 사이의 일치와 계보 기록**을 확인한다. 출력에 없는 원본 asset bytes의 실제 hash, 과거 프레임 bytes, 생성 제공자의 실행 진위, 외형 품질, 브라우저 재생은 검증했다고 보고하지 않는다. PASS 보고서의 `limits`에도 이 범위를 명시한다.

후속 검사기 추가 후 `PYTHONDONTWRITEBYTECODE=1 engine/sprite-gen/.venv/bin/python -m pytest tests/integration/test_pipeline.py -q -p no:cacheprovider` 실행: **84 passed**. 새 22개 검사는 실제 로컬 bake 산출물과 격리된 손상 사본을 사용하며 파일 해시를 다시 맞춰도 내부 불일치를 잡는지 확인한다. 브라우저/외부 생성/서버 실행은 하지 않는다.
