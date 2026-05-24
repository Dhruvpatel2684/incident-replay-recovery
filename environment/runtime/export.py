import json
import hashlib
import os
import logging
import configparser
from datetime import datetime, timezone

from runtime.db import get_connection

logger = logging.getLogger("replay.export")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "replay.ini")


def load_export_path():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    rel = config.get("export", "output_path", fallback="runtime/exports")
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def export_timeline():
    """Export reconstructed timeline from active replay windows."""
    conn = get_connection()
    export_path = load_export_path()
    os.makedirs(export_path, exist_ok=True)

    windows = conn.execute(
        "SELECT window_id, event_ids FROM replay_windows WHERE status = 'active' ORDER BY window_start"
    ).fetchall()

    timeline_path = os.path.join(export_path, "reconstructed_timeline.jsonl")
    integrity_path = os.path.join(export_path, "replay_integrity.json")

    hasher = hashlib.sha256()
    event_count = 0

    with open(timeline_path, "w") as tf:
        for w in windows:
            event_ids = json.loads(w["event_ids"])
            for eid in event_ids:
                row = conn.execute(
                    "SELECT event_id, timestamp_norm, payload FROM raw_events WHERE event_id = ?",
                    (eid,),
                ).fetchone()
                if row is None:
                    continue
                record = {
                    "event_id": row["event_id"],
                    "timestamp": row["timestamp_norm"],
                    "payload": json.loads(row["payload"]),
                }
                line = json.dumps(record, separators=(",", ":"), sort_keys=True)
                tf.write(line + "\n")
                hasher.update(line.encode("utf-8"))
                event_count += 1

    integrity = {
        "sha256": hasher.hexdigest(),
        "event_count": event_count,
        "window_count": len(windows),
        "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
    }
    with open(integrity_path, "w") as f:
        json.dump(integrity, f, indent=2)

    conn.close()
    logger.info("exported %d events across %d windows → %s", event_count, len(windows), timeline_path)
    return timeline_path, integrity_path
