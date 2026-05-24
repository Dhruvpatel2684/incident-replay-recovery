import json
import logging
from datetime import datetime, timezone, timedelta
import configparser
import os

from runtime.db import get_connection

logger = logging.getLogger("replay.reconstruct")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "replay.ini")


def load_window_size():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    return int(config.get("replay", "window_size_seconds", fallback="300"))


def build_windows():
    """Construct replay windows on a fixed grid and assign events to matching windows."""
    conn = get_connection()
    window_size = load_window_size()

    rows = conn.execute(
        "SELECT event_id, timestamp_norm FROM raw_events ORDER BY timestamp_norm"
    ).fetchall()

    if not rows:
        logger.warning("no events to reconstruct")
        conn.close()
        return 0

    # determine grid boundaries from event range, anchored to epoch-aligned intervals
    first_ts = datetime.fromisoformat(rows[0]["timestamp_norm"])
    last_ts = datetime.fromisoformat(rows[-1]["timestamp_norm"])

    # align grid start to the nearest lower window boundary
    epoch = datetime(2024, 1, 15, tzinfo=timezone.utc)
    elapsed = (first_ts - epoch).total_seconds()
    grid_offset = int(elapsed // window_size) * window_size
    grid_start = epoch + timedelta(seconds=grid_offset)

    # build fixed window grid
    grid = []
    cursor = grid_start
    while cursor <= last_ts:
        grid.append((cursor, cursor + timedelta(seconds=window_size)))
        cursor = cursor + timedelta(seconds=window_size)

    # assign events to windows
    window_events = {i: [] for i in range(len(grid))}
    for row in rows:
        evt_ts = datetime.fromisoformat(row["timestamp_norm"])
        for i, (w_start, w_end) in enumerate(grid):
            if evt_ts >= w_start and evt_ts <= w_end:
                window_events[i].append(row["event_id"])

    # persist non-empty windows
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    built = 0
    for i, (w_start, w_end) in enumerate(grid):
        event_ids = window_events[i]
        if not event_ids:
            continue
        conn.execute(
            "INSERT INTO replay_windows (window_start, window_end, event_ids, status, created_at) "
            "VALUES (?, ?, ?, 'active', ?)",
            (
                w_start.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                w_end.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                json.dumps(event_ids),
                now,
            ),
        )
        built += 1

    conn.commit()
    conn.close()
    logger.info("built %d replay windows from %d events", built, len(rows))
    return built
