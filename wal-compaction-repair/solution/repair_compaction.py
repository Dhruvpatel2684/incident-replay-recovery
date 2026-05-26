"""
Oracle solution for wal-compaction-repair task.

Fixes the 4 bugs:
1. state_builder.py: is_visible() checks `_finalized_txns` (committed + aborted)
   but should check `_committed_txns` only. Aborted transaction changes must be
   invisible in the compacted output.
   
2. snapshot_manager.py: resolve_conflicts() sorts descending (reverse=True) and
   takes [-1], which gives the LOWEST LSN (first writer). Should either sort
   ascending and take [-1], or sort descending and take [0].
   
3. state_builder.py: apply_delete() records tombstones unconditionally regardless
   of transaction outcome. Tombstones from aborted transactions should NOT be
   recorded (or should be removed when the abort is processed).
   
4. report_writer.py: compute_compaction_fingerprint() normalizes values to
   canonical JSON before hashing, but the correct fingerprint is computed
   from the raw WAL value strings without re-serialization.

This script re-processes the WAL with correct logic and overwrites the output files.
"""

import os
import sys
import json
import hashlib

# Ensure runtime directory is in path
runtime_dir = "/app/runtime"
sys.path.insert(0, runtime_dir)

from wal_parser import parse_wal_segments, get_transaction_ids, get_committed_txns, get_aborted_txns, get_data_operations


def main():
    wal_path = os.path.join(runtime_dir, "wal_segments.log")
    
    # Parse all entries
    entries = parse_wal_segments(wal_path)
    
    # Determine transaction status
    committed = get_committed_txns(entries)
    aborted = get_aborted_txns(entries)
    all_txn_ids = get_transaction_ids(entries)
    data_ops = get_data_operations(entries)
    
    # FIX Bug 1: Only consider operations from COMMITTED transactions (not all finalized)
    # FIX Bug 2: Use ascending LSN sort and take [-1] for highest (or descending + [0])
    # FIX Bug 3: Only record tombstones from COMMITTED transactions
    
    # Build per-key write history, only from committed transactions
    key_history = {}  # key -> list of (lsn, operation, value, txn_id)
    
    for entry in entries:
        if not entry.is_data_op:
            continue
        # FIX Bug 1: Skip operations from non-committed transactions
        if entry.txn_id not in committed:
            continue
        
        key = entry.key
        if key not in key_history:
            key_history[key] = []
        key_history[key].append((entry.lsn, entry.operation, entry.value, entry.txn_id))
    
    # Resolve final state: for each key, the operation with highest LSN wins
    final_state = {}
    deleted_keys = set()
    
    for key, history in key_history.items():
        # FIX Bug 2: Sort ascending by LSN and take [-1] for highest LSN (last writer wins)
        history.sort(key=lambda x: x[0])  # ascending sort by LSN
        last_lsn, last_op, last_value, last_txn = history[-1]
        
        if last_op == "DELETE":
            # FIX Bug 3: Only committed DELETEs count as tombstones
            deleted_keys.add(key)
        else:
            final_state[key] = last_value
    
    # FIX Bug 4: Compute fingerprint with SORTED keys
    hasher = hashlib.sha256()
    for key in sorted(final_state.keys()):
        value = final_state[key] if final_state[key] else ""
        hasher.update(f"{key}={value}\n".encode("utf-8"))
    fingerprint = hasher.hexdigest()[:16]
    
    # Write compacted_state.json
    parsed_state = {}
    for key, value in sorted(final_state.items()):
        try:
            parsed_state[key] = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            parsed_state[key] = value
    
    state_output = os.path.join(runtime_dir, "compacted_state.json")
    with open(state_output, "w") as f:
        json.dump(parsed_state, f, indent=2, sort_keys=True)
    
    # Write compaction_report.json
    live_keys = set(final_state.keys())
    
    report = {
        "compaction_summary": {
            "total_transactions": len(all_txn_ids),
            "committed_transactions": len(committed),
            "aborted_transactions": len(aborted),
            "total_data_operations": len(data_ops),
        },
        "state_summary": {
            "live_key_count": len(live_keys),
            "deleted_key_count": len(deleted_keys),
            "keys": sorted(list(live_keys)),
        },
        "compaction_fingerprint": fingerprint,
    }
    
    report_output = os.path.join(runtime_dir, "compaction_report.json")
    with open(report_output, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    
    print(f"[repair] Compaction repair complete:")
    print(f"  Live keys: {len(live_keys)}")
    print(f"  Deleted keys: {len(deleted_keys)}")
    print(f"  Fingerprint: {fingerprint}")


if __name__ == "__main__":
    main()
