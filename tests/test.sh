#!/bin/bash
set -e

# Run the pipeline if output doesn't exist yet (NOP scenario)
if [ ! -f /app/runtime/output/pipeline_output.jsonl ]; then
    python3 /app/runtime/run_pipeline.py
fi

# Run pytest and capture result
python3 -m pytest /tests/test_pipeline.py -v --tb=short 2>&1 | tee /logs/verifier/test_output.txt
TEST_EXIT=${PIPESTATUS[0]}

# Write reward
if [ $TEST_EXIT -eq 0 ]; then
    echo "1.0" > /logs/verifier/reward.txt
else
    echo "0.0" > /logs/verifier/reward.txt
fi

exit $TEST_EXIT
