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
    Format: SECONDS.MICROSECONDS
    """
    # BUG 2: Truncates to milliseconds (3 decimal places) instead of preserving
    # full microsecond precision (6 decimal places). This causes events at
    # 1716000000.100200 (node-1 VOTE_GRANT) and 1716000000.100200 (node-3 VOTE_GRANT)
    # to sort correctly, but events within the same millisecond lose ordering.
    parts = ts_str.split(".")
    if len(parts) == 2:
        # Truncate to 3 decimal places (milliseconds)
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

    # Extract term number based on event type
    if "term" in payload:
        # BUG 1: For VOTE_REQUEST events, incorrectly extracts the term by
        # taking the character index position from the payload string rather
        # than the parsed value. This happens because we re-split the raw
        # payload_str looking for "term" and use find() offset logic.
        if event_type == "VOTE_REQUEST":
            # Attempt to extract term from raw string position
            term_pos = payload_str.find("term=")
            # BUG: uses position-based extraction that gets the wrong substring
            # when other numeric fields appear before 'term' in the payload
            raw_after_term = payload_str[term_pos + 5:]
            # Takes chars until comma, but starts from wrong offset in some cases
            term_val = raw_after_term.split(",")[0]
            # Incorrectly adds 1 to the extracted term (off-by-one from position math)
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

    # Sort by timestamp (BUG 2 interaction: truncated timestamps cause
    # ties that Python's stable sort resolves by file order, but this
    # may differ from true chronological order at microsecond level)
    events.sort(key=lambda e: e["timestamp"])
    return events
