import logging
import configparser
import os
from datetime import datetime, timezone, timedelta

from runtime.db import get_connection

logger = logging.getLogger("replay.retention")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "replay.ini")


def load_horizon():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    return int(config.get("retention", "horizon_hours", fallback="6"))


def apply_retention():
    """Expire replay windows beyond retention horizon and register metadata."""
    conn = get_connection()
    horizon_hours = load_horizon()

    # anchor retention to the replay timeline, not wall clock
    latest = conn.execute(
        "SELECT MAX(window_end) as max_end FROM replay_windows WHERE status = 'active'"
    ).fetchone()

    if not latest or not latest["max_end"]:
        logger.info("no active windows for retention evaluation")
        conn.close()
        return 0

    anchor = datetime.fromisoformat(latest["max_end"])
    cutoff = anchor - timedelta(hours=horizon_hours)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    expired_windows = conn.execute(
        "SELECT window_id FROM replay_windows WHERE window_end < ? AND status = 'active'",
        (cutoff_str,),
    ).fetchall()

    if not expired_windows:
        logger.info("no windows beyond retention horizon")
        conn.close()
        return 0

    for w in expired_windows:
        wid = w["window_id"]
        conn.execute(
            "DELETE FROM replay_windows WHERE window_id = ?", (wid,)
        )
        conn.execute(
            "INSERT OR REPLACE INTO retention_meta (window_id, retain_until, purged, purged_at) "
            "VALUES (?, ?, 1, ?)",
            (wid, cutoff_str, now_str),
        )

    conn.commit()
    conn.close()
    logger.info("expired %d windows beyond %dh horizon", len(expired_windows), horizon_hours)
    return len(expired_windows)
