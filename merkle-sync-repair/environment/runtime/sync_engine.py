"""
Anti-entropy sync engine entry point.

Orchestrates the full synchronization pipeline:
1. Load replica state from JSON fixtures
2. Build Merkle trees for each replica
3. Detect divergent keys via tree comparison
4. Resolve conflicts for divergent keys
5. Build merged state and write output

This module is correct - bugs are in the component modules.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from replica_state import load_all_replicas, get_all_keys
from merkle_tree import MerkleTree
from diff_detector import DiffDetector
from conflict_resolver import ConflictResolver
from output_writer import write_output


def main():
    # Step 1: Load all replicas
    replicas = load_all_replicas()

    # Step 2: Build Merkle trees
    trees = {}
    for replica_id, data in replicas.items():
        trees[replica_id] = MerkleTree(data)

    # Step 3: Detect divergent keys
    detector = DiffDetector()
    divergent_keys = detector.detect_all_divergent_keys(trees)

    # Step 4: Get total unique keys across all replicas
    all_keys = get_all_keys(replicas)
    total_keys_seen = len(all_keys)

    # Step 5: Resolve conflicts for divergent keys
    resolver = ConflictResolver()
    resolved_entries = resolver.resolve_divergent_keys(divergent_keys, replicas)

    # Step 6: Build merged state
    # Start with keys that are identical across all replicas (not in divergent set)
    merged_state = {}
    identical_keys = all_keys - divergent_keys

    for key in identical_keys:
        # Pick from any replica that has it (they're all the same)
        for replica_id, data in replicas.items():
            if key in data:
                entry = data[key]
                if not entry.get("tombstone"):
                    merged_state[key] = entry["value"]
                break

    # Add resolved entries
    for key, entry in resolved_entries.items():
        merged_state[key] = entry["value"]

    # Step 7: Build sync operations log
    sync_operations = []
    for key in sorted(divergent_keys):
        if key in resolved_entries:
            # Determine which replica was the source
            resolved_value = resolved_entries[key]["value"]
            source = "unknown"
            for replica_id, data in sorted(replicas.items()):
                if key in data and data[key]["value"] == resolved_value:
                    source = replica_id
                    break
            sync_operations.append({
                "key": key,
                "action": "resolve",
                "source_replica": source
            })
        else:
            # Key was divergent but resolved to deletion (tombstone won)
            sync_operations.append({
                "key": key,
                "action": "delete",
                "source_replica": "tombstone"
            })

    # Step 8: Write output
    conflicts_resolved = len([op for op in sync_operations
                              if op["action"] == "resolve"])
    write_output(
        merged_state=merged_state,
        total_keys_seen=total_keys_seen,
        divergent_keys_detected=len(divergent_keys),
        conflicts_resolved=conflicts_resolved,
        sync_operations=sync_operations
    )


if __name__ == "__main__":
    main()
