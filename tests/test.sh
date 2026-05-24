#!/bin/bash
mkdir -p /logs/verifier
python3 /app/runtime/run_reconciler.py
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
set +e
python3 -m pytest -v "${SCRIPT_DIR}/test_drift.py"
TEST_EXIT=$?
set -e
if [ "$TEST_EXIT" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
cat /logs/verifier/reward.txt
exit "$TEST_EXIT"
