# Packet Reassembly Repair — Debugging Task

## Overview

An IP packet fragment reassembly system processes captured network traffic containing fragmented datagrams. It reassembles complete packets from their fragments, detects overlapping fragment attacks (IDS evasion), applies configurable overlap resolution policies, and verifies datagram integrity through checksum computation.

## System Environment

- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source, config, data, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **Entry point**: `python3 -m runtime.run_reassembly`

## System Architecture

- `/app/runtime/engine/` — Fragment buffer management, reassembly logic
- `/app/runtime/policy/` — Overlap resolution policies
- `/app/runtime/metrics/` — Integrity checksums, statistics tracking

## Observed Symptoms

- One stream fails reassembly with gaps even though all byte positions are covered by fragments
- Integrity checksums do not match expected values for any stream
- The overlap resolution does not match the expected "first-wins" behavior used by standard TCP/IP stacks
- Fragment ordering appears non-deterministic when multiple fragments share an offset

## Expected Behavior

- All 3 streams reassemble successfully (100% success rate)
- Total reassembled bytes: 96 (alpha=32, beta=28, gamma=36)
- All checksums verify against expected values in the stream specifications
- Beta stream (with overlaps) produces correct data using first-arriving fragment priority

## Output Schema

### `/app/runtime/output/reassembly_summary.json`

| Field | Type | Description |
|-------|------|-------------|
| `streams_processed` | integer | Number of fragment streams processed |
| `total_fragments` | integer | Total fragments received |
| `total_overlaps` | integer | Overlapping fragments detected |
| `successful_reassemblies` | integer | Streams reassembled without gaps |
| `failed_reassemblies` | integer | Streams with incomplete reassembly |
| `total_bytes_reassembled` | integer | Total bytes across successful datagrams |
| `success_rate` | float | Ratio of successful reassemblies |

### `/app/runtime/output/reassembly_results.json`

Array of per-stream results with fragment counts, overlap detection, reassembly metrics, and checksum verification.

## Key Files

| File | Purpose |
|------|---------|
| `/app/runtime/run_reassembly.py` | Entry point, orchestrates processing |
| `/app/runtime/engine/fragment_buffer.py` | Fragment storage and overlap detection |
| `/app/runtime/engine/reassembler.py` | Datagram reconstruction from fragments |
| `/app/runtime/policy/overlap_policy.py` | Overlap resolution (first/last wins) |
| `/app/runtime/metrics/integrity.py` | 16-bit Internet checksum computation |
| `/app/runtime/metrics/stats.py` | Aggregate statistics collection |
| `/app/runtime/data/stream_alpha.json` | Non-overlapping fragment stream |
| `/app/runtime/data/stream_beta.json` | Overlapping fragments (evasion attempt) |
| `/app/runtime/data/stream_gamma.json` | Out-of-order adjacent fragments |

## Your Task

Identify and fix the defects causing reassembly failures, incorrect checksums, and wrong overlap behavior. The bugs are spread across multiple modules and interact through the reassembly data flow.
