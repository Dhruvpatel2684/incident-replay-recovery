#!/bin/bash
set -euo pipefail
mkdir -p /logs/verifier
if [ ! -f /app/runtime/vault_output.json ] || [ ! -f /app/runtime/vault_stats.json ]; then
    python3 /app/runtime/vault.py
fi
set +e
uv run --with pytest pytest /tests/test_vault.py -v --tb=short
TEST_EXIT=$?
set -e
if [ "$TEST_EXIT" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
cat /logs/verifier/reward.txt
exit "$TEST_EXIT"
