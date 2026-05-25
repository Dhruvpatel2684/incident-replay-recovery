# Log Pipeline Reconciler — Crash Recovery Repair

## Scenario

You are investigating a **log event processing pipeline** that suffered a crash during execution. The pipeline code at `/app/runtime/` is **correct** — it processes events properly when given valid state. However, the crash left the state files **corrupted**, causing the pipeline to produce incorrect output when it resumes.

Your task is to write a **repair script** that analyzes the raw data and corrupted state, computes what the correct state should be, and restores the pipeline to a consistent state so it can produce correct output.

## System Architecture

The pipeline processes raw log events through these stages:

1. **Partition Reading**: Events are read from 3 partition files (`/app/runtime/partitions/partition_0.jsonl`, `partition_1.jsonl`, `partition_2.jsonl`) containing 75 total events.
2. **Deduplication**: A registry (`/app/runtime/state/dedup_registry.json`) tracks which event IDs have been processed to prevent duplicates.
3. **Shard Assignment**: Each event is assigned to one of 4 output shards using a deterministic hash: `hash(event_id) % 4` (polynomial rolling hash, base 31).
4. **Sequence Numbering**: A global counter (`/app/runtime/state/sequence_state.json`) assigns monotonically increasing sequence numbers.
5. **Checkpoint Tracking**: Per-partition offsets (`/app/runtime/state/checkpoints.json`) track how far each partition has been processed.
6. **Output Writing**: Events are written to shard files (`/app/runtime/shards/shard_0.jsonl` through `shard_3.jsonl`).
7. **Manifest Generation**: An integrity manifest (`/app/runtime/output/manifest.json`) records SHA-256 checksums per shard.

## What Went Wrong (5 Corruptions)

### 1. Checkpoints are AHEAD of reality
`checkpoints.json` claims all 3 partitions are fully processed (offsets 30, 25, 20). However, partition_2's events never made it to the shard files before the crash. The pipeline trusts these checkpoints and skips all partitions on restart.

### 2. Dedup registry has PHANTOM entries
`dedup_registry.json` contains 10 event IDs (`evt-phantom-001` through `evt-phantom-010`) that don't exist in any partition file. These could block future valid events with matching IDs.

### 3. Shard 3 is MISSING
`/app/runtime/shards/shard_3.jsonl` was lost during the crash. Events that hash to shard 3 are absent from the output.

### 4. Sequence counter JUMPED
`sequence_state.json` shows `next_sequence: 200`, but only ~55 events were actually sequenced (1-55). The counter was corrupted during the crash.

### 5. Manifest checksums are STALE
`manifest.json` contains SHA-256 checksums computed before the crash. They no longer match the actual shard file contents (especially since shard_3 is missing).

## Key Insight: Corruptions INTERACT

These aren't independent problems — fixing them requires understanding their dependencies:
- Fixing checkpoints reveals that partition_2 needs processing → adds events to shards
- Adding partition_2 events → changes shard contents → changes checksums
- Regenerating shard_3 requires knowing which events belong there → depends on correct dedup and checkpoints
- Sequence counter must be fixed AFTER all events are processed
- Checksums must be recomputed LAST after shards are finalized

## Your Task

Write a repair script at `/solution/repair_pipeline.py` that:

1. Analyzes raw partition files to determine valid event IDs
2. Fixes the corrupted state files
3. Ensures the pipeline can produce correct output for all 75 events

Your solution will be executed via `/solution/solve.sh`.

## Environment

- System-wide Python tooling and pytest are available
- Python standard library only (no external packages)
- Pipeline source code is at `/app/runtime/`
- All paths use absolute `/app/` prefix

## Expected Output Schema

After repair, the pipeline should produce:

**Shard files** (`/app/runtime/shards/shard_N.jsonl`):
```json
{"event_id": "evt-0001", "timestamp": "...", "source": "...", "level": "...", "payload": {...}, "shard_id": N, "sequence": M, "partition_source": "partition_X"}
```

**Manifest** (`/app/runtime/output/manifest.json`):
```json
{
  "num_shards": 4,
  "shards": {
    "shard_0.jsonl": {"checksum": "<sha256>", "event_count": N},
    ...
  },
  "total_events": 75
}
```

**State files** after repair:
- `checkpoints.json`: `{"partition_0": 30, "partition_1": 25, "partition_2": 20}`
- `dedup_registry.json`: `{"seen": [<only valid event IDs>]}`
- `sequence_state.json`: `{"next_sequence": 76}`
