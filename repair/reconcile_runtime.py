#!/usr/bin/env python3
"""Replay runtime reconciliation.

Repairs corrupted replay state in-place after a defective runtime execution.
Operates directly on replay_state.db and regenerates export artifacts.
"""

import json
import hashlib
import os
import sys
import sqlite3
import logging
import configparser
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RUNTIME_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtime")
DB_PATH = os.path.join(RUNTIME_DIR, "replay_state.db")
CONFIG_PATH = os.path.join(RUNTIME_DIR, "config", "replay.ini")
EXPORTS_DIR = os.path.join(RUNTIME_DIR, "exports")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("repair.reconcile")


def get_connection():
    conn = sqlite3.connect(DB_PATH, isolation_level="DEFERRED")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def load_config():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    return config


def normalize_timestamp_correct(ts_str):
    """Correct UTC normalization including offset minutes."""
    ts_str = ts_str.strip()
    if ts_str.endswith("Z"):
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))

    if "+" in ts_str[10:]:
        sign_pos = ts_str.rindex("+")
        sign = 1
    elif ts_str.count("-") > 2:
        sign_pos = ts_str.rindex("-")
        sign = -1
    else:
        return datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)

    offset_part = ts_str[sign_pos + 1:]
    base_part = ts_str[:sign_pos]

    parts = offset_part.split(":")
    offset_hours = int(parts[0])
    offset_minutes = int(parts[1]) if len(parts) > 1 else 0
    offset_td = timedelta(hours=offset_hours, minutes=offset_minutes) * sign

    base_dt = datetime.fromisoformat(base_part).replace(tzinfo=timezone.utc)
    return base_dt - offset_td


def repair_timestamp_normalization(conn):
    """Re-normalize all raw timestamps with correct offset arithmetic."""
    rows = conn.execute("SELECT event_id, timestamp_raw, timestamp_norm FROM raw_events").fetchall()
    repaired = 0
    for row in rows:
        correct_dt = normalize_timestamp_correct(row["timestamp_raw"])
        correct_str = correct_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        if correct_str != row["timestamp_norm"]:
            conn.execute(
                "UPDATE raw_events SET timestamp_norm = ? WHERE event_id = ?",
                (correct_str, row["event_id"]),
            )
            repaired += 1
    conn.commit()
    logger.info("timestamp normalization: corrected %d/%d events", repaired, len(rows))
    return repaired


