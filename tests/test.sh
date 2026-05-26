#!/bin/bash
# Layout Engine Repair — Test harness

mkdir -p /logs/verifier

# Run the layout engine to produce output if not already present
if [ ! -f /app/runtime/output/layout_result.json ]; then
    cd /app/runtime && python3 run_layout.py || true
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

set +e
uv run --with pytest pytest -v "${SCRIPT_DIR}/test_layout.py" 2>&1 | tee /logs/verifier/output.log
TEST_EXIT=${PIPESTATUS[0]}
set -e

if [ "$TEST_EXIT" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi

cat /logs/verifier/reward.txt

exit "$TEST_EXIT"
