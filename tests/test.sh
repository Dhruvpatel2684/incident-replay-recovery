#!/bin/bash
# =============================================================================
# Firewall Rule Compiler - Test Runner
# =============================================================================
# Runs the compiler if output doesn't exist, then executes the test suite.
# Writes pass/fail reward to /logs/verifier/reward.txt
# =============================================================================

# Ensure output exists — run the compiler if output file is missing
if [ ! -f /app/runtime/output/compiled_rules.txt ]; then
    echo "[test] Output not found, running compiler..."
    cd /app
    python3 -m runtime.run_compiler
fi

# Create log directory
mkdir -p /logs/verifier

# Run pytest and capture exit code
echo "[test] Running test suite..."
cd /tests
python3 -m pytest test_rules.py -v --tb=short > /logs/verifier/test_output.txt 2>&1
TEST_EXIT=$?

if [ $TEST_EXIT -eq 0 ]; then
    echo "1.0" > /logs/verifier/reward.txt
    echo "[test] ALL TESTS PASSED"
else
    echo "0.0" > /logs/verifier/reward.txt
    echo "[test] SOME TESTS FAILED"
fi

cat /logs/verifier/test_output.txt
exit $TEST_EXIT
