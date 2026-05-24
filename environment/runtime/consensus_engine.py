"""
Consensus Engine - Main Entrypoint
Orchestrates replay of cluster consensus logs and produces output files.

Usage: python3 consensus_engine.py

Reads: cluster_logs.txt (raw cluster communication log)
Produces:
  - cluster_state.jsonl (per-node final state, one JSON record per line)
  - integrity.json (summary statistics and consistency hash)
"""

import os
import sys

# Ensure runtime directory is on the path
RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RUNTIME_DIR)

from log_parser import load_events
from state_machine import ClusterStateMachine
from output_formatter import format_output


# Node IDs in the cluster
CLUSTER_NODES = ["node-1", "node-2", "node-3"]

# Output directory (same as runtime dir)
OUTPUT_DIR = RUNTIME_DIR


def main():
    """Main execution: parse logs, replay through state machine, write output."""

    # Load and parse all events from the cluster log
    log_path = os.path.join(RUNTIME_DIR, "cluster_logs.txt")
    events = load_events(log_path)

    print(f"Loaded {len(events)} events from cluster log")

    # Initialize the cluster state machine
    sm = ClusterStateMachine(CLUSTER_NODES)

    # Replay all events through the state machine
    for event in events:
        sm.process_event(event)

    # Get final cluster state
    cluster_state = sm.get_cluster_state()
    election_history = sm.get_election_history()

    print(f"Replay complete. {len(election_history)} elections processed.")
    print(f"Total commits tracked: {sm.total_commits}")

    # Format and write output
    jsonl_path, integrity_path = format_output(
        cluster_state=cluster_state,
        election_history=election_history,
        total_commits=sm.total_commits,
        total_nodes=sm.total_nodes,
        output_dir=OUTPUT_DIR,
    )

    print(f"Output written:")
    print(f"  - {jsonl_path}")
    print(f"  - {integrity_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
