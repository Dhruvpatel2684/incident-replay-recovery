#!/usr/bin/env python3
"""Replay recovery behavioral audit.

Validates runtime invariants against replay state and exported artifacts.
Expects replay_state.db and exports to already exist from a prior pipeline run.
"""

import json
import hashlib
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from collections import Counter

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_DIR = os.path.join(BASE_DIR, "runtime")
DB_PATH = os.path.join(RUNTIME_DIR, "replay_state.db")
EXPORTS_DIR = os.path.join(RUNTIME_DIR, "exports")
TIMELINE_PATH = os.path.join(EXPORTS_DIR, "reconstructed_timeline.jsonl")
INTEGRITY_PATH = os.path.join(EXPORTS_DIR, "replay_integrity.json")
RUN_REPLAY = os.path.join(RUNTIME_DIR, "run_replay.py")
REPAIR_SCRIPT = os.path.join(BASE_DIR, "repair", "reconcile_runtime.py")


class AuditResult:
    def __init__(self):
        self.passed = []
        self.failed = []

    def record(self, name, ok, detail=""):
        if ok:
            self.passed.append(name)
        else:
            self.failed.append((name, detail))

    def summary(self):
        total = len(self.passed) + len(self.failed)
        print(f"\n{'='*60}")
        print(f"REPLAY AUDIT: {len(self.passed)}/{total} checks passed")
        print(f"{'='*60}")
        if self.failed:
            for name, detail in self.failed:
                print(f"  FAIL: {name}")
                if detail:
                    print(f"        {detail}")
        return len(self.failed) == 0


def run_pipeline_with_repair():
    """Execute runtime then repair, return exit code."""
    rc = subprocess.run(
        [sys.executable, RUN_REPLAY],
        capture_output=True, text=True, cwd=BASE_DIR,
    ).returncode
    if rc != 0:
        return rc
    rc = subprocess.run(
        [sys.executable, REPAIR_SCRIPT],
        capture_output=True, text=True, cwd=BASE_DIR,
    ).returncode
    return rc


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


# --- AUDIT CHECKS ---


def check_monotonic_ordering(audit):
    """Verify exported timeline events are in strictly non-decreasing timestamp order."""
    if not os.path.exists(TIMELINE_PATH):
        audit.record("monotonic_ordering", False, "timeline file missing")
        return

    prev_ts = None
    violations = 0
    with open(TIMELINE_PATH) as f:
        for line in f:
            record = json.loads(line.strip())
            ts = parse_iso(record["timestamp"])
            if prev_ts is not None and ts < prev_ts:
                violations += 1
            prev_ts = ts

    audit.record(
        "monotonic_ordering",
        violations == 0,
        f"{violations} ordering violations in exported timeline" if violations else "",
    )


def check_no_duplicate_events(audit):
    """Verify no event_id appears more than once in the exported timeline."""
    if not os.path.exists(TIMELINE_PATH):
        audit.record("no_duplicate_events", False, "timeline file missing")
        return

    event_ids = []
    with open(TIMELINE_PATH) as f:
        for line in f:
            record = json.loads(line.strip())
            event_ids.append(record["event_id"])

    counts = Counter(event_ids)
    duplicates = {k: v for k, v in counts.items() if v > 1}
    audit.record(
        "no_duplicate_events",
        len(duplicates) == 0,
        f"{len(duplicates)} duplicated event_ids in export: {list(duplicates.keys())[:5]}" if duplicates else "",
    )


def check_utc_normalization(audit):
    """Verify all timestamp_norm values match correct UTC conversion from timestamp_raw."""
    conn = get_db()
    rows = conn.execute("SELECT event_id, timestamp_raw, timestamp_norm FROM raw_events").fetchall()
    conn.close()

    drift_count = 0
    max_drift_seconds = 0
    for row in rows:
        expected = correct_utc_normalize(row["timestamp_raw"])
        actual = parse_iso(row["timestamp_norm"])
        drift = abs((actual - expected).total_seconds())
        if drift > 0:
            drift_count += 1
            max_drift_seconds = max(max_drift_seconds, drift)

    audit.record(
        "utc_normalization",
        drift_count == 0,
        f"{drift_count} events with normalization drift (max {max_drift_seconds}s)" if drift_count else "",
    )


def check_cursor_consistency(audit):
    """Verify all active cursors reference valid positions within their assigned windows."""
    conn = get_db()
    cursors = conn.execute(
        "SELECT cursor_id, window_id, position, state FROM replay_cursor WHERE state = 'active'"
    ).fetchall()

    invalid = 0
    for c in cursors:
        window = conn.execute(
            "SELECT event_ids FROM replay_windows WHERE window_id = ?", (c["window_id"],)
        ).fetchone()
        if window is None:
            invalid += 1
            continue
        event_count = len(json.loads(window["event_ids"]))
        if c["position"] < 0 or c["position"] > event_count:
            invalid += 1

    conn.close()
    audit.record(
        "cursor_consistency",
        invalid == 0,
        f"{invalid} cursors with invalid position or missing window reference" if invalid else "",
    )