def rebuild_replay_windows(conn, config):
    """Rebuild window assignments with correct boundary semantics and deterministic ordering."""
    window_size = int(config.get("replay", "window_size_seconds", fallback="300"))

    # clear existing windows
    conn.execute("DELETE FROM replay_windows")
    conn.commit()

    rows = conn.execute(
        "SELECT event_id, timestamp_norm FROM raw_events ORDER BY timestamp_norm, event_id"
    ).fetchall()

    if not rows:
        logger.warning("no events for window reconstruction")
        return 0

    first_ts = datetime.fromisoformat(rows[0]["timestamp_norm"])
    last_ts = datetime.fromisoformat(rows[-1]["timestamp_norm"])

    # align grid to epoch
    epoch = datetime(2024, 1, 15, tzinfo=timezone.utc)
    elapsed = (first_ts - epoch).total_seconds()
    grid_offset = int(elapsed // window_size) * window_size
    grid_start = epoch + timedelta(seconds=grid_offset)

    # build grid
    grid = []
    cursor = grid_start
    while cursor <= last_ts:
        grid.append((cursor, cursor + timedelta(seconds=window_size)))
        cursor += timedelta(seconds=window_size)

    # assign events to windows using strict less-than on upper bound
    window_events = {i: [] for i in range(len(grid))}
    for row in rows:
        evt_ts = datetime.fromisoformat(row["timestamp_norm"])
        for i, (w_start, w_end) in enumerate(grid):
            if evt_ts >= w_start and evt_ts < w_end:
                window_events[i].append(row["event_id"])
                break

    # persist non-empty windows with deterministic event ordering
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    built = 0
    for i, (w_start, w_end) in enumerate(grid):
        event_ids = window_events[i]
        if not event_ids:
            continue

        # stable sort: already ordered by (timestamp_norm, event_id) from query
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
    logger.info("rebuilt %d replay windows with correct boundaries", built)
    return built


def reconcile_retention(conn, config):
    """Re-apply retention against corrected windows."""
    horizon_hours = int(config.get("retention", "horizon_hours", fallback="4"))

    # clear stale retention metadata
    conn.execute("DELETE FROM retention_meta")

    latest = conn.execute(
        "SELECT MAX(window_end) as max_end FROM replay_windows WHERE status = 'active'"
    ).fetchone()

    if not latest or not latest["max_end"]:
        conn.commit()
        return 0

    anchor = datetime.fromisoformat(latest["max_end"])
    cutoff = anchor - timedelta(hours=horizon_hours)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    expired = conn.execute(
        "SELECT window_id FROM replay_windows WHERE window_end < ? AND status = 'active'",
        (cutoff_str,),
    ).fetchall()

    for w in expired:
        wid = w["window_id"]
        conn.execute(
            "INSERT INTO retention_meta (window_id, retain_until, purged, purged_at) VALUES (?, ?, 1, ?)",
            (wid, cutoff_str, now_str),
        )
        conn.execute("DELETE FROM replay_windows WHERE window_id = ?", (wid,))

    conn.commit()
    logger.info("retention reconciled: %d windows expired", len(expired))
    return len(expired)


def reconcile_cursors(conn):
    """Repair cursor state: mark orphaned cursors as stale, fix checkpoint drift."""
    # identify existing window IDs
    active_windows = {
        r["window_id"]
        for r in conn.execute("SELECT window_id FROM replay_windows").fetchall()
    }

    # mark cursors pointing to purged windows
    all_cursors = conn.execute("SELECT cursor_id, window_id, state FROM replay_cursor").fetchall()
    orphaned = 0
    for c in all_cursors:
        if c["window_id"] not in active_windows and c["state"] == "active":
            conn.execute(
                "UPDATE replay_cursor SET state = 'stale' WHERE cursor_id = ?",
                (c["cursor_id"],),
            )
            orphaned += 1

    # repair checkpoint drift: for remaining active cursors, ensure checkpoint_ts
    # is not stale relative to the runtime execution window
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    conn.execute(
        "UPDATE replay_cursor SET checkpoint_ts = ?, updated_at = ?, position = 0 "
        "WHERE state = 'active'",
        (now_str, now_str),
    )

    conn.commit()
    logger.info("cursor reconciliation: %d orphaned marked stale, active cursors checkpoint-reset", orphaned)
    return orphaned


def regenerate_export(conn, config):
    """Regenerate timeline export from repaired state."""
    rel_path = config.get("export", "output_path", fallback="runtime/exports")
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    export_path = os.path.join(base, rel_path)
    os.makedirs(export_path, exist_ok=True)

    timeline_path = os.path.join(export_path, "reconstructed_timeline.jsonl")
    integrity_path = os.path.join(export_path, "replay_integrity.json")

    windows = conn.execute(
        "SELECT window_id, event_ids FROM replay_windows WHERE status = 'active' ORDER BY window_start"
    ).fetchall()

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

    logger.info("export rebuilt: %d events, %d windows → %s", event_count, len(windows), timeline_path)
    return timeline_path, integrity_path


def main():
    logger.info("replay runtime reconciliation starting")

    if not os.path.exists(DB_PATH):
        logger.error("no replay state found at %s", DB_PATH)
        sys.exit(1)

    config = load_config()
    conn = get_connection()

    # phase 1: correct timestamp normalization
    repair_timestamp_normalization(conn)

    # phase 2: rebuild replay windows with correct boundaries
    rebuild_replay_windows(conn, config)

    # phase 3: re-apply retention with corrected timestamps
    reconcile_retention(conn, config)

    # phase 4: reconcile cursor state
    reconcile_cursors(conn)

    # phase 5: regenerate exports from repaired state
    regenerate_export(conn, config)

    conn.close()
    logger.info("reconciliation complete")


if __name__ == "__main__":
    main()
