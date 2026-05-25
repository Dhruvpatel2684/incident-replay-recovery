# Packet Reassembly Pipeline — Broken After Network Stack Refactor

## Incident Summary

Our packet fragment reassembly pipeline processes edge-ingress captures from production network appliances. It takes raw fragment captures (from a simplified TCP-like protocol), reconstructs complete sessions from out-of-order fragments, detects retransmissions, and produces session reconstruction statistics for network observability.

The pipeline was passing all checks until last week when we refactored the flow tracking and reassembly layers to support higher throughput. Since the refactor, several output metrics are wrong. The bugs seem to interact — fixing one metric sometimes reveals that another was being masked.

## Architecture

Five Python modules in `/app/runtime/`:

- `reassembler.py` — pipeline entry point, orchestrates stages (this file is correct)
- `fragment_parser.py` — reads `capture.fragments`, produces structured fragment records (this module is correct)
- `flow_tracker.py` — per-flow state machine, deduplication, retransmit detection
- `reassembly_engine.py` — byte-range reconstruction, gap detection, completeness verdict
- `integrity_checker.py` — cross-flow validation, aggregate stats, integrity checksum
- `session_writer.py` — final serialization and enrichment (correct, just passes data through)

The input capture (`capture.fragments`) contains 85 fragment records from 12 flows. The capture is correct — don't modify it.

## What's broken

Multiple metrics are wrong and the issues seem interdependent:

1. **Retransmission count is inflated** — we're seeing 12 retransmissions but the capture only has 7 R-flagged packets. It looks like late out-of-order duplicate arrivals are being conflated with actual retransmissions.

2. **Payload byte counts are slightly off** — several flows are reporting 1 byte less than expected. The total across all flows is 15282 but should be 15288. Only some flows are affected.

3. **Packet loss estimate is way too high** — reporting ~0.245 when it should be ~0.125. This might be related to the inflated retransmit count, or there could be a formula error.

4. **Integrity checksum doesn't match** — the checksum is supposed to be deterministic but we're getting `297fb04947ae2d83` instead of the expected `6e66d7e4ef19a678`. This could be caused by any upstream data corruption OR by a non-deterministic iteration order.

5. **Curiously, all completeness checks pass** — despite the byte count errors, all 12 flows show as "complete". We suspect there might be a compensating error somewhere that masks the byte count issue.

## Expected correct output

The pipeline should produce:
- 12 flows, all complete (no gaps)
- Total payload: 15288 bytes
- 7 retransmissions (R-flagged only)
- Packet loss ≈ 0.125
- Checksum: `6e66d7e4ef19a678`

## How to run

```bash
python3 /app/runtime/reassembler.py
```

Produces `sessions.jsonl` and `reassembly_stats.json` in `/app/runtime/`.

## What we need

Fix the bugs in the pipeline modules. The entry point (`reassembler.py`), the fragment parser (`fragment_parser.py`), and the session writer (`session_writer.py`) are working correctly — the issues are in the flow tracking, reassembly engine, and integrity checker.

Warning: the bugs interact. One bug in the reassembly engine is currently MASKED by another bug in the same module — fixing one without the other will cause completeness checks to start failing where they currently pass. Similarly, the retransmit counting issue cascades downstream into RTT estimation and per-flow annotations.

Python 3 standard library only. No external packages needed.
