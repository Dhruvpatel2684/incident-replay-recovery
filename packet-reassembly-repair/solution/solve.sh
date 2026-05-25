#!/bin/bash
set -e

# Step 1: Run the broken entrypoint to generate initial (incorrect) output files.
# This ensures sessions.jsonl and reassembly_stats.json exist before repair.
python3 /app/runtime/reassembler.py

# Step 2: Run the repair script which performs a full re-processing of
# /app/runtime/capture.fragments from scratch with corrected logic.
#
# The repair script fixes 7 bugs across 3 modules:
#   - fragment_parser.py: Removes erroneous +1 on FIN offset, removes -1
#                         on LAST_FRAGMENT payload_len
#   - reassembly_engine.py: Moves byte counting after dedup check (only new
#                           fragments), fixes RTT timestamp direction (new - old),
#                           removes FIN byte inflation
#   - session_writer.py: Sorts sessions for deterministic checksum, corrects
#                        bloom filter FPR denominator to (sessions + fragments)
#
# It re-parses all 47 fragments, reassembles through a corrected engine,
# then writes sessions.jsonl and reassembly_stats.json with correct values.
python3 /solution/repair_reassembly.py
