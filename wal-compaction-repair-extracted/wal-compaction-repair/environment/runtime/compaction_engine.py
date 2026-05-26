"""
WAL Compaction Engine — Main Orchestrator
==========================================
Reads WAL segments, replays operations to reconstruct state,
resolves conflicts, and produces the compacted output.

Pipeline:
    wal_segments.log → wal_parser → state_builder → snapshot_manager → report_writer
                                                                          ↓
                                              compacted_state.json + compaction_report.json

This file orchestrates the pipeline. It is correct — bugs are in the
downstream modules (state_builder, snapshot_manager, report_writer).
"""

import os
import sys

# Add runtime directory to path
runtime_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, runtime_dir)

from wal_parser import (
    parse_wal_segments,
    get_transaction_ids,
    get_committed_txns,
    get_aborted_txns,
    get_data_operations,
)
from state_builder import build_state
from snapshot_manager import SnapshotManager
from report_writer import (
    write_compacted_state,
    compute_compaction_fingerprint,
    write_compaction_report,
)


def main():
    """Run the WAL compaction pipeline."""
    wal_path = os.path.join(runtime_dir, "wal_segments.log")
    state_output = os.path.join(runtime_dir, "compacted_state.json")
    report_output = os.path.join(runtime_dir, "compaction_report.json")
    
    print("[compaction] Starting WAL compaction engine...")
    
    # Step 1: Parse WAL segments
    entries = parse_wal_segments(wal_path)
    print(f"[compaction] Parsed {len(entries)} WAL entries")
    
    # Step 2: Build state by replaying operations
    state_buffer = build_state(entries)
    
    # Step 3: Get visible state (filtered by visibility predicate)
    visible_state = state_buffer.get_visible_state()
    visible_metadata = state_buffer.get_visible_metadata()
    live_keys = state_buffer.get_live_keys()
    tombstoned_keys = state_buffer.get_tombstoned_keys()
    print(f"[compaction] Visible state has {len(visible_state)} keys, {len(live_keys)} live")
    
    # Step 4: Resolve conflicts via snapshot manager
    snapshot_mgr = SnapshotManager(entries)
    resolved_state = snapshot_mgr.resolve_conflicts(visible_state, visible_metadata, live_keys)
    
    # Step 5: Determine deleted keys for reporting
    deleted_keys = snapshot_mgr.get_deleted_keys(visible_metadata, tombstoned_keys, live_keys)
    
    # Step 6: Compute fingerprint
    fingerprint = compute_compaction_fingerprint(resolved_state)
    
    # Step 7: Gather statistics
    txn_ids = get_transaction_ids(entries)
    committed = get_committed_txns(entries)
    aborted = get_aborted_txns(entries)
    data_ops = get_data_operations(entries)
    
    # Step 8: Write outputs
    write_compacted_state(resolved_state, state_output)
    write_compaction_report(
        state=resolved_state,
        metadata=visible_metadata,
        live_keys=set(resolved_state.keys()),
        deleted_keys=deleted_keys,
        total_txns=len(txn_ids),
        committed_count=len(committed),
        aborted_count=len(aborted),
        total_operations=len(data_ops),
        fingerprint=fingerprint,
        output_path=report_output,
    )
    
    print(f"[compaction] Compaction complete:")
    print(f"  Transactions: {len(txn_ids)} total, {len(committed)} committed, {len(aborted)} aborted")
    print(f"  Live keys: {len(resolved_state)}")
    print(f"  Deleted keys: {len(deleted_keys)}")
    print(f"  Fingerprint: {fingerprint}")
    print(f"[compaction] Output written to {state_output} and {report_output}")


if __name__ == "__main__":
    main()
