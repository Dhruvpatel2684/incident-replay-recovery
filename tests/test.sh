#!/bin/bash
set -e

cd /app

python3 runtime/run_replay.py

mkdir -p /logs/verifier

if python3 -m pytest tests/test_replay.py -v; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
