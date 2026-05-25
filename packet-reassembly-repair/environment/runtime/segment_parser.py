"""
Segment parser for packet capture logs.

Reads /app/runtime/capture.log and returns a list of parsed Segment objects.
Format: SEQ_NUM|FLOW_ID|PAYLOAD_HEX|FLAGS|TIMESTAMP
"""

from collections import namedtuple

Segment = namedtuple("Segment", ["seq_num", "flow_id", "payload", "flags", "timestamp"])

CAPTURE_LOG_PATH = "/app/runtime/capture.log"


def parse_capture_log(path=None):
    """Parse the capture log file and return a list of Segment objects."""
    if path is None:
        path = CAPTURE_LOG_PATH

    segments = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
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
