#!/bin/bash
set -euo pipefail

mkdir -p /logs/verifier

if [ ! -f /app/runtime/replay_state.db ]; then
    python3 /app/runtime/run_replay.py
fi

set +e
python3 -m pytest -v /tests/test_replay.py
TEST_EXIT=$?
set -e

if [ "$TEST_EXIT" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi

cat /logs/verifier/reward.txt

exit "$TEST_EXIT"
