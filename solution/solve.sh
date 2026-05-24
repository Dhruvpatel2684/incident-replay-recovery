#!/bin/bash
set -e

cd /app

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

python3 /app/runtime/run_replay.py
python3 "${SCRIPT_DIR}/reconcile_runtime.py"
