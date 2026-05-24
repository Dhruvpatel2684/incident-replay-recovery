#!/bin/bash
set -euo pipefail

mkdir -p /logs/verifier

# Run the entrypoint if output doesn't exist yet
if [ ! -f /app/runtime/cluster_state.jsonl ]; then
    python3 /app/runtime/consensus_engine.py
fi

set +e
python3 -m pytest -v /tests/test_consensus.py
TEST_EXIT=$?
set -e

if [ "$TEST_EXIT" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi

cat /logs/verifier/reward.txt
exit "$TEST_EXIT"
