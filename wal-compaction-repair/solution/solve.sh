#!/bin/bash
set -e
# Run the broken compaction engine to produce initial output
python3 /app/runtime/compaction_engine.py
# Re-process WAL segments with correct visibility, ordering,
# tombstone handling, and sorted fingerprint computation
python3 /solution/repair_compaction.py
