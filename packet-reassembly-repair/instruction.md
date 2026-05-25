# Packet Reassembly Engine -- Broken After "Protocol Compliance Refactor"

## What happened

We have a network packet reassembly engine that reconstructs byte streams from fragmented segments captured off the wire. Three flows, various segment sizes, some retransmissions. Last Thursday someone did a "protocol compliance refactor" claiming the sequence number handling needed to match some RFC more closely. Now the whole pipeline produces garbage.

The engine runs without crashing but the output is wrong in several ways. I need to get this back to producing correct reassembled streams before the next capture analysis window.

## Architecture

Six Python modules in `/app/runtime/`:

- `reassembly_engine.py` -- main orchestrator, wires everything together (this one is fine)
- `segment_parser.py` -- parses the capture log file into segment objects (this one is fine)
- `stream_buffer.py` -- manages byte stream buffers, places segments at offsets
- `overlap_handler.py` -- detects overlapping/retransmitted segments
- `checksum_validator.py` -- computes and validates stream CRC32 checksums
- `output_writer.py` -- writes result files (this one is fine)

Input data is in `capture.log`. Don't modify it.

## Symptoms

1. **Streams are garbled** -- byte positions are wrong. Characters that should be at offset N end up at offset N-1. The first byte of each stream looks correct but everything after that is shifted. Something is wrong with how sequence numbers map to buffer offsets.

2. **Retransmissions not detected** -- the overlap count is always 0 even though there are clearly retransmitted segments in the capture (marked with RETRANSMIT flag). The overlap handler should detect when a new segment's byte range intersects with an already-placed segment and drop it. Instead it places everything, causing later retransmits with slightly different content to corrupt the stream.

3. **Checksums don't match** -- even after fixing the stream content, the CRC32 checksums reported in the output don't match what I compute manually. Something is off in the checksum computation.

4. **Gap detection reports wrong ranges** -- flow_C has a deliberate gap (segments jump from byte 10 to byte 16) but the reported gap positions are wrong because the buffer offsets are messed up from issue #1.

## Capture format

Plain text, one segment per line. Lines starting with `#` are comments.

```
SEQ_NUM|FLOW_ID|PAYLOAD_HEX|FLAGS|TIMESTAMP
```

- `SEQ_NUM`: 0-based byte offset where this segment's payload starts in the stream
- `FLOW_ID`: identifies which stream this segment belongs to
- `PAYLOAD_HEX`: hex-encoded payload bytes (may be empty for FIN segments)
- `FLAGS`: SYN, ACK, RETRANSMIT, or FIN
- `TIMESTAMP`: monotonic capture timestamp

## Output schema

### streams.json

```json
{
  "flow_A": {
    "stream_hex": "48656c6c6f...",
    "stream_text": "Hello...",
    "total_bytes": 27,
    "has_gaps": false,
    "gaps": []
  },
  ...
}
```

- `stream_hex`: hex encoding of reassembled byte stream
- `stream_text`: UTF-8 decode of stream (replacement chars for gap bytes)
- `total_bytes`: total length of reassembled buffer
- `has_gaps`: whether any byte offsets are missing data
- `gaps`: list of `[start, end]` inclusive ranges with no data

### reassembly_report.json

```json
{
  "total_flows": 3,
  "total_segments": 17,
  "total_retransmits": 4,
  "total_overlaps": 3,
  "per_flow": {
    "flow_A": {
      "segments_received": 8,
      "stream_length": 27,
      "overlaps_detected": 2,
      "gaps": [],
      "checksum": "..."
    },
    ...
  }
}
```

- `total_flows`: number of distinct flow IDs
- `total_segments`: total segments parsed from capture log
- `total_retransmits`: count of segments with RETRANSMIT flag
- `total_overlaps`: total overlapping segments detected and dropped
- `per_flow`: per-flow stats with segment count, stream length, overlaps, gaps, and CRC32 checksum

## How to run

```bash
python3 /app/runtime/reassembly_engine.py
```

Produces `streams.json` and `reassembly_report.json` in `/app/runtime/`.

## What to fix

The bugs are in `stream_buffer.py`, `overlap_handler.py`, and `checksum_validator.py`. The reassembly engine, segment parser, and output writer are all correct.

I count about 4 distinct bugs across those three files. They interact with each other -- fixing the buffer offsets alone won't give you correct flow_B content because the overlap handler also needs to work to prevent the corrupting retransmit from being placed.

Standard library only. `zlib` is part of the standard library and is used for CRC32.
