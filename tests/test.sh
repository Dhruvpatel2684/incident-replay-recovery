#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure output directories exist
mkdir -p /logs/verifier /output

# Run allocator if output doesn't exist yet
if [ ! -f /output/assignments.json ]; then
    echo "Running allocator..."
    python3 /app/runtime/run_allocator.py 2>&1 || true
fi

# Run tests
echo "Running verification tests..."
uv run --with pytest pytest -v "${SCRIPT_DIR}/test_allocator.py" 2>&1 | tee /logs/verifier/output.log
TEST_EXIT=${PIPESTATUS[0]}

# Write reward
if [ "$TEST_EXIT" -eq 0 ]; then
    echo "1" > /logs/verifier/reward.txt
    echo "All tests passed."
else
    echo "0" > /logs/verifier/reward.txt
    echo "Some tests failed."
fi

exit $TEST_EXIT