def check_no_cursors_on_purged_windows(audit):
    """Verify no active cursor points to a purged (deleted) window."""
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

    audit.record(
        "no_cursors_on_purged_windows",
        len(orphaned) == 0,
        f"{len(orphaned)} active cursors referencing purged/missing windows" if orphaned else "",
    )


def check_deterministic_ordering(audit):
    """Verify same-timestamp events are ordered by event_id for deterministic output."""
    if not os.path.exists(TIMELINE_PATH):
        audit.record("deterministic_ordering", False, "timeline file missing")
        return

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

    audit.record(
        "deterministic_ordering",
        violations == 0,
        f"{violations} timestamp groups with non-deterministic event_id ordering" if violations else "",
    )


def check_checkpoint_monotonicity(audit):
    """Verify no active cursor has a stale checkpoint relative to its runtime epoch."""
    conn = get_db()

    latest_window = conn.execute("SELECT MAX(created_at) as latest FROM replay_windows").fetchone()
    if not latest_window or not latest_window["latest"]:
        audit.record("checkpoint_monotonicity", True)
        conn.close()
        return

    runtime_epoch = parse_iso(latest_window["latest"])

    stale_cursors = conn.execute(
        "SELECT cursor_id, checkpoint_ts FROM replay_cursor WHERE state = 'active'"
    ).fetchall()
    conn.close()

    regressions = 0
    for s in stale_cursors:
        if parse_iso(s["checkpoint_ts"]) < runtime_epoch - timedelta(hours=24):
            regressions += 1

    audit.record(
        "checkpoint_monotonicity",
        regressions == 0,
        f"{regressions} checkpoint regressions detected" if regressions else "",
    )


def check_export_checksum_stability(audit):
    """Verify two consecutive pipeline+repair runs produce identical export checksums."""
    if not os.path.exists(INTEGRITY_PATH):
        audit.record("export_checksum_stability", False, "integrity file missing")
        return

    with open(INTEGRITY_PATH) as f:
        first_integrity = json.load(f)
    first_sha = first_integrity["sha256"]

    # execute full pipeline+repair again
    rc = run_pipeline_with_repair()
    if rc != 0:
        audit.record("export_checksum_stability", False, "second pipeline+repair run failed")
        return

    with open(INTEGRITY_PATH) as f:
        second_integrity = json.load(f)
    second_sha = second_integrity["sha256"]

    audit.record(
        "export_checksum_stability",
        first_sha == second_sha,
        f"checksum mismatch: run1={first_sha[:16]}... run2={second_sha[:16]}..." if first_sha != second_sha else "",
    )


def check_window_uniqueness(audit):
    """Verify no event_id is assigned to more than one replay window."""
    conn = get_db()
    windows = conn.execute("SELECT window_id, event_ids FROM replay_windows").fetchall()
    conn.close()

    all_refs = []
    for w in windows:
        eids = json.loads(w["event_ids"])
        for eid in eids:
            all_refs.append((eid, w["window_id"]))

    event_windows = {}
    for eid, wid in all_refs:
        event_windows.setdefault(eid, []).append(wid)

    multi_assigned = {k: v for k, v in event_windows.items() if len(v) > 1}
    audit.record(
        "window_uniqueness",
        len(multi_assigned) == 0,
        f"{len(multi_assigned)} events assigned to multiple windows" if multi_assigned else "",
    )


def check_referential_integrity(audit):
    """Verify every event_id referenced in replay_windows exists in raw_events."""
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

    audit.record(
        "referential_integrity",
        len(dangling) == 0,
        f"{len(dangling)} dangling event references in replay windows" if dangling else "",
    )


def check_export_integrity_metadata(audit):
    """Verify replay_integrity.json event_count matches actual timeline line count."""
    if not os.path.exists(INTEGRITY_PATH) or not os.path.exists(TIMELINE_PATH):
        audit.record("export_integrity_metadata", False, "export artifacts missing")
        return

    with open(INTEGRITY_PATH) as f:
        meta = json.load(f)

    line_count = 0
    hasher = hashlib.sha256()
    with open(TIMELINE_PATH) as f:
        for line in f:
            hasher.update(line.strip().encode("utf-8"))
            line_count += 1

    count_ok = meta["event_count"] == line_count
    hash_ok = meta["sha256"] == hasher.hexdigest()

    audit.record(
        "export_integrity_metadata",
        count_ok and hash_ok,
        f"count {'ok' if count_ok else 'MISMATCH'}, hash {'ok' if hash_ok else 'MISMATCH'}"
        if not (count_ok and hash_ok)
        else "",
    )


def main():
    audit = AuditResult()

    if not os.path.exists(DB_PATH):
        print("no replay state found, cannot audit")
        sys.exit(1)

    print("auditing replay state and exports...\n")

    check_monotonic_ordering(audit)
    check_no_duplicate_events(audit)
    check_utc_normalization(audit)
    check_cursor_consistency(audit)
    check_no_cursors_on_purged_windows(audit)
    check_deterministic_ordering(audit)
    check_checkpoint_monotonicity(audit)
    check_export_checksum_stability(audit)
    check_window_uniqueness(audit)
    check_referential_integrity(audit)
    check_export_integrity_metadata(audit)

    all_pass = audit.summary()
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
