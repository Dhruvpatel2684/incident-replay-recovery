"""Replay recovery behavioral tests.

Validates runtime invariants against replay state and exported artifacts.
Expects replay_state.db and exports to already exist from a prior runtime execution.
"""

import json
import hashlib
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from collections import Counter

BASE_DIR = "/app"
RUNTIME_DIR = os.path.join(BASE_DIR, "runtime")
DB_PATH = os.path.join(RUNTIME_DIR, "replay_state.db")
EXPORTS_DIR = os.path.join(RUNTIME_DIR, "exports")
TIMELINE_PATH = os.path.join(EXPORTS_DIR, "reconstructed_timeline.jsonl")
INTEGRITY_PATH = os.path.join(EXPORTS_DIR, "replay_integrity.json")
RUN_REPLAY = os.path.join(RUNTIME_DIR, "run_replay.py")
SOLVE_SCRIPT = os.path.join(BASE_DIR, "solution", "solve.sh")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def parse_iso(ts_str):
    return datetime.fromisoformat(ts_str)


def correct_utc_normalize(raw_ts):
    """Reference implementation of correct UTC normalization."""
    ts_str = raw_ts.strip()
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


def test_monotonic_ordering():
    """Exported timeline events must be in non-decreasing timestamp order."""
    assert os.path.exists(TIMELINE_PATH), "timeline file missing"

    prev_ts = None
    with open(TIMELINE_PATH) as f:
        for line in f:
            record = json.loads(line.strip())
            ts = parse_iso(record["timestamp"])
            if prev_ts is not None:
                assert ts >= prev_ts, f"ordering violation: {ts} < {prev_ts}"
            prev_ts = ts


def test_no_duplicate_events():
    """No event_id may appear more than once in the exported timeline."""
    assert os.path.exists(TIMELINE_PATH), "timeline file missing"

    event_ids = []
    with open(TIMELINE_PATH) as f:
        for line in f:
            record = json.loads(line.strip())
            event_ids.append(record["event_id"])

    counts = Counter(event_ids)
    duplicates = {k: v for k, v in counts.items() if v > 1}
    assert len(duplicates) == 0, f"duplicated event_ids: {list(duplicates.keys())[:5]}"


def test_utc_normalization():
    """All timestamp_norm values must match correct UTC conversion from timestamp_raw."""
    conn = get_db()
    rows = conn.execute("SELECT event_id, timestamp_raw, timestamp_norm FROM raw_events").fetchall()
    conn.close()

    drift_events = []
    for row in rows:
        expected = correct_utc_normalize(row["timestamp_raw"])
        actual = parse_iso(row["timestamp_norm"])
        drift = abs((actual - expected).total_seconds())
        if drift > 0:
            drift_events.append((row["event_id"], drift))

    assert len(drift_events) == 0, f"{len(drift_events)} events with normalization drift"


def test_cursor_consistency():
    """All active cursors must reference valid positions within their assigned windows."""
    conn = get_db()
    cursors = conn.execute(
        "SELECT cursor_id, window_id, position, state FROM replay_cursor WHERE state = 'active'"
    ).fetchall()

    invalid = []
    for c in cursors:
        window = conn.execute(
            "SELECT event_ids FROM replay_windows WHERE window_id = ?", (c["window_id"],)
        ).fetchone()
        if window is None:
            invalid.append(c["cursor_id"])
            continue
        event_count = len(json.loads(window["event_ids"]))
        if c["position"] < 0 or c["position"] > event_count:
            invalid.append(c["cursor_id"])

    conn.close()
    assert len(invalid) == 0, f"{len(invalid)} cursors with invalid position or missing window"


def test_no_cursors_on_purged_windows():
    """No active cursor may point to a purged or deleted window."""
    conn = get_db()
    active_cursors = conn.execute(
        "SELECT cursor_id, window_id FROM replay_cursor WHERE state = 'active'"
    ).fetchall()

    purged = conn.execute(
        "SELECT window_id FROM retention_meta WHERE purged = 1"
    ).fetchall()
    purged_wids = {r["window_id"] for r in purged}

    existing_windows = conn.execute("SELECT window_id FROM replay_windows").fetchall()
    existing_wids = {r["window_id"] for r in existing_windows}
    conn.close()

    orphaned = []
    for c in active_cursors:
        wid = c["window_id"]
        if wid in purged_wids or wid not in existing_wids:
            orphaned.append(c["cursor_id"])

    assert len(orphaned) == 0, f"{len(orphaned)} active cursors on purged/missing windows"


