#!/usr/bin/env bash
# =============================================================================
# Certificate Chain Auditor - Test Runner
# =============================================================================
# Cascade gate: only runs the auditor if output doesn't already exist.
# Then runs pytest to validate the output files.
# Writes reward.txt with 1 (pass) or 0 (fail).
# =============================================================================

set -e

# Cascade gate: conditionally run the runtime if output doesn't exist
if [ ! -f /app/runtime/output/audit_report.jsonl ]; then
    echo "[TEST] Output not found, running auditor..."
    python3 /app/runtime/run_auditor.py
fi

echo "[TEST] Running test suite..."

# Run pytest and capture exit code
mkdir -p /logs/verifier
if python3 -m pytest /tests/test_chain.py -v --tb=short 2>&1; then
    echo "1" > /logs/verifier/reward.txt
    echo "[TEST] PASSED - reward: 1"
else
    echo "0" > /logs/verifier/reward.txt
    echo "[TEST] FAILED - reward: 0"
fi
