"""
Report Writer — Compaction Output Generation
==============================================
Generates the compacted state file and compaction report with
statistics and a fingerprint for integrity verification.

The fingerprint is a SHA-256 digest of the compacted state that
allows downstream consumers to verify they have the correct
compacted output without comparing full state dumps.
"""

import json
import hashlib
import os
from typing import Dict, Set, Tuple, List


def write_compacted_state(state: Dict[str, str], output_path: str):
    """Write the compacted key-value state to a JSON file.
    
    Args:
        state: The final compacted state (key -> value as JSON string)
        output_path: Path to write the output file
    """
    # Parse JSON values back into objects for cleaner output
    parsed_state = {}
    for key, value in state.items():
        try:
            parsed_state[key] = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            parsed_state[key] = value
    
    with open(output_path, "w") as f:
        json.dump(parsed_state, f, indent=2, sort_keys=True)


def compute_compaction_fingerprint(state: Dict[str, str]) -> str:
    """Compute a SHA-256 fingerprint of the compacted state.
    
    The fingerprint provides a quick way to verify that compaction
    produced the expected output. It hashes the key-value pairs
    in a deterministic sorted order to produce a stable digest
    regardless of insertion order or serialization format.
    
    Canonical JSON normalization ensures hash stability across
    serialization variants (whitespace, key ordering, numeric
    formatting) that don't affect semantic equivalence.
    """
    hasher = hashlib.sha256()
    
    # Sort keys for deterministic iteration
    sorted_keys = sorted(state.keys())
    # Hash each key-value pair in canonical form
    for key in sorted_keys:
        raw_value = state[key] if state[key] else ""
        # Normalize to canonical JSON for format-independent hashing
        try:
            parsed = json.loads(raw_value)
            canonical_value = json.dumps(parsed, sort_keys=True, separators=(',', ':'))
        except (json.JSONDecodeError, TypeError):
            canonical_value = raw_value
        hasher.update(f"{key}={canonical_value}\n".encode("utf-8"))
    
    return hasher.hexdigest()[:16]


def write_compaction_report(
    state: Dict[str, str],
    metadata: Dict[str, Tuple[str, int, int, str]],
    live_keys: Set[str],
    deleted_keys: Set[str],
    total_txns: int,
    committed_count: int,
    aborted_count: int,
    total_operations: int,
    fingerprint: str,
    output_path: str
):
    """Write the compaction report with statistics.
    
    Args:
        state: Final compacted state
        metadata: Key metadata from state builder
        live_keys: Set of live key names
        deleted_keys: Set of deleted (tombstoned) key names
        total_txns: Total number of transactions processed
        committed_count: Number of committed transactions
        aborted_count: Number of aborted transactions  
        total_operations: Total data operations processed
        fingerprint: Compaction fingerprint hash
        output_path: Path to write the report
    """
    report = {
        "compaction_summary": {
            "total_transactions": total_txns,
            "committed_transactions": committed_count,
            "aborted_transactions": aborted_count,
            "total_data_operations": total_operations,
        },
        "state_summary": {
            "live_key_count": len(live_keys),
            "deleted_key_count": len(deleted_keys),
            "keys": sorted(list(live_keys)),
        },
        "compaction_fingerprint": fingerprint,
    }
    
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
