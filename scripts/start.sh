#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
PY="$PWD/engine/sprite-gen/.venv/bin/python"
if [ ! -x "$PY" ] || [ ! -f apps/web/dist/index.html ]; then
  echo '먼저 scripts/setup.sh를 실행하세요.' >&2
  exit 1
fi
exec "$PY" scripts/launch.py
