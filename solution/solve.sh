#!/usr/bin/env bash
set -euo pipefail

# Step 1: Run the orchestrator to produce the (buggy) initial output
# This generates build_plan.json with incorrect analysis results
python3 /app/runtime/run_orchestrator.py

# Step 2: Apply the repair to graph_analyzer.py
# Fixes three interacting bugs:
#   - are_independent: adjacency check -> BFS reachability (transitive closure)
#   - compute_priority: out-degree -> longest path to terminal (critical path length)
#   - find_parallel_set: descending greedy -> widest topological layer (maximum antichain)
python3 /app/solution/repair_orchestrator.py

# Step 3: Remove stale output so the orchestrator regenerates with fixed code
rm -f /app/runtime/output/build_plan.json

# Step 4: Re-run the orchestrator with the repaired graph analyzer
python3 /app/runtime/run_orchestrator.py
