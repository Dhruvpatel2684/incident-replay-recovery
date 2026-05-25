"""
Output writer for the anti-entropy sync engine.

Writes the merged sync result and a statistics report to JSON files
in the runtime directory.
"""

import hashlib
import json
import os


RUNTIME_DIR = "/app/runtime"


def compute_integrity_hash(merged_state):
    """Compute SHA-256 integrity hash of the sorted merged state.

    Format: for each key in sorted order, append 'key=json.dumps(value, sort_keys=True)\n'
    Returns first 16 hex characters of the SHA-256 hash.
    """
    lines = []
    for key in sorted(merged_state.keys()):
        value_str = json.dumps(merged_state[key], sort_keys=True)
        lines.append(f"{key}={value_str}\n")
    content = "".join(lines)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def write_output(merged_state, total_keys_seen, divergent_keys_detected,
                 conflicts_resolved, sync_operations):
    """Write sync_result.json and sync_report.json to the runtime directory.

    Args:
        merged_state: dict mapping key -> value (the final merged KV store)
        total_keys_seen: count of unique keys across all replicas
        divergent_keys_detected: count of divergent keys from diff detection
        conflicts_resolved: count of keys that needed conflict resolution
        sync_operations: list of operation dicts (key, action, source_replica)
    """
    # Write sync result (key -> value mapping)
    result_path = os.path.join(RUNTIME_DIR, "sync_result.json")
    with open(result_path, "w") as f:
        json.dump(merged_state, f, indent=2, sort_keys=True)

    # Compute integrity hash
    integrity_hash = compute_integrity_hash(merged_state)

    # Write sync report
    report = {
        "replicas_processed": 3,
        "total_keys_seen": total_keys_seen,
        "divergent_keys_detected": divergent_keys_detected,
        "conflicts_resolved": conflicts_resolved,
        "sync_operations": sync_operations,
        "integrity_hash": integrity_hash
    }

    report_path = os.path.join(RUNTIME_DIR, "sync_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
