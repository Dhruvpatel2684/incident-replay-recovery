#!/bin/bash
set -e

# Step 1: Run the broken entrypoint to generate initial (incorrect) state files.
# This ensures cluster_state.jsonl and integrity.json exist before repair.
python3 /app/runtime/consensus_engine.py

# Step 2: Run the repair script (/solution/repair_consensus.py) which performs
# a full re-processing of /app/runtime/cluster_logs.txt from scratch.
#
# The repair script fixes 7 bugs across 3 modules:
#   - log_parser.py: Fixes VOTE_REQUEST term extraction (removes off-by-one)
#                    and restores full microsecond timestamp precision
#   - state_machine.py: Resets vote counters after elections, counts commits
#                       per-event not per-node, uses prev_log_idx+1 for
#                       follower log positioning
#   - output_formatter.py: Sorts nodes for deterministic hash computation,
#                          corrects quorum threshold to (n//2)+1
#
# It re-parses all 54 events, replays them through a corrected state machine,
# then writes cluster_state.jsonl and integrity.json with correct values.
python3 /solution/repair_consensus.py
