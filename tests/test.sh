#!/bin/bash
# Git Object Store Repair — Test harness
# Runs verifier to produce integrity report, then validates with pytest

mkdir -p /logs/verifier

# Run the store verifier to produce integrity report if not already present
if [ ! -f /app/runtime/output/integrity_report.json ]; then
    python3 /app/runtime/run_store.py || true
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

set +e
uv run --with pytest pytest -v "${SCRIPT_DIR}/test_store.py" 2>&1 | tee /logs/verifier/output.log
TEST_EXIT=${PIPESTATUS[0]}
set -e

if [ "$TEST_EXIT" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi

cat /logs/verifier/reward.txt

exit "$TEST_EXIT"
