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

## Environment

The runtime environment already contains the required system-wide Python tooling and pytest installation.

## Key Files

- `/app/runtime/run_replay.py` — orchestration entrypoint
- `/app/runtime/ingest.py` — JSONL feed ingestion and timestamp normalization
- `/app/runtime/reconstruct.py` — replay window construction
- `/app/runtime/cursor.py` — cursor lifecycle and checkpoint management
- `/app/runtime/retention.py` — window expiration and cleanup
- `/app/runtime/export.py` — timeline export with integrity checksum
- `/app/runtime/replay_state.db` — SQLite replay state (created during execution)
- `/app/runtime/exports/` — output artifacts
- `/app/solution/reconcile_runtime.py` — replay state reconciliation repair script

## JSONL Replay Feed Schema

Each fragment file contains one JSON object per line representing an incident event:

- `event_id` (string) — unique event identifier across all fragments
- `timestamp` (string) — ISO-8601 timestamp with timezone offset (e.g. `2024-01-15T10:05:00+05:30`)
- `data` (object) — event payload containing `service`, `level`, `message`, and context-specific fields

Fragments arrive from multiple geographic sources with varying timezone offsets. The runtime normalizes all timestamps to UTC and reconstructs them into deterministic, time-bounded replay windows.

## SQLite Replay State Schema

The runtime persists replay state in `/app/runtime/replay_state.db` across four tables:

**raw_events** — Staging table for ingested events. Stores both the original `timestamp_raw` (as received from the fragment source) and the UTC-normalized `timestamp_norm`. Each event is deduplicated by `event_id` at ingestion time.

**replay_windows** — Time-bounded windows constructed on a fixed grid. Each window holds a JSON array of `event_ids` representing events assigned to that interval. Window status transitions from `active` to expired upon retention cleanup. Correct boundary semantics require exclusive upper bounds to prevent cross-window duplication.

**replay_cursor** — Tracks replay session progress per window. Each cursor binds a `session_id` to a `window_id` with a `position` offset and `checkpoint_ts`. Cursor state should transition to `stale` when its referenced window is purged. Checkpoint timestamps must never regress for a given session/window pair.

**retention_meta** — Records window expiration decisions. Stores the `window_id`, retention cutoff, and purge timestamp. Windows beyond the configured retention horizon are removed, and this table preserves the audit trail.

## Replay Export Schema

The exported timeline at `/app/runtime/exports/reconstructed_timeline.jsonl` contains one JSON object per line:

- `event_id` (string) — the original event identifier
- `timestamp` (string) — UTC-normalized ISO-8601 timestamp (`+00:00` suffix)
- `payload` (object) — the original event data

Events are emitted in strict chronological order by `timestamp`. Events sharing an identical timestamp are ordered lexicographically by `event_id` to ensure deterministic output. Each event appears exactly once across all replay windows — no duplicates in the export.

## Integrity Metadata Schema

The file `/app/runtime/exports/replay_integrity.json` contains:

- `sha256` (string) — SHA-256 digest computed over the concatenated JSONL output lines
- `event_count` (integer) — total number of events in the exported timeline
- `window_count` (integer) — number of active replay windows contributing to the export
- `exported_at` (string) — UTC timestamp of when the export was produced

The checksum must remain stable across consecutive runs given identical input feeds and correct replay state.
