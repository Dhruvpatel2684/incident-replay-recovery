#!/bin/bash
set -e

python3 /app/runtime/run_replay.py
python3 /solution/reconcile_runtime.py
