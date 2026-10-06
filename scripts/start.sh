#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
PY="$PWD/engine/sprite-gen/.venv/bin/python"
if ! command -v node >/dev/null || ! command -v npm >/dev/null; then
  echo 'Node.js와 npm을 설치한 뒤 다시 실행하세요.' >&2
  exit 1
fi

if [ ! -x "$PY" ] || ! "$PY" -c 'import fastapi, uvicorn, PIL, numpy, sprite_gen, python_multipart, httpx' >/dev/null 2>&1; then
  if ! command -v uv >/dev/null; then
    echo 'Python 실행 환경 준비에 uv가 필요합니다: https://docs.astral.sh/uv/getting-started/installation/' >&2
    exit 1
  fi
  echo 'Python 실행 환경을 준비합니다.'
  if [ ! -x "$PY" ]; then
    uv venv --python 3.12 engine/sprite-gen/.venv
  fi
  uv pip sync --python "$PY" engine/requirements.lock.txt
fi
"$PY" scripts/doctor.py

NEEDS_BUILD=0
if [ ! -d apps/web/node_modules ] || ! npm --prefix apps/web ls --depth=0 --include=dev >/dev/null 2>&1 \
  || [ ! -x apps/web/node_modules/.bin/tsc ] || [ ! -x apps/web/node_modules/.bin/vite ]; then
  echo 'npm 의존성이 없거나 불완전합니다. npm install을 실행합니다.'
  npm --prefix apps/web install --include=dev
  NEEDS_BUILD=1
fi

if [ "$NEEDS_BUILD" -eq 1 ] || [ ! -f apps/web/dist/index.html ]; then
  echo '웹 앱을 빌드합니다.'
  npm --prefix apps/web run build
  "$PY" scripts/package-guide.py
fi

echo '실행 환경 준비 완료. 프레임룸을 시작합니다.'
exec "$PY" scripts/launch.py
