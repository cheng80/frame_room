# sprite-gen 2.12.1 제품 포크

Upstream: https://github.com/aldegad/sprite-gen · v2.12.1 · b058341f7543f3adcbea227bd4e6b7587895b1bc

연구 보존 tarball의 SHA-256을 baseline.json과 비교한 뒤 360개 원본 파일을 추출했다. LICENSE, NOTICE, 각 SPDX 고지는 변경하지 않았다. 공용 skill 설치는 import/실행/수정하지 않는다.

수정:

현재 품질 반영 버전은 **v2.34.0**이다. 아래 번호 1~5는 기존 적용 이력을 보존한 기록이며, 현재 파일 해시는 `engine-lock.json`의 `patches`를 기준으로 검사한다. backports의 과거 항목에 적힌 해시는 당시 기록이다.

1. `sprite_gen/gen/__init__.py`: GenTimeoutError의 내부 1회 재시도 삭제. 접수 불명 요청은 재전송하지 않는다.
2. `sprite_gen/gen/codex_provider.py`: 미지원 aspect ratio도 거절. ChatGPT 구독 route 고정 및 API 키/부모 thread 환경 제거. transport prompt/stdout/stderr/rollout 원문 보존. 자식은 worker process group을 상속한다.
3. `tests/gen/test_gen.py`: 원본 receipt 복사 검증에 맞춰 기존 fake rollout을 실제 빈 파일 fixture로 생성한다. 기존 테스트 assertion은 유지한다.

앱은 `adapters/spritegen/provider.py`의 명시 Codex 단일 호출만 사용한다. upstream CLI의 타 provider/default/facing 기능은 앱 인터페이스가 아니다. 반환 PNG는 그대로 두고 별도 앱 pipeline이 배경 제거·추출·정렬을 수행한다.

재설치(repository root):

```sh
uv venv --python 3.12 engine/sprite-gen/.venv
uv pip sync --python engine/sprite-gen/.venv/bin/python engine/requirements.lock.txt
uv pip check --python engine/sprite-gen/.venv/bin/python
```

requirements.lock.txt는 직접/전이 의존성 28개를 설치 버전으로 고정한다. engine-lock.json은 archive/원본/수정본/라이선스 해시와 실제 Python·의존성 inventory를 기록한다. 설치 중 Git·원격 게시 작업은 없다.

4. `sprite_gen/frames/cutout.py` (2026-10-04): prepare가 선택하는 cyan 배경을 가져오기 cutout도 처리한다. cyan 자동 감지·명시 선택을 기존 chroma 제거 경로에 연결한다. off-cyan 실제 생성 색과 일반 cyan 회귀 4건, 기존 cutout 12건 통과. 공용 스킬은 변경하지 않는다.

