"""
Packet reassembly engine -- main orchestrator.

Reads a packet capture log, groups segments by flow, reassembles byte streams,
detects overlaps, computes checksums, and writes output files.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from segment_parser import parse_capture_log
from stream_buffer import StreamBuffer
from overlap_handler import OverlapHandler
from checksum_validator import ChecksumValidator
from output_writer import write_outputs


def run_reassembly():
    """Run the full reassembly pipeline."""
    # Parse capture log
    segments = parse_capture_log()

    # Group segments by flow_id, preserving file order
    flows = {}
    for seg in segments:
        if seg.flow_id not in flows:
            flows[seg.flow_id] = []
        flows[seg.flow_id].append(seg)

    # Count retransmits
    total_retransmits = sum(1 for seg in segments if seg.flags == "RETRANSMIT")

    # Process each flow
    checksum_validator = ChecksumValidator()
    streams_data = {}
    per_flow_stats = {}
    total_overlaps = 0

    for flow_id, flow_segments in flows.items():
        buffer = StreamBuffer()
        overlap_handler = OverlapHandler()
        placed_segments = []

        for seg in flow_segments:
            # Check for overlap with already-placed segments
            if overlap_handler.is_overlapping(seg, placed_segments):
                overlap_handler.record_overlap()
            else:
                buffer.place_segment(seg)
                placed_segments.append(seg)

        # Get reassembled stream
        stream_bytes = buffer.get_stream_bytes()
        stream_length = buffer.get_next_expected_seq()
        gaps = buffer.get_gaps()
        has_gaps = len(gaps) > 0
        checksum = checksum_validator.compute_stream_checksum(stream_bytes)

        streams_data[flow_id] = {
            "stream_bytes": stream_bytes,
            "has_gaps": has_gaps,
            "gaps": gaps
        }

        per_flow_stats[flow_id] = {
            "segments_received": len(flow_segments),
            "stream_length": stream_length,
            "overlaps_detected": overlap_handler.overlap_count,
            "gaps": gaps,
            "checksum": checksum
        }

        total_overlaps += overlap_handler.overlap_count

    # Build report
    report_data = {
        "total_flows": len(flows),
        "total_segments": len(segments),
        "total_retransmits": total_retransmits,
        "total_overlaps": total_overlaps,
        "per_flow": per_flow_stats
    }

    # Write outputs
    write_outputs(streams_data, report_data)


if __name__ == "__main__":
    run_reassembly()
