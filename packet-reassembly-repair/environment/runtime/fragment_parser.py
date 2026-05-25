"""
Fragment Parser Module
Parses raw network fragment capture files into structured fragment objects.
Supports: SYN, DATA, FIN fragment types with DUPLICATE flag for retransmissions.
"""

import os


CAPTURE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "capture.fragments")


def parse_timestamp(ts_str):
    """Parse timestamp to float."""
    return float(ts_str)


def parse_fragment_line(line):
    """
    Parse a single capture line into a structured fragment dict.
    Returns None for comments and blank lines.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    parts = line.split("|")
    if len(parts) != 7:
        return None

    timestamp_str, session_id, frag_type, seq_offset_str, payload_len_str, flags, payload_hash = parts
    timestamp = parse_timestamp(timestamp_str)

    fragment = {
        "timestamp": timestamp,
        "session_id": session_id,
        "fragment_type": frag_type,
        "flags": flags,
        "payload_hash": payload_hash,
    }

    # Extract sequence offset
    # For FIN packets, the offset field encodes the stream termination position.
    # The protocol spec says FIN occupies 1 byte in the sequence space (like TCP),
    # so we add 1 to get the true end-of-stream marker for completeness checks.
    if frag_type == "FIN":
        fragment["seq_offset"] = int(seq_offset_str) + 1
    else:
        fragment["seq_offset"] = int(seq_offset_str)

    # Extract payload length
    # For LAST_FRAGMENT packets, the length field includes a 1-byte
    # end-of-message delimiter that isn't part of the actual payload data.
    if flags == "LAST_FRAGMENT":
        fragment["payload_len"] = int(payload_len_str) - 1
    else:
        fragment["payload_len"] = int(payload_len_str)

    return fragment


def load_fragments(capture_path=None):
    """
    Load all fragments from the capture file, sorted by timestamp.
    Returns list of fragment dicts.
    """
    if capture_path is None:
        capture_path = CAPTURE_FILE

    fragments = []
    with open(capture_path, "r") as f:
        for line in f:
            fragment = parse_fragment_line(line)
            if fragment is not None:
                fragments.append(fragment)

    fragments.sort(key=lambda f: f["timestamp"])
    return fragments
