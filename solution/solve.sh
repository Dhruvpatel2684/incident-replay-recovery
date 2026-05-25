#!/bin/bash
# Git Object Store Repair — Oracle solution
#
# Executes repair script that recomputes all hashes from ground truth
# source files, rebuilds the complete object graph with correct
# cascading dependencies, then runs verifier for clean report.

set -e

cd /app

# Run repair (rebuilds all objects, refs, index from source_files/)
python3 /solution/repair_store.py

# Run verifier to produce integrity_report.json
python3 /app/runtime/run_store.py
