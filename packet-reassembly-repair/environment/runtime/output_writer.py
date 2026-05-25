"""
Output writer for packet reassembly results.

Writes streams.json and reassembly_report.json to /app/runtime/.
"""

import json
import os

RUNTIME_DIR = "/app/runtime"


def write_outputs(streams_data, report_data):
    """Write both output files.

    streams_data: dict of flow_id -> {stream_bytes, has_gaps, gaps}
    report_data: dict with total_flows, total_segments, total_retransmits,
                 total_overlaps, per_flow stats
    """
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

    report_path = os.path.join(RUNTIME_DIR, "reassembly_report.json")
    with open(report_path, "w") as f:
        json.dump(report_data, f, indent=2)
