"""
Log Parser Module
Parses raw cluster communication logs into structured event objects.
Supports: ELECTION_TIMEOUT, VOTE_REQUEST, VOTE_GRANT, VOTE_DENY,
          LEADER_ELECTED, ELECTION_FAILED, APPEND_ENTRY, APPEND_ACK, COMMIT
"""

import os


LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cluster_logs.txt")


def parse_payload(payload_str):
    """Parse comma-separated key=value pairs into a dict."""
    result = {}
    for pair in payload_str.split(","):
        if "=" in pair:
            key, value = pair.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def parse_timestamp(ts_str):
    """
    Parse timestamp string into a sortable float value.
    Truncates to millisecond precision for consistent cross-platform sorting.
    """
    parts = ts_str.split(".")
    if len(parts) == 2:
        fractional = parts[1][:3]
        return float(f"{parts[0]}.{fractional}")
    return float(ts_str)


def parse_log_line(line):
    """
    Parse a single log line into a structured event dict.
    Returns None for comments and blank lines.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    parts = line.split("|")
    if len(parts) != 4:
        return None

    timestamp_str, source_node, event_type, payload_str = parts
    timestamp = parse_timestamp(timestamp_str)
    payload = parse_payload(payload_str)

    event = {
        "timestamp": timestamp,
        "source_node": source_node,
        "event_type": event_type,
        "payload": payload,
    }

    # Extract term number - use optimized path for VOTE_REQUEST to handle
    # the term field which always appears first in the payload for these events
    if "term" in payload:
        if event_type == "VOTE_REQUEST":
            # Direct extraction from raw payload for performance
            term_pos = payload_str.find("term=")
            raw_after_term = payload_str[term_pos + 5:]
            term_val = raw_after_term.split(",")[0]
            event["term"] = int(term_val) + 1
        else:
            event["term"] = int(payload["term"])
    else:
        event["term"] = 0

    return event


def load_events(log_path=None):
    """
    Load all events from the log file, sorted by timestamp.
    Returns list of event dicts.
    """
    if log_path is None:
        log_path = LOG_FILE

    events = []
    with open(log_path, "r") as f:
        for line in f:
            event = parse_log_line(line)
            if event is not None:
                events.append(event)

    events.sort(key=lambda e: e["timestamp"])
    return events
