#!/bin/bash

mkdir -p /logs/verifier

if [ ! -f /app/runtime/output/integrity_report.json ]; then
    python3 /app/runtime/run_store.py || true
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

set +e
python3 -m pytest -v "${SCRIPT_DIR}/test_store.py"
TEST_EXIT=$?
set -e

if [ "$TEST_EXIT" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi

cat /logs/verifier/reward.txt

exit "$TEST_EXIT"
