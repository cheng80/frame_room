# Provider adapter 통합

`engine/sprite-gen/.venv/bin/python`으로 repository root에서 import한다.

```python
from adapters.spritegen.provider import providers, generate, ProviderError

# 계정 로그인 상태만 확인. 이미지 생성 없음.
capabilities = providers()

# 실제 호출은 단일 worker의 독립 process group 안에서만 실행한다.
# generate(params, approved_reference, asset_path, attempt_output_dir, regeneration_target=target_or_none)
```

- `providerId='codex'` 명시 필수. `model`은 Codex agent 모델이며 이미지 모델 ID가 아니다. 기본 `gpt-6-sol`, 로컬 Codex catalog의 GPT 모델만 허용한다. 계정의 실제 image_gen 가능 여부는 생성 전 증명되지 않는다.
- native alpha는 프롬프트로 요청할 수 있다(`nativeAlphaRequest=true`). 참조 이미지가 있으면 불안정하며 투명 출력은 보장하지 않는다. 원격 취소와 결과 조회는 지원하지 않는다(`remoteCancel=false`, `resultLookup=false`).
- `background=transparent`는 진짜 PNG alpha와 체커보드 금지를 명시한다. white/green/magenta는 각각 #FFFFFF/#00FF00/#FF00FF 균일 배경을 요청한다. snapshot의 `requestedNativeAlpha`는 요청 사실이며 receipt의 `alphaStats`(transparent/partial/opaque 픽셀 수), `alphaChannelPresent`는 실제 PNG 측정이다. RGB 또는 불투명 결과도 실패로 숨기거나 재생성하지 않는다.
- `quality`, `resolution`, `aspectRatio`는 Codex 전송 API가 지원하지 않아 `None`/빈 값만 허용한다. `auto`도 지원한다고 주장하지 않는다.
- `scope='states'`(기본), `'sheet'`, `'frame'`을 받는다. frame scope는 frameCount=1. frameCount 1–24는 한 PNG 안에 요청하는 포즈 수이며 API 반환 이미지 장수가 아니다. 실제 포즈 수는 추출·검수 전 `null`이다.
- frame scope에는 `regeneration_target={frameVersionId,imageAssetId,sha256}` keyword 인자가 필수다. worker가 저장된 job snapshot에서 프레임과 crop asset을 찾고 SHA-256을 전달한다. 선택적 `rawAssetId`, `sourceRect`도 snapshot에 보존한다. 대상 누락·frameVersionId 불일치·hash 불일치는 전송 전에 차단한다. `requestSnapshot.regenerationTarget`은 params/reference와 별도로 기록한다.
- identity → style → pose → regeneration-target 순서로 원본 참조의 작업 사본을 첨부한다. roles·fixedTraits·allowedChanges·forbiddenTransfers·facing·background를 프롬프트에 전달한다. regeneration-target은 선택 프레임의 실제 crop bytes이며 해당 포즈/action 재생성의 기준이다. identity와 고정 외형이 target보다 우선하며 다른 pose 참조는 보조임을 prompt에 명시한다. crop을 다시 resize/fit하지 않는다. 픽셀/체형/알파 보장은 후속 검수가 담당한다.
- `gen.generate_image('codex', ...)`만 호출한다. `gen-set`의 기본 동시성 6, default-provider fallback, facing 재생성, chroma 제거, trim은 이 경로에서 사용하지 않는다. 이미지 원본을 유지한다.
- Codex child는 argv 배열/stdin으로 실행하며 셸 평가나 별도 process group을 만들지 않는다. worker가 group의 취소/종료/수거를 소유한다. engine timeout은 `SPRITE_GEN_GEN_TIMEOUT_SECONDS`(기본180초)이며 timeout 재전송은 제거했다.
- `--ignore-user-config`, 명시 `model_provider=openai`, `forced_login_method=chatgpt`로 구독 경로를 고정한다. API 키와 base URL 및 부모 thread 환경변수를 자식에서 제거한다. 실제 readiness도 ChatGPT 로그인 문자열을 요구한다.
- 실패: 로컬 validation/login은 `outcome_unknown=False`; engine 진입 후 timeout/비정상 종료/결과 해석 오류는 `ProviderError.code='provider.outcome_unknown'`, `.outcome_unknown=True`. `.retryable=False`. UI 또는 worker에서 자동 재시도하지 않는다.
- `provider-attempt` 폴더를 독점 생성해 동일 디렉터리의 재호출을 거절한다. worker의 idempotency ledger를 대체하지 않는다. 중단 뒤 `submission.json`이 있으면 원격 접수 여부를 추정하지 않는다.

## 증거

작업별 `provider-attempt/`에 다음 원본을 남긴다.

- `request-snapshot.json`: 입력 params/reference, 역할별 참조 SHA-256, 사용자 prompt, 실제 enginePrompt, 고정 옵션.
- `transport-prompt.txt`: Codex stdin 원문.
- `codex-stdout.jsonl`, `codex-stderr.txt`: 전송 응답 원문; timeout 부분 stream 포함.
- `codex-rollout.jsonl`: 성공한 child session의 원본 rollout 복사본. `keep_session=True`로 원래 rollout도 유지.
- `raw.png`, `generated.png`, `generated.png.raw.png`: resize/keying하지 않은 PNG.
- `engine-receipt.json`: `GenResult.to_dict()` 그대로 저장. 절대 작업 경로가 포함된 로컬 감사 원본.
- `receipt.json`: public/portable receipt. image SHA-256, session, 시간, 요청/반환 수, 실제 크기.
- `failure.json`: 불명 결과에 대한 비밀정보 없는 오류 요약.

API/backup에는 반환 `receipt`/`requestSnapshot`만 사용한다. 원본 transport/rollout/engine-receipt는 로컬 작업 증거이며 전체를 브라우저 응답·로그·backup으로 노출하지 않는다. 로그인 probe는 lastSuccess를 추정하지 않는다. 앱 ledger가 실제 성공 receipt를 바탕으로 lastSuccess를 합성해야 한다.

## 검증

외부 생성을 호출하지 않았다. parent가 앱 worker 경로에서 실제 검증한다.

```sh
engine/sprite-gen/.venv/bin/python -m pytest -q tests/integration/test_provider.py engine/sprite-gen/tests/gen/test_gen.py engine/sprite-gen/tests/gen/test_codex_rollout_resolution.py -o cache_dir=engine/.pytest-cache --basetemp=engine/.combined-test-tmp
```

기존 Pillow getdata deprecation warning이 발생할 수 있다. 최신 실행 결과는 engine-lock.json validation에 기록한다. 전송 부분만 가짜로 대체한 real-engine 통합 테스트가 포함된다.
