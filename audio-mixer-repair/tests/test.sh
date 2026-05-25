#!/bin/bash
set -euo pipefail

mkdir -p /logs/verifier

# Run the mixer to generate output
python3 /app/runtime/mixer.py /app/runtime/mix_session.json

# Run pytest validation using uv
set +e
uv run --with pytest pytest /tests/test_mixer.py -v --tb=short
TEST_EXIT=$?
set -e

if [ "$TEST_EXIT" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi

cat /logs/verifier/reward.txt
exit "$TEST_EXIT"