def test_deterministic_ordering():
    """Same-timestamp events must be ordered by event_id for deterministic output."""
    assert os.path.exists(TIMELINE_PATH), "timeline file missing"

    events = []
    with open(TIMELINE_PATH) as f:
        for line in f:
            record = json.loads(line.strip())
            events.append((record["timestamp"], record["event_id"]))

    violations = 0
    i = 0
    while i < len(events):
        j = i
        while j < len(events) and events[j][0] == events[i][0]:
            j += 1
        group_ids = [e[1] for e in events[i:j]]
        if group_ids != sorted(group_ids):
            violations += 1
        i = j

    assert violations == 0, f"{violations} timestamp groups with non-deterministic ordering"


def test_checkpoint_monotonicity():
    """No active cursor may have a stale checkpoint relative to its runtime epoch."""
    conn = get_db()

    latest_window = conn.execute("SELECT MAX(created_at) as latest FROM replay_windows").fetchone()
    if not latest_window or not latest_window["latest"]:
        conn.close()
        return

    runtime_epoch = parse_iso(latest_window["latest"])

    stale_cursors = conn.execute(
        "SELECT cursor_id, checkpoint_ts FROM replay_cursor WHERE state = 'active'"
    ).fetchall()
    conn.close()

    regressions = []
    for s in stale_cursors:
        if parse_iso(s["checkpoint_ts"]) < runtime_epoch - timedelta(hours=24):
            regressions.append(s["cursor_id"])

    assert len(regressions) == 0, f"{len(regressions)} checkpoint regressions detected"


def test_export_checksum_stability():
    """Two consecutive runtime+repair runs must produce identical export checksums."""
    assert os.path.exists(INTEGRITY_PATH), "integrity file missing"

    with open(INTEGRITY_PATH) as f:
        first_integrity = json.load(f)
    first_sha = first_integrity["sha256"]

    # run full recovery again
    rc = subprocess.run(
        [sys.executable, RUN_REPLAY],
        capture_output=True, text=True, cwd=BASE_DIR,
    ).returncode
    assert rc == 0, "replay runtime failed on second run"

    rc = subprocess.run(
        [sys.executable, os.path.join(BASE_DIR, "solution", "reconcile_runtime.py")],
        capture_output=True, text=True, cwd=BASE_DIR,
    ).returncode
    assert rc == 0, "reconciliation failed on second run"

    with open(INTEGRITY_PATH) as f:
        second_integrity = json.load(f)
    second_sha = second_integrity["sha256"]

    assert first_sha == second_sha, f"checksum mismatch: {first_sha[:16]}... vs {second_sha[:16]}..."


def test_window_uniqueness():
    """No event_id may be assigned to more than one replay window."""
    conn = get_db()
    windows = conn.execute("SELECT window_id, event_ids FROM replay_windows").fetchall()
    conn.close()

    event_windows = {}
    for w in windows:
        eids = json.loads(w["event_ids"])
        for eid in eids:
            event_windows.setdefault(eid, []).append(w["window_id"])

    multi_assigned = {k: v for k, v in event_windows.items() if len(v) > 1}
    assert len(multi_assigned) == 0, f"{len(multi_assigned)} events in multiple windows"


def test_referential_integrity():
    """Every event_id referenced in replay_windows must exist in raw_events."""
    conn = get_db()
    windows = conn.execute("SELECT window_id, event_ids FROM replay_windows").fetchall()
    raw_ids = {r["event_id"] for r in conn.execute("SELECT event_id FROM raw_events").fetchall()}
    conn.close()

    dangling = []
    for w in windows:
        eids = json.loads(w["event_ids"])
        for eid in eids:
            if eid not in raw_ids:
                dangling.append((eid, w["window_id"]))

    assert len(dangling) == 0, f"{len(dangling)} dangling event references"


def test_export_integrity_metadata():
    """replay_integrity.json must match actual timeline content."""
    assert os.path.exists(INTEGRITY_PATH), "integrity file missing"
    assert os.path.exists(TIMELINE_PATH), "timeline file missing"

    with open(INTEGRITY_PATH) as f:
        meta = json.load(f)

    line_count = 0
    hasher = hashlib.sha256()
    with open(TIMELINE_PATH) as f:
        for line in f:
            hasher.update(line.strip().encode("utf-8"))
            line_count += 1

    assert meta["event_count"] == line_count, f"count mismatch: {meta['event_count']} vs {line_count}"
    assert meta["sha256"] == hasher.hexdigest(), "hash mismatch in integrity metadata"
