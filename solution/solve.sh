#!/bin/bash
# Git Object Store Repair — Oracle solution
#
# Executes repair script that extracts metadata from corrupted commits,
# reads source files for current state, identifies historical blobs,
# rebuilds the complete object graph, then runs verifier for clean report.

set -e

cd /app

# Run repair (rebuilds all objects, refs, index)
python3 /solution/repair_store.py

# Run verifier to produce integrity_report.json
python3 /app/runtime/run_store.py
