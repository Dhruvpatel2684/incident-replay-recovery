# WAL Compaction Repair — Debugging Task

## Overview

A Write-Ahead Log (WAL) compaction system processes transaction log segments, performs garbage collection on superseded entries and expired tombstones, builds point-in-time database snapshots, and computes integrity checksums for each segment. The system uses LSN (Log Sequence Number) encoding with bitwise segment extraction and XOR-fold checksumming.

## System Environment

- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source, config, data, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **Entry point**: `python3 -m runtime.run_compaction`

## Processing Stages

1. **Segment Loading** — Loads WAL segment files from `/app/runtime/data/`. Each segment file contains entries with monotonically increasing LSNs within that segment.

2. **LSN Segment Mapping** — Maps each entry's LSN to its segment number using bit-shift extraction. With segment_size=256 (2^8), the segment number is obtained by right-shifting the LSN by 8 bits: `segment_number = lsn >> 8`. This means LSNs 0-255 map to segment 0, 256-511 to segment 1, 512-767 to segment 2.

3. **Compaction** — Identifies live entries by retaining only the latest (highest LSN) entry for each key. Tombstone entries (deletes) are garbage collected when their LSN is strictly less than the GC watermark (`max_lsn - gc_watermark_offset`). Tombstones AT the watermark are retained (the condition is strict less-than).

4. **Snapshot Building** — Builds a point-in-time snapshot by replaying compacted entries up to the checkpoint boundary. The boundary is computed by rounding UP to the next checkpoint interval: `boundary = ((max_lsn // interval) + 1) * interval`. This ensures entries in the current epoch are included.

5. **Checksum Computation** — Computes per-segment and output integrity checksums using XOR-fold algorithm. The 64-bit accumulator is folded to 32 bits: `result = (accumulator >> 32) ^ (accumulator & 0xFFFFFFFF)`.

## Problem

The system runs without errors but produces incorrect results:

- Only 2 of 3 WAL segments are detected during scanning
- Integrity checksums do not match independently computed reference values
- The snapshot is missing entries that should be included in the current epoch
- One tombstone is incorrectly garbage collected

## Expected Correct Output

When operating correctly:

- All 3 segments are scanned (segment numbers 0, 1, 2)
- 33 live entries survive compaction (including 5 retained tombstones)
- Snapshot contains 28 live keys spanning all namespaces
- Per-segment checksums match reference XOR-fold with full 32-bit lower mask
- GC watermark is 513, and the tombstone at LSN 513 is retained

## Output Schema

### `/app/runtime/output/compacted_log.json`

A JSON array of surviving entries after compaction:

| Field | Type | Description |
|-------|------|-------------|
| `lsn` | integer | Log Sequence Number |
| `op` | string | Operation type: "put" or "del" |
| `key` | string | Database key (namespace:id format) |
| `value` | string or null | Value (null for deletes) |
| `ts` | integer | Timestamp |

### `/app/runtime/output/snapshot_state.json`

A JSON object mapping live keys to their current values.

### `/app/runtime/output/compaction_summary.json`

| Field | Type | Description |
|-------|------|-------------|
| `compaction_stats` | object | Statistics from compaction |
| `snapshot_size` | integer | Number of live keys in snapshot |
| `namespace_stats` | object | Per-namespace put/del/live counts |
| `segment_checksums` | object | Per-segment integrity checksums |
| `output_checksum` | integer | Checksum over compacted output |
| `compacted_entry_count` | integer | Number of entries in compacted log |

Fields within `compaction_stats`:

| Field | Type | Description |
|-------|------|-------------|
| `total_entries` | integer | Total entries across all segments |
| `unique_keys` | integer | Number of distinct keys seen |
| `live_entries` | integer | Entries surviving compaction |
| `dead_entries` | integer | Entries removed by compaction |
| `live_keys` | integer | Keys with at least one live entry |
| `tombstones_retained` | integer | Delete entries kept (above GC watermark) |
| `gc_watermark` | integer | LSN threshold for tombstone collection |
| `segments_scanned` | integer | Number of distinct segments found |

## Key Files

| File | Purpose |
|------|---------|
| `/app/runtime/run_compaction.py` | Main entry point orchestrating compaction |
| `/app/runtime/compactor.py` | WAL compaction engine with GC logic |
| `/app/runtime/lsn.py` | LSN encoding utilities (segment extraction) |
| `/app/runtime/snapshot.py` | Point-in-time snapshot builder |
| `/app/runtime/checksum.py` | XOR-fold checksum computation |
| `/app/runtime/config.ini` | Configuration for WAL, compaction, checksum |
| `/app/runtime/data/wal_segment_0.json` | WAL segment 0 (26 entries, LSNs 0-25) |
| `/app/runtime/data/wal_segment_1.json` | WAL segment 1 (25 entries, LSNs 256-280) |
| `/app/runtime/data/wal_segment_2.json` | WAL segment 2 (16 entries, LSNs 512-527) |
| `/app/runtime/output/compacted_log.json` | Compacted WAL output |
| `/app/runtime/output/snapshot_state.json` | Database snapshot |
| `/app/runtime/output/compaction_summary.json` | Compaction statistics |

## Your Task

Identify and fix defects in the runtime source files so that the system produces correct compaction results, valid checksums, and complete snapshots. The defects are in the algorithmic implementations involving bitwise operations, boundary arithmetic, and comparison semantics.
