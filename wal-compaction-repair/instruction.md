# WAL Compaction Tool — Incident Report

## Context

We have a WAL (Write-Ahead Log) compaction tool that processes raw WAL segments from our analytics database and produces a compacted key-value state. Think PostgreSQL's WAL replay but simplified — it reads INSERT/UPDATE/DELETE operations, tracks transaction boundaries, and outputs the final materialized state after compaction.

This has been running fine for months. After a recent refactor to "improve modularity" (splitting the monolithic compactor into state_builder, snapshot_manager, and report_writer), the compacted output stopped matching our reference snapshots.

## Symptoms

We validated against a known-good pg_dump of the same data window:

1. **Phantom keys from non-committed transactions** — The compacted state includes keys that were only ever written by transactions that did NOT commit. For example, `cache:7002` and `session:3003` appear in the output despite coming from aborted transactions. It's like the visibility filtering is letting through changes that shouldn't be visible.

2. **Wrong winner on multi-writer conflicts** — When multiple committed transactions write the same key, the wrong value wins. Specifically `user:1001` ends up with `role=admin` (the initial value from the earliest transaction) instead of `role=owner` (from the latest). Similarly `config:1001` shows the old feature flags instead of the updated ones.

3. **Committed keys getting incorrectly removed** — `session:3001` was inserted by a committed transaction (txn_002) but doesn't appear in the output. We traced this to an aborted transaction (txn_003) that tried to DELETE it — even though that DELETE was aborted, the key is still being removed from the final state.

4. **Compaction fingerprint doesn't match reference** — The SHA-256 fingerprint we use for CI regression detection is completely wrong. Even if we manually fix individual values, the hash doesn't match.

## System Architecture

The pipeline is:

```
wal_segments.log → wal_parser.py → state_builder.py → snapshot_manager.py → report_writer.py
                                                                                  ↓
                                                      compacted_state.json + compaction_report.json
```

- `compaction_engine.py` — Orchestrator. Reads WAL, runs the pipeline, writes output. This file is fine.
- `wal_parser.py` — Parses the pipe-delimited WAL format. This file is fine.
- `state_builder.py` — Replays WAL operations to build key-value state. Uses an eager-apply / deferred-visibility architecture where all operations are applied immediately and visibility is determined at read time by a predicate. Also handles tombstone tracking for DELETE operations.
- `snapshot_manager.py` — Resolves multi-writer conflicts using last-writer-wins (LWW) semantics to determine the final value for each key.
- `report_writer.py` — Writes the JSON state file and compaction report with fingerprint.

## Input Format

The WAL segment log (`wal_segments.log`) uses pipe-delimited fields:

```
LSN|TXN_ID|OPERATION|KEY|VALUE|TIMESTAMP
```

- LSN: Log Sequence Number (monotonically increasing, authoritative ordering)
- TXN_ID: Transaction identifier (e.g., txn_001)
- OPERATION: BEGIN, INSERT, UPDATE, DELETE, COMMIT, ABORT, CHECKPOINT
- KEY: affected key (e.g., "user:1001", "order:5023")
- VALUE: JSON value (empty for DELETE/BEGIN/COMMIT/ABORT)
- TIMESTAMP: wall-clock time (may have clock skew between transactions)

## Output Schema

### compacted_state.json

A JSON object mapping keys to their final values:
```json
{
  "user:1001": {"name": "alice", "role": "...", ...},
  "order:5003": {"user": "alice", "amount": 500, "status": "confirmed"},
  ...
}
```

### compaction_report.json

```json
{
  "compaction_summary": {
    "total_transactions": 10,
    "committed_transactions": 8,
    "aborted_transactions": 2,
    "total_data_operations": 32
  },
  "state_summary": {
    "live_key_count": <int>,
    "deleted_key_count": <int>,
    "keys": [<sorted list of live key names>]
  },
  "compaction_fingerprint": "<16-char hex string>"
}
```

## Environment

- Python 3.11 available system-wide
- No external dependencies needed (stdlib only)
- Output files go in `/app/runtime/`
- Run with: `python3 /app/runtime/compaction_engine.py`

## What We Need

Find and fix the bugs causing the symptoms above. The WAL data and parser are correct — the issues are in how visibility is determined, how conflicts are resolved, how tombstones are tracked, and how the report is generated.

Don't add dependencies. Don't change the input format or output schema. Just make the compaction correct.
