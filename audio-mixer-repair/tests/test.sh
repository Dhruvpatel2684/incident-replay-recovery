#!/bin/bash
# test.sh - Run the mixer pipeline and then execute validation tests
# Expected to run inside the Docker container with /app as WORKDIR

set -e

# Run the mixer to generate output
python3 /app/runtime/mixer.py /app/runtime/mix_session.json

# Run pytest validation using uv
uv run --with pytest pytest /app/tests/test_mixer.py -v --tb=short

echo "[test] All tests completed."
