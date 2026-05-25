#!/usr/bin/env python3
"""
Repair script for the log pipeline reconciler.

This script fixes corrupted state files by:
1. Scanning raw partition files to determine valid event IDs
2. Cleaning the dedup registry (removing phantom entries)
3. Scanning existing shard files to determine actual processing state
4. Recomputing checkpoints based on what's actually in the shards
5. Resetting the sequence counter appropriately
6. Re-running the pipeline to process missing events and regenerate output

The pipeline code itself is CORRECT — only the state files are corrupted
from a simulated crash recovery scenario.
"""

import json
import os
import sys
import hashlib


def assign_shard(event_id, num_shards):
    """Deterministic shard assignment (must match hasher.py)."""
    h = 0
    for c in event_id:
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    return h % num_shards


def get_valid_event_ids(base_path):
    """Read all raw partition files and collect valid event IDs."""
    partitions_dir = os.path.join(base_path, 'partitions')
    valid_ids = set()
    partition_events = {}  # partition_name -> [event_ids in order]

    for fname in sorted(os.listdir(partitions_dir)):
        if not fname.endswith('.jsonl'):
            continue
        partition_name = fname.replace('.jsonl', '')
        partition_events[partition_name] = []
        with open(os.path.join(partitions_dir, fname), 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    event = json.loads(line)
                    event_id = event['event_id']
                    valid_ids.add(event_id)
                    partition_events[partition_name].append(event_id)

    return valid_ids, partition_events


def get_events_in_shards(base_path):
    """Scan existing shard files to find which events are actually present."""
    shards_dir = os.path.join(base_path, 'shards')
    events_in_shards = set()
    max_sequence = 0

    if not os.path.exists(shards_dir):
        return events_in_shards, max_sequence

    for fname in os.listdir(shards_dir):
        if not fname.endswith('.jsonl'):
            continue
        with open(os.path.join(shards_dir, fname), 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    record = json.loads(line)
                    events_in_shards.add(record['event_id'])
                    seq = record.get('sequence', 0)
                    if seq > max_sequence:
                        max_sequence = seq

    return events_in_shards, max_sequence


def fix_dedup_registry(base_path, valid_ids):
    """Remove phantom entries from the dedup registry.

    Only keep event IDs that actually exist in the raw partition files.
    """
    registry_path = os.path.join(base_path, 'state', 'dedup_registry.json')

    if not os.path.exists(registry_path):
        # Create empty registry
        with open(registry_path, 'w') as f:
            json.dump({"seen": []}, f, indent=2)
        return 0

    with open(registry_path, 'r') as f:
        data = json.load(f)

    original_count = len(data.get("seen", []))
    cleaned = [eid for eid in data.get("seen", []) if eid in valid_ids]
    removed = original_count - len(cleaned)

    with open(registry_path, 'w') as f:
        json.dump({"seen": sorted(cleaned)}, f, indent=2)

    print(f"  Dedup registry: removed {removed} phantom entries "
          f"({original_count} -> {len(cleaned)})")
    return removed


def fix_checkpoints(base_path, partition_events, events_in_shards):
    """Recompute checkpoints based on what events are actually in shards.

    For each partition, find how many events (from the beginning) are
    actually present in the shard files. That's the true checkpoint.
    """
    checkpoints_path = os.path.join(base_path, 'state', 'checkpoints.json')
    new_checkpoints = {}

    for partition_name, event_ids in sorted(partition_events.items()):
        # Find the contiguous prefix of events that are in shards
        checkpoint = 0
        for eid in event_ids:
            if eid in events_in_shards:
                checkpoint += 1
            else:
                break
        new_checkpoints[partition_name] = checkpoint

    with open(checkpoints_path, 'w') as f:
        json.dump(new_checkpoints, f, indent=2)

    print(f"  Checkpoints recomputed: {new_checkpoints}")
    return new_checkpoints


def fix_sequence_counter(base_path, max_sequence):
    """Reset sequence counter to max_sequence + 1."""
    sequence_path = os.path.join(base_path, 'state', 'sequence_state.json')
    next_seq = max_sequence + 1

    with open(sequence_path, 'w') as f:
        json.dump({"next_sequence": next_seq}, f, indent=2)

    print(f"  Sequence counter reset: next_sequence = {next_seq}")
    return next_seq


def remove_corrupted_shards(base_path):
    """Remove shard files that are incomplete or corrupted.

    We need to remove shards and let the pipeline regenerate them
    because shard_3 is missing and existing shards may be incomplete.
    """
    shards_dir = os.path.join(base_path, 'shards')
    if os.path.exists(shards_dir):
        for fname in os.listdir(shards_dir):
            if fname.endswith('.jsonl'):
                os.remove(os.path.join(shards_dir, fname))
        print("  Removed existing shard files for clean regeneration")


def remove_stale_output(base_path):
    """Remove stale manifest and pipeline output."""
    manifest_path = os.path.join(base_path, 'output', 'manifest.json')
    pipeline_output = os.path.join(base_path, 'output', 'pipeline_output.jsonl')

    if os.path.exists(manifest_path):
        os.remove(manifest_path)
    if os.path.exists(pipeline_output):
        os.remove(pipeline_output)
    print("  Removed stale output files")


def repair(base_path):
    """Main repair logic."""
    print("=" * 60)
    print("LOG PIPELINE RECONCILER - STATE REPAIR")
    print("=" * 60)

    # Step 1: Gather valid event IDs from raw partitions
    print("\n[1/6] Scanning raw partition files...")
    valid_ids, partition_events = get_valid_event_ids(base_path)
    total_raw = sum(len(v) for v in partition_events.values())
    print(f"  Found {total_raw} valid events across "
          f"{len(partition_events)} partitions")

    # Step 2: Scan existing shards to understand actual state
    print("\n[2/6] Scanning existing shard files...")
    events_in_shards, max_sequence = get_events_in_shards(base_path)
    print(f"  Found {len(events_in_shards)} events in shards, "
          f"max sequence = {max_sequence}")

    # Step 3: Fix dedup registry (remove phantoms)
    print("\n[3/6] Fixing dedup registry...")
    fix_dedup_registry(base_path, valid_ids)

    # Step 4: Fix checkpoints based on actual shard contents
    print("\n[4/6] Fixing checkpoints...")
    fix_checkpoints(base_path, partition_events, events_in_shards)

    # Step 5: Reset sequence counter and clean shards for full reprocessing
    # Since shard_3 is missing, we need to rebuild all shards from scratch
    # to ensure consistency. Reset all state for clean reprocessing.
    print("\n[5/6] Resetting for clean reprocessing...")

    # Clear dedup registry (pipeline will rebuild it)
    registry_path = os.path.join(base_path, 'state', 'dedup_registry.json')
    with open(registry_path, 'w') as f:
        json.dump({"seen": []}, f, indent=2)
    print("  Cleared dedup registry for fresh processing")

    # Reset checkpoints to zero
    checkpoints_path = os.path.join(base_path, 'state', 'checkpoints.json')
    with open(checkpoints_path, 'w') as f:
        json.dump({}, f, indent=2)
    print("  Reset all checkpoints to zero")

    # Reset sequence counter
    sequence_path = os.path.join(base_path, 'state', 'sequence_state.json')
    with open(sequence_path, 'w') as f:
        json.dump({"next_sequence": 1}, f, indent=2)
    print("  Reset sequence counter to 1")

    # Remove corrupted shards
    remove_corrupted_shards(base_path)

    # Remove stale output
    remove_stale_output(base_path)

    # Step 6: Re-run the pipeline with clean state
    print("\n[6/6] Re-running pipeline with repaired state...")
    sys.path.insert(0, base_path)
    from pipeline import Pipeline
    pipeline = Pipeline(base_path)
    pipeline.run()

    print("\n" + "=" * 60)
    print("REPAIR COMPLETE")
    print("=" * 60)

    # Verify results
    manifest_path = os.path.join(base_path, 'output', 'manifest.json')
    if os.path.exists(manifest_path):
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        print(f"\nFinal state:")
        print(f"  Total events processed: {manifest['total_events']}")
        for shard_name, info in sorted(manifest['shards'].items()):
            print(f"  {shard_name}: {info['event_count']} events")


if __name__ == '__main__':
    base_path = '/app/runtime'
    repair(base_path)
