#!/bin/bash

mkdir -p /logs/verifier

if [ ! -f /app/runtime/replay_state.db ]; then
    python3 /app/runtime/run_replay.py
fi

if python3 -m pytest -v /app/tests/test_replay.py; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
