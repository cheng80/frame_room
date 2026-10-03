#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v uv >/dev/null || { echo 'uv가 필요합니다: https://docs.astral.sh/uv/getting-started/installation/'; exit 1; }
command -v npm >/dev/null || { echo 'Node.js와 npm을 설치하세요.'; exit 1; }
if [ ! -x engine/sprite-gen/.venv/bin/python ]; then
  uv venv --python 3.12 engine/sprite-gen/.venv
fi
uv pip sync --python engine/sprite-gen/.venv/bin/python engine/requirements.lock.txt
npm --prefix apps/web ci
npm --prefix apps/web run build
engine/sprite-gen/.venv/bin/python scripts/package-guide.py
engine/sprite-gen/.venv/bin/python scripts/doctor.py
echo '설치 완료. 프레임룸 실행.command 또는 scripts/start.sh로 실행하세요.'
