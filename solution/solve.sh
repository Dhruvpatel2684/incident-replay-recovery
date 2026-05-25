#!/bin/bash
set -e

# First run the pipeline to generate initial (corrupted) output if not present
if [ ! -f /app/runtime/output/pipeline_output.jsonl ]; then
    python3 /app/runtime/run_pipeline.py
fi

# Run the repair script which fixes state and re-runs the pipeline
python3 /solution/repair_pipeline.py
