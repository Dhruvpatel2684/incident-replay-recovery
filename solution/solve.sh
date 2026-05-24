#!/bin/bash
set -e

cd /app

python3 runtime/run_replay.py
python3 solution/reconcile_runtime.py
