#!/bin/bash
# Priority Task Scheduler — Test harness
# Runs the scheduler if output doesn't exist, then validates with pytest

mkdir -p /logs/verifier

# Run the scheduler to produce output if not already present
if [ ! -f /app/runtime/output/execution_plan.json ]; then
    python3 /app/runtime/run_scheduler.py || true
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

set +e
uv run --with pytest pytest -v "${SCRIPT_DIR}/test_scheduler.py" 2>&1 | tee /logs/verifier/output.log
TEST_EXIT=${PIPESTATUS[0]}
set -e

if [ "$TEST_EXIT" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi

cat /logs/verifier/reward.txt

exit "$TEST_EXIT"
