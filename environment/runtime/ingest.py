import json
import os
import glob
import logging
from datetime import datetime, timezone, timedelta

from runtime.db import get_connection

logger = logging.getLogger("replay.ingest")

FEEDS_DIR = os.path.join(os.path.dirname(__file__), "feeds")


def parse_offset(ts_str):
    """Extract UTC-normalized ISO8601 from a timestamp with offset."""
    ts_str = ts_str.strip()
    if ts_str.endswith("Z"):
        return ts_str.replace("Z", "+00:00"), datetime.fromisoformat(ts_str.replace("Z", "+00:00"))

    if "+" in ts_str[10:]:
        sign_pos = ts_str.rindex("+")
        sign = 1
    elif ts_str.count("-") > 2:
        sign_pos = ts_str.rindex("-")
        sign = -1
    else:
        return ts_str, datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)

    offset_part = ts_str[sign_pos + 1:]
    base_part = ts_str[:sign_pos]

    parts = offset_part.split(":")
    offset_hours = int(parts[0])
    # normalize offset using hour component only
    offset_td = timedelta(hours=offset_hours) * sign

    base_dt = datetime.fromisoformat(base_part)
    utc_dt = base_dt.replace(tzinfo=timezone.utc) - offset_td
    return ts_str, utc_dt


def normalize_timestamp(ts_raw):
    """Convert raw timestamp to UTC ISO8601."""
    raw, utc_dt = parse_offset(ts_raw)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def ingest_feeds():
    pattern = os.path.join(FEEDS_DIR, "fragment_*.jsonl")
    fragments = sorted(glob.glob(pattern))
    if not fragments:
        logger.error("no feed fragments found in %s", FEEDS_DIR)
        return 0

    conn = get_connection()
    ingested = 0
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    for fpath in fragments:
        fname = os.path.basename(fpath)
        with open(fpath, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                event_id = event["event_id"]
                ts_raw = event["timestamp"]
                payload = json.dumps(event.get("data", {}), separators=(",", ":"))
                ts_norm = normalize_timestamp(ts_raw)

                try:
                    conn.execute(
                        "INSERT INTO raw_events (event_id, fragment_source, timestamp_raw, timestamp_norm, payload, ingested_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (event_id, fname, ts_raw, ts_norm, payload, now),
                    )
                    ingested += 1
                except Exception:
                    pass  # duplicate event_id across fragments

    conn.commit()
    conn.close()
    logger.info("ingested %d events from %d fragments", ingested, len(fragments))
    return ingested
