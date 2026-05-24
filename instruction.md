# Incident Replay Recovery — Operational Context

## Situation

A replay recovery runtime processes fragmented incident event feeds into a deterministic reconstructed timeline. The system ingests JSONL event fragments from multiple sources, normalizes timestamps to UTC, constructs time-bounded replay windows, manages replay cursor state, applies retention cleanup, and exports the finalized timeline with integrity verification.

After a partial recovery scenario, the exported timeline exhibits several anomalies:

- Duplicate events appearing in the reconstructed output
- Timestamp ordering inconsistencies for events originating from non-UTC sources
- Replay cursors referencing windows that no longer exist after retention cleanup
- Checkpoint state reflecting stale positions from a concurrent replay session
- Non-deterministic ordering of same-timestamp events across reruns

## Observed Symptoms

Running `python3 /app/runtime/run_replay.py` produces an export that:

1. Contains more event references than the number of unique ingested events
2. Shows events from `+05:30` timezone sources placed incorrectly in the timeline
3. Leaves cursor state pointing to purged replay windows
4. Overwrites cursor progress with older checkpoint timestamps
5. Produces output where same-timestamp event ordering depends on ingestion sequence

## Expected Behavior

After repair, the runtime must produce:

- Exactly one reference per event across all replay windows
- Correct UTC normalization accounting for full timezone offset (hours and minutes)
- No active cursors referencing deleted or purged windows
- Monotonically non-decreasing checkpoint timestamps for all active cursors
- Deterministic ordering of same-timestamp events (lexicographic by event_id)
- Byte-identical export output across consecutive runs

## Scope

The repair should reconcile replay state without rewriting the runtime modules. Inspect the SQLite replay state (`/app/runtime/replay_state.db`), identify metadata corruption, and apply targeted corrections that restore deterministic replay behavior.

## Key Files

- `/app/runtime/run_replay.py` — orchestration entrypoint
- `/app/runtime/ingest.py` — JSONL feed ingestion and timestamp normalization
- `/app/runtime/reconstruct.py` — replay window construction
- `/app/runtime/cursor.py` — cursor lifecycle and checkpoint management
- `/app/runtime/retention.py` — window expiration and cleanup
- `/app/runtime/export.py` — timeline export with integrity checksum
- `/app/runtime/replay_state.db` — SQLite replay state (created during execution)
- `/app/runtime/exports/` — output artifacts
