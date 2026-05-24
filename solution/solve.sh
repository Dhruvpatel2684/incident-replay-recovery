#!/bin/bash
set -e

# Step 1: Run the broken entrypoint to generate initial (incorrect) state files
# This ensures cluster_state.jsonl and integrity.json exist before repair
python3 /app/runtime/consensus_engine.py

# Step 2: Run the repair script which re-processes the raw log data
# with corrected logic across all modules (parser, state machine, formatter)
# and overwrites the output files with correct results
python3 /solution/repair_consensus.py
