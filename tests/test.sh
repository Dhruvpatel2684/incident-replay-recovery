#!/usr/bin/env bash
set -euo pipefail

# Generate the build plan if it doesn't exist
if [ ! -f /app/runtime/output/build_plan.json ]; then
    python3 /app/runtime/run_orchestrator.py
fi

# Run the test suite
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 -m pytest "${SCRIPT_DIR}/test_build_plan.py" -v --tb=short 2>&1

# Determine pass/fail based on pytest exit code
if python3 -m pytest "${SCRIPT_DIR}/test_build_plan.py" --tb=no -q > /dev/null 2>&1; then
    echo "1" > "${SCRIPT_DIR}/reward.txt"
else
    echo "0" > "${SCRIPT_DIR}/reward.txt"
fi
