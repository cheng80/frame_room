#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec engine/sprite-gen/.venv/bin/python scripts/launch.py --dev
