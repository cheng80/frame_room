# sprite-gen 2.12.1 제품 포크

Upstream: https://github.com/aldegad/sprite-gen · v2.12.1 · b058341f7543f3adcbea227bd4e6b7587895b1bc

연구 보존 tarball의 SHA-256을 baseline.json과 비교한 뒤 360개 원본 파일을 추출했다. LICENSE, NOTICE, 각 SPDX 고지는 변경하지 않았다. 공용 skill 설치는 import/실행/수정하지 않는다.

수정:

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
