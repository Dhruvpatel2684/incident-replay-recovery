"""
Oracle solution for packet reassembly repair.

Re-processes capture.log from scratch with correct logic:
- 0-based sequence offsets (no off-by-one)
- Exclusive-end next expected sequence
- Standard overlap intersection check (first-writer-wins)
- Direct CRC32 without byte reversal
"""

import json
import os
import zlib
from collections import namedtuple

Segment = namedtuple("Segment", ["seq_num", "flow_id", "payload", "flags", "timestamp"])

CAPTURE_LOG_PATH = "/app/runtime/capture.log"
RUNTIME_DIR = "/app/runtime"


def parse_capture_log():
    """Parse the capture log file."""
    segments = []
    with open(CAPTURE_LOG_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            if len(parts) != 5:
                continue
            seq_num = int(parts[0])
            flow_id = parts[1]
            payload_hex = parts[2]
            payload = bytes.fromhex(payload_hex) if payload_hex else b""
            flags = parts[3]
            timestamp = int(parts[4])
            segments.append(Segment(
                seq_num=seq_num,
                flow_id=flow_id,
                payload=payload,
                flags=flags,
                timestamp=timestamp
            ))
    return segments


def is_overlapping(new_seg, placed_segments):
    """Check if new segment overlaps with any already-placed segment.
    Correct overlap check: new_start < exist_end and exist_start < new_end."""
    if not new_seg.payload:
        return False
    new_start = new_seg.seq_num
    new_end = new_seg.seq_num + len(new_seg.payload)
    for existing in placed_segments:
        if not existing.payload:
            continue
        exist_start = existing.seq_num
        exist_end = existing.seq_num + len(existing.payload)
        # Standard interval overlap: ranges intersect if neither is fully before the other
        if new_start < exist_end and exist_start < new_end:
            return True
    return False


def compute_checksum(stream_bytes):
    """Compute CRC32 checksum directly (no byte reversal)."""
    if not stream_bytes:
        return "00000000"
    return format(zlib.crc32(stream_bytes) & 0xFFFFFFFF, '08x')


def run_repair():
    """Run the correct reassembly pipeline."""
    segments = parse_capture_log()

    # Group by flow_id preserving order
    flows = {}
    for seg in segments:
        if seg.flow_id not in flows:
            flows[seg.flow_id] = []
        flows[seg.flow_id].append(seg)

    # Count retransmits
    total_retransmits = sum(1 for seg in segments if seg.flags == "RETRANSMIT")

    streams_data = {}
    per_flow_stats = {}
    total_overlaps = 0

    for flow_id, flow_segments in flows.items():
        buffer = {}  # offset -> byte value
        placed_segments = []
        overlap_count = 0

        for seg in flow_segments:
            if is_overlapping(seg, placed_segments):
                overlap_count += 1
            else:
                # Place at correct 0-based offset
                offset = seg.seq_num
                for i, byte_val in enumerate(seg.payload):
                    buffer[offset + i] = byte_val
                placed_segments.append(seg)

        # Reassemble stream bytes
        if buffer:
            max_offset = max(buffer.keys())
            stream_bytes = bytearray(max_offset + 1)
            for offset, byte_val in buffer.items():
                stream_bytes[offset] = byte_val
            stream_bytes = bytes(stream_bytes)
        else:
            stream_bytes = b""

        # Detect gaps
        gaps = []
        if buffer:
            max_offset = max(buffer.keys())
            gap_start = None
            for i in range(max_offset + 1):
                if i not in buffer:
                    if gap_start is None:
                        gap_start = i
                else:
                    if gap_start is not None:
                        gaps.append([gap_start, i - 1])
                        gap_start = None
            if gap_start is not None:
                gaps.append([gap_start, max_offset])

        has_gaps = len(gaps) > 0
        stream_length = len(stream_bytes)
        checksum = compute_checksum(stream_bytes)

        streams_data[flow_id] = {
            "stream_bytes": stream_bytes,
            "has_gaps": has_gaps,
            "gaps": gaps
        }

        per_flow_stats[flow_id] = {
            "segments_received": len(flow_segments),
            "stream_length": stream_length,
            "overlaps_detected": overlap_count,
            "gaps": gaps,
            "checksum": checksum
        }

        total_overlaps += overlap_count

    # Write streams.json
    streams_output = {}
    for flow_id, data in streams_data.items():
        stream_bytes = data["stream_bytes"]
        streams_output[flow_id] = {
            "stream_hex": stream_bytes.hex(),
            "stream_text": stream_bytes.decode("utf-8", errors="replace"),
            "total_bytes": len(stream_bytes),
            "has_gaps": data["has_gaps"],
            "gaps": data["gaps"]
        }

    streams_path = os.path.join(RUNTIME_DIR, "streams.json")
    with open(streams_path, "w") as f:
        json.dump(streams_output, f, indent=2)

    # Write reassembly_report.json
    report_data = {
        "total_flows": len(flows),
        "total_segments": len(segments),
        "total_retransmits": total_retransmits,
        "total_overlaps": total_overlaps,
        "per_flow": per_flow_stats
    }

    report_path = os.path.join(RUNTIME_DIR, "reassembly_report.json")
    with open(report_path, "w") as f:
        json.dump(report_data, f, indent=2)


if __name__ == "__main__":
    run_repair()
