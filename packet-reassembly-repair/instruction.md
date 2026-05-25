# Packet Reassembly — Broken After Refactor

## What happened

We have a packet fragment reassembler that reads captured network fragments (like a simplified TCP stream), reconstructs full messages from out-of-order pieces using sequence numbers, detects duplicate retransmissions, and produces a session reconstruction summary. It was passing all checks three weeks ago.

Then someone refactored the reassembly buffer logic "for performance" and now the output is garbage. Multiple fields are wrong and the bugs seem to interact with each other.

## How it works

Four Python files in `/app/runtime/`:

- `reassembler.py` — entry point, just wires stuff together (this file is fine)
- `fragment_parser.py` — reads `capture.fragments`, turns lines into fragment dicts
- `reassembly_engine.py` — takes fragments and reconstructs sessions (groups by session_id, orders by offset, detects retransmissions, merges payloads)
- `session_writer.py` — takes reconstructed sessions, writes `sessions.jsonl` and `reassembly_stats.json`

The input capture (`capture.fragments`) has fragments from 8 sessions, some arriving out of order, some retransmitted. The capture file itself is correct — don't modify it.

## What's broken (symptoms we're seeing)

Honestly there are multiple things wrong and they seem related:

- **Session payload lengths are wrong** — reassembled messages have incorrect byte counts. The payload length calculation for some fragment types seems off, like it's using the header length instead of the data length.

- **Retransmission count is wrong** — we know there are exactly 5 duplicate fragments in the capture, but the detector is reporting a different number. Looks like it's keeping the wrong copy when a retransmission arrives (keeping the later one instead of the original).

- **Gap detection is broken** — sessions that should be fully contiguous (no missing bytes) are showing gaps. Something about how fragment offsets are parsed for certain packet types introduces an off-by-one.

- **Checksum is non-deterministic** — the integrity checksum gives different results between runs. The fragment ordering within a session isn't stable before hashing.

- **Session boundaries bleed** — fragments from one session are appearing in another. The reassembly buffer state carries over between sessions instead of being reset.

- **RTT estimate is wrong** — the round-trip time calculation between original and retransmission uses the wrong timestamp field, producing an inflated value.

- **total_bytes_reassembled is inflated** — it includes retransmitted bytes that should have been deduplicated out. Deduplication seems to happen after byte counting instead of before.

## Output file format

The reassembler produces two files in `/app/runtime/`:

**`sessions.jsonl`** — one JSON record per reassembled session (sorted by session_id), each with:
- `session_id` (string): the session identifier
- `total_fragments` (int): unique (non-retransmitted) fragments in this session
- `payload_bytes` (int): total reassembled payload size in bytes
- `is_complete` (bool): true if no gaps exist in the byte range
- `fragment_offsets` (list of int): sorted list of unique byte offsets

**`reassembly_stats.json`** — summary with:
- `total_sessions` (int): number of distinct sessions
- `total_bytes_reassembled` (int): sum of payload_bytes across all sessions
- `retransmissions_detected` (int): number of duplicate fragments found
- `complete_sessions` (int): sessions with is_complete=true
- `reassembly_checksum` (string): 16-char hex SHA-256 prefix over sorted output
- `avg_fragments_per_session` (float): mean fragment count per session
- `estimated_avg_rtt_ms` (float): average RTT in milliseconds from retransmission pairs
- `max_fragment_offset` (int): highest byte offset seen across all sessions

## How to run

```bash
python3 /app/runtime/reassembler.py
```

This regenerates `sessions.jsonl` and `reassembly_stats.json` in `/app/runtime/`.

## What we need

Fix the bugs in the processing modules so the output is correct. The entry point (`reassembler.py`) is fine — the problems are in how fragments get parsed, how reassembly and deduplication work, and how the session output gets generated.

Fair warning: these bugs interact with each other. Fixing one thing might not show improvement until you also fix the related issue in another file. The checksum in particular depends on multiple fields being correct simultaneously.

Python 3 standard library is available system-wide. No external packages needed.