5. **공개 영상 품질 보완의 선택적 이식 (2026-10-04)**: 기반 엔진은 v2.12.1로 유지하고, 공개 [v2.19.0](https://github.com/aldegad/sprite-gen/tree/9e8cf1e238495b2b113e4acf1f73517e1fbe6e70)의 영상 의존 모듈만 이식했다. 전체 덮어쓰기·공용 skill 변경·외부 생성 호출은 없다. 파일별 기존/이식 원본/로컬 해시는 `engine-lock.json`에 기록한다.

   - `gen/video.py`, `video/batch.py`: `front_diagonal/back_diagonal`, 고정된 시점·장비·카메라 문구, 대각선 보행의 첫/끝 프레임 고정, Lite 보행 크기 및 뒤 대각선 머리 흔들림 억제. `wave/cheer`의 공개 동작 문구와 넓은 캔버스를 연결했다. 앱 `dance`는 공개 UI 항목에 맞춘 로컬 기본 문구이며 upstream 실증 문구로 주장하지 않는다.
   - `video/loop.py`: `resize_cell(image, (w,h))`로 색(Hamming premultiplied RGB)과 알파(범위 제한 Lanczos)를 분리한다. 앱 `rgba` 마무리에 사용하며, 승인된 GIF 재현 경로의 legacy Lanczos+팔레트는 유지한다.
   - `video/auto_motion.py`, `video/local_cycle.py`, `video/gait_fallback.py`: FFT 기반 추적과 단 1회의 제한된 재탐색. 앱은 기존 탐색 성공 시 결과를 바꾸지 않으며 실패 시에만 최대 영상 길이 60%/2초까지 재탐색하고, 3% 이상 크기 드리프트 보정 여부를 기록한다. 분석에서 드리프트를 제거했더라도 실제 출력 프레임의 이음새 검사를 통과해야 한다.
   - `video/frames.py`: v2.18의 top/left/right 4px edge-band 원칙을 영상 모듈 안에서 적용한다. 기존 cyan/extract 변경을 보존하기 위해 palette 보정이 실제 가장자리 픽셀을 만들었을 때만 원래 matte를 다시 계산하고, 원래 투명했던 band 픽셀의 새 coverage를 제거한다. 내부 머리카락 복구와 원래 불투명한 가장자리는 유지한다.
   - `video/repair.py`, `video/rife.py`, `video/rife_install.py`: 점프 프레임 검출·RIFE 보간·흔들림 진단. 앱의 `repairMode` 기본은 `off`이다. `auto`는 설치가 없을 때 원본 유지와 경고를 명시하며 `on`은 필요한 RIFE가 없으면 실패한다. 발견한 실행 파일의 실행 오류는 자동으로 무시하지 않는다.
   - `video/align.py`: 방향별 주기를 동일 프레임 수로 맞출 때 정수 시각의 원본은 재사용하고 중간 시각만 RIFE로 보간한다. 앱은 public `matchClipId`를 parent worker가 `targetFrameCount/targetDurationMs`로 해석해 전달한다. 결과에 고유 `outputFrameIndex`, 두 source index와 보간 비율, 출력 영역 `boundsPaths`를 기록한다. 새 동작은 감지한 착지 시점부터 시작하며 비교 기준 동작 자체의 위상/편집은 변경하지 않는다.

   RIFE 설치는 프로젝트 전용 `.data/tools/rife/rife-ncnn-vulkan-20221029-macos/`이며 모델은 `rife-v4.6`이다. 공식 ZIP SHA-256 `4a63a1f3c9c715773c57d2ee51df1b315ed20cd6c63103e45c483ecc4400b595` 확인 후 설치·실제 보간 검사 통과. 앱 adapter는 이 경로를 직접 찾으므로 전역 환경변수 설정이 필요 없다. 모델/실행 파일은 Git에 넣지 않는다. 약 35MB 설치(전체 ZIP 다운로드는 약 437MB).

   재설치와 엔진 단독 주기맞춤은 기존 최상위 CLI를 변경하지 않은 **모듈 진입점**을 사용한다:

   ```sh
   engine/sprite-gen/.venv/bin/python -m sprite_gen.video.rife_install install --dir .data/tools/rife
   SPRITE_GEN_RIFE="$PWD/.data/tools/rife/rife-ncnn-vulkan-20221029-macos/rife-ncnn-vulkan" engine/sprite-gen/.venv/bin/python -m sprite_gen.video.align --loop-dir <loop-a> --loop-dir <loop-b>
   ```

   검증: 기존/신규 영상 및 video request 엔진 검사 430개 통과, 기본 검색 경로에 RIFE가 없는 실제 바이너리 검사 1개는 프로젝트 경로를 지정하여 별도 통과. 앱 helper로 합성 시험 동작 24→25프레임에 실제 RIFE를 실행해 원본 1장/보간 24장/1,200ms를 확인했다. 테스트 fixture는 실제 AI 생성으로 소개하지 않는다. WebP 엔진 검사를 위해 Homebrew `webp 1.6.0`의 `img2webp`를 설치했다. 앱의 영상 생성 제출은 여전히 단일 요청·접수 불명 재전송 차단을 유지한다.

   크기 드리프트의 좌표 출처: selection의 `scaleCorrection`은 최초 프레임에서 적합한 높이와 프레임별 foot anchor·원본→보정 affine 변환을 보존한다. 앱 결과 `frames[].processing`은 `coordinateSpace: processed-video-canvas`와 `sourceTransform`을 기록한다. RIFE 결과는 `rawToProcessedMapping: non-affine-interpolation` 및 입력별 `preInterpolationSourceTransforms`를 사용해 단일 원본 affine으로 오인되지 않게 한다. 픽셀 처리·타이밍은 이 메타데이터 추가로 바뀌지 않는다.

6. **공개 v2.34.0 품질 기술 반영 (2026-10-06)**: 공개 소스 revision `1fc35090fa9c359bc96d1287fbc32f733acaa7e4`의 영상·프롬프트·공용 변환과 관련 모듈/시험을 반영했다. 기반 버전/commit은 기존 산출물 호환성 때문에 v2.12.1로 유지하고 `qualityVersion: 2.34.0` 및 파일별 upstream/fork 해시를 추가했다. 공용 설치 스킬은 읽기만 했다.

   - `util/resample`, `video/align/rife/gait_fallback/local_cycle/loop/frames/canvas`, `frames/decontam`: 공용 색/알파 변환, 보간 손상 대체, 대응 포즈 크기 보정과 여백, 보수적인 가장자리 보정. 가장자리 보호가 decontam 내부로 이동했으므로 해당 회귀도 실제 새 경로를 검사한다.
   - `video/period/held/legs/body_plan`, `gen/handedness/prompt_parts/prepare/chroma`: 주기·그림 갱신·체형·장비 좌우·구도 가이드·원본 알파 판정. 앱 연결 및 실제 검증은 [적용 결과](../docs/product/LATEST_SKILL_UPGRADE_2026-10-06.md)에 구분한다.
   - `gen/__init__`의 접수 불명 timeout 재시도는 다시 제거했다. `gen/codex_provider`의 프로젝트 인증 격리, cyan 키 제거, 등록 시트 행 제한을 유지한다. 앱 adapter 1.3.0은 가이드 참조와 정확한 전송 프롬프트를 snapshot에 남기고 엔진의 중복 가이드 추가를 끈다.
   - 레이어·씬·아틀라스·시트 변환과 CLI 등록도 갱신했다. follow-through, marker 장비 QA, 외부 영상 프롬프트는 엔진/CLI 지원이며 앱 메뉴 전체 연결을 뜻하지 않는다.
   - 앱 걷기 기본값은 최신 엔진의 32장과 다르게 사용자 지정 **8장**이다. 기존 GIF 마무리·nearest 픽셀 편집·원본 시간은 보존한다. 앱의 WebP exact 수정은 `alignment/animation_exports.py`에서 별도로 구현했다.

   검증: 엔진 관련 9,211 PASS / 1 SKIP, 앱 통합 652 PASS, 웹 282 PASS와 production build 성공. 실제 보존 MP4 3개를 8장으로 추출했고 별도 실제 RIFE 보간 11장/손상 원본 대체 13장을 확인했다. 추가 생성 호출은 0건이다. `doctor.py`는 기존 inventory와 신규 patch 경로의 합집합 407개 파일을 검사한다.

## M1 복구 경계 (2026-10-22)

`gen/video.py`의 `http_download`에 선택 timeout/deadline·시도 계수 callback을 추가하고 `gen/xai.py`에 앱 전용 절대 수신 deadline을 추가했다. socket의 매 수신 전에 남은 시간을 적용해 느린 header/body도 예산을 공유한다. 기존 독립 CLI는 deadline을 생략하여 기존 transport를 유지한다. 앱 adapter가 GET 재시도·전체 잔여 시간·MP4 검사를 담당한다. 기존 POST 1회·기반 pin·`qualityVersion`은 유지하며 v2.45.3 전체 이식으로 표시하지 않는다. MP4 게시는 고정 `.part` 대신 독점 `mkstemp`·fsync·replace를 사용하고 실패 임시 파일을 정리한다. 최종 출력 symlink는 거절하여 다른 원본을 따라가지 않는다. 현재 해시는 lock의 `patches`·`localAdaptations`, M0 당시 해시는 `m0-port-plan.json`·`m0-function-plan.json`·`m0-baseline-manifest.json`에 보존한다.

## M2 영상 helper 묶음 (2026-10-22)

고정 v2.45.3 `59b2738a2e76ed7043d9691a230396ed6374a336`의 loop/align/repair/rife/frames와 crossings/interpolation_quality, gait·period·motion·evidence·source 및 필요한 공용 resample/lsq/GIF helper를 선별 반영했다. source는 loop/align의 출처 영수증 전이 의존이며 M3 복원 UI를 제공했다는 뜻이 아니다. 기반 pin·`qualityVersion=2.34.0`과 M1 gen/video·xai 보호 패치를 유지하고 이 부분은 `videoQualityVersion=2.45.3-m2`로 구분한다. 공용 sprite-gen과 전역 설정은 변경하지 않는다.

앱은 기존 선택→보정→주기맞춤→정규화→마무리→worker 저장 경로를 사용한다. 실제 소스 digest와 새 VERSION으로 구 작업의 최신 처리 재개를 막으며 완성 결과 저장 복구를 유지한다. RIFE Cache와 입력/품질 helper를 재사용하고 앱 전용 context의 절대 deadline·취소/TTA, cache symlink·손상/쓰기 실패 경계 및 repair/overlap 검색 확인을 로컬 적응했다. 새 TTA/overlap은 off 기본값·명시 opt-in이다. 현재/이식/원본 해시와 관련 시험은 `engine-lock.json.localAdaptations[M2]`를 기준으로 검사한다. 실제 검증·미검증은 M2 구현 보고서에 기록한다.


## M3 비교·원본 복원·follow 검사 (2026-10-22)

같은 고정 v2.45.3 commit의 compare/restoration/playback/follow/follow_inspect와 해당 5개 시험 묶음을 추가·선별 반영한다. 기존 follow 시험은 삭제하지 않는다. body_motion의4번째 worn 결과와 그룹별 move_regions 호출 계약을 앱에서 적응한다. 기존 기반pin/qualityVersion·M1 transport·M2 원본보호를 유지하며 `clipToolsQualityVersion=2.45.3-m3`로 식별한다. 앱 source bridge는 별도 policy이며 canonical 가변시간·원본 keyed 재투영·최초 origin·복원chain·캡의 정확한 좌표 조건을 검사한다. 엔진 전체 CLI의 나머지 기능을 흡수 완료로 표시하지 않는다. 현재 해시는 `localAdaptations[M3]`를 따른다.
