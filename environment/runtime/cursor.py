import logging
import uuid
from datetime import datetime, timezone

from runtime.db import get_connection

logger = logging.getLogger("replay.cursor")


def create_session():
    return str(uuid.uuid4())


def initialize_cursors(session_id):
    """Create cursor entries for all active replay windows."""
    conn = get_connection()
    windows = conn.execute(
        "SELECT window_id FROM replay_windows WHERE status = 'active' ORDER BY window_start"
    ).fetchall()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    for w in windows:
        conn.execute(
            "INSERT INTO replay_cursor (session_id, window_id, position, last_event_ts, checkpoint_ts, state, updated_at) "
            "VALUES (?, ?, 0, NULL, ?, 'active', ?)",
            (session_id, w["window_id"], now, now),
        )

    conn.commit()
    conn.close()
    logger.info("initialized %d cursors for session %s", len(windows), session_id[:8])


def advance_cursor(session_id, window_id, new_position, last_ts):
    """Advance cursor position within a window. On window completion, transition to next."""
    conn = get_connection()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    conn.execute(
        "UPDATE replay_cursor SET position = ?, last_event_ts = ?, checkpoint_ts = ?, updated_at = ? "
        "WHERE session_id = ? AND window_id = ?",
        (new_position, last_ts, now, now, session_id, window_id),
    )
    conn.commit()
    conn.close()


def advance_to_next_window(session_id, current_window_id):
    """Move cursor to the next window after completing current one."""
    conn = get_connection()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    conn.execute(
        "UPDATE replay_cursor SET state = 'completed', updated_at = ? "
        "WHERE session_id = ? AND window_id = ?",
        (now, session_id, current_window_id),
    )

    next_window = conn.execute(
        "SELECT window_id FROM replay_windows WHERE window_id > ? AND status = 'active' ORDER BY window_id LIMIT 1",
        (current_window_id,),
    ).fetchone()

    if next_window:
        # reset position for new window
        conn.execute(
            "UPDATE replay_cursor SET position = 0, checkpoint_ts = ?, updated_at = ? "
            "WHERE session_id = ? AND window_id = ?",
            (now, now, session_id, next_window["window_id"]),
        )

    conn.commit()
    conn.close()
    return next_window["window_id"] if next_window else None


def simulate_concurrent_replay(session_id):
    """Simulate a second replay pass that checkpoints concurrently."""
    conn = get_connection()
    cursors = conn.execute(
        "SELECT cursor_id, window_id, position FROM replay_cursor "
        "WHERE session_id = ? AND state = 'active'",
        (session_id,),
    ).fetchall()

    stale_ts = "2024-01-15T08:00:00+00:00"
    for c in cursors:
        # write checkpoint without comparing existing checkpoint_ts
        conn.execute(
            "UPDATE replay_cursor SET position = ?, checkpoint_ts = ?, updated_at = ? "
            "WHERE cursor_id = ?",
            (0, stale_ts, stale_ts, c["cursor_id"]),
        )

    conn.commit()
    conn.close()
    logger.info("concurrent replay pass checkpointed %d cursors", len(cursors))


def get_active_cursors(session_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT cursor_id, window_id, position, state FROM replay_cursor "
        "WHERE session_id = ? AND state = 'active' ORDER BY window_id",
        (session_id,),
    ).fetchall()
    conn.close()
    return rows
