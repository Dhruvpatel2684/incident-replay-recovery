#!/bin/bash
set -e

mkdir -p /logs/verifier

cd /app/runtime && python3 run_layout.py

cd /tests
if uv run --with pytest pytest test_layout.py -v 2>&1 | tee /logs/verifier/test_output.txt; then
    echo "1" > /logs/verifier/reward.txt
else
    echo "0" > /logs/verifier/reward.txt
fi
