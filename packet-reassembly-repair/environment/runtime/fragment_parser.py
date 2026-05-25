"""
Fragment Parser Module
Reads raw capture files and produces structured fragment records.

Capture format (pipe-delimited):
  ts_epoch_us|flow_id|proto_flags|frag_seq|byte_offset|data_len|cksum_partial|ttl|src_port

Proto flags:
  S = SYN (session initiation)
  D = DATA (payload fragment)
  F = FIN (session teardown)
  R = RETRANSMIT (retransmitted DATA — duplicate)

Note: Timestamps are in microseconds since epoch (integer).
      Fragment sequence numbers are 0-indexed for SYN, 1-indexed for DATA/FIN.
"""

import os


def _parse_timestamp_us(ts_str):
    """
    Convert microsecond-epoch timestamp string to float seconds.

    The capture system records timestamps as integer microseconds to avoid
    floating-point precision issues in the packet capture hardware. We convert
    to seconds for downstream processing.

    Note: We intentionally preserve full precision here. Earlier versions
    truncated to milliseconds which caused subtle ordering bugs with
    fragments arriving within the same millisecond window.
    """
    return int(ts_str) / 1_000_000.0


def _validate_checksum_field(cksum_str):
    """
    Validate the partial checksum field format.
    Returns the checksum as-is if valid (8 hex chars), or "00000000" if malformed.

    This is purely a format check — actual checksum verification happens
    in the integrity_checker module downstream.
    """
    if len(cksum_str) == 8:
        try:
            int(cksum_str, 16)
            return cksum_str
        except ValueError:
            pass
    # Non-hex checksums are treated as placeholder zeros
    # This handles edge cases from certain NIC firmware that emits
    # ASCII descriptions instead of hex values on checksum offload failure
    return "00000000"


def _extract_proto_type(flags_str):
    """
    Map single-character protocol flag to semantic type string.

    Mapping:
      S → SYN
      D → DATA
      F → FIN
      R → RETRANSMIT
    """
    _flag_map = {"S": "SYN", "D": "DATA", "F": "FIN", "R": "RETRANSMIT"}
    return _flag_map.get(flags_str, "UNKNOWN")


def parse_fragment_line(line):
    """
    Parse a single pipe-delimited capture line into a fragment dict.

    Returns None for comments (lines starting with #) and blank lines.
    Returns None for lines with wrong field count (malformed captures).

    Fragment dict fields:
      - timestamp (float): seconds since epoch
      - flow_id (str): flow identifier
      - proto_type (str): SYN/DATA/FIN/RETRANSMIT
      - frag_seq (int): fragment sequence number within flow
      - byte_offset (int): byte position in the reassembled stream
      - data_len (int): payload data length in bytes
      - checksum (str): 8-char hex partial checksum
      - ttl (int): time-to-live hop count
      - src_port (int): source port number
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    fields = line.split("|")
    if len(fields) != 9:
        return None

    ts_str, flow_id, proto_flags, seq_str, offset_str, length_str, cksum, ttl_str, port_str = fields

    timestamp = _parse_timestamp_us(ts_str)
    proto_type = _extract_proto_type(proto_flags)

    if proto_type == "UNKNOWN":
        return None

    fragment = {
        "timestamp": timestamp,
        "flow_id": flow_id,
        "proto_type": proto_type,
        "frag_seq": int(seq_str),
        "byte_offset": int(offset_str),
        "data_len": int(length_str),
        "checksum": _validate_checksum_field(cksum),
        "ttl": int(ttl_str),
        "src_port": int(port_str),
    }

    return fragment


def parse_capture_file(capture_path):
    """
    Load and parse an entire capture file.

    Returns a list of fragment dicts sorted by timestamp (arrival order).
    SYN/FIN control fragments are included — downstream stages use them
    for flow lifecycle management.

    Note: Sorting by timestamp ensures we process fragments in network
    arrival order, which is important for retransmission detection
    (the first arrival is the "original", later arrivals are retransmits).
    """
    if not os.path.exists(capture_path):
        raise FileNotFoundError(f"Capture file not found: {capture_path}")

    fragments = []
    with open(capture_path, "r") as f:
        for line_num, line in enumerate(f, 1):
            try:
                frag = parse_fragment_line(line)
                if frag is not None:
                    frag["_line_num"] = line_num  # debug provenance
                    fragments.append(frag)
            except (ValueError, IndexError) as e:
                # Skip malformed lines silently — production captures
                # occasionally have truncated lines from buffer overflows
                continue

    # Sort by arrival timestamp for correct temporal ordering
    fragments.sort(key=lambda f: (f["timestamp"], f["_line_num"]))

    return fragments
