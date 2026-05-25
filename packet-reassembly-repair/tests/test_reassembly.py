"""
Tests for packet-reassembly-repair task.
Validates the packet fragment reassembler output files.
"""

import json
import os


RUNTIME_DIR = "/app/runtime"
JSONL_PATH = os.path.join(RUNTIME_DIR, "sessions.jsonl")
STATS_PATH = os.path.join(RUNTIME_DIR, "reassembly_stats.json")


def load_sessions():
    """Load sessions.jsonl and return list of session records."""
    records = []
    with open(JSONL_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_stats():
    """Load reassembly_stats.json and return dict."""
    with open(STATS_PATH, "r") as f:
        return json.load(f)


# ============================================================
# TIER 1: Basic structure and format tests
# ============================================================

def test_output_files_exist():
    """Both output files must be created."""
    assert os.path.exists(JSONL_PATH), "sessions.jsonl not found"
    assert os.path.exists(STATS_PATH), "reassembly_stats.json not found"


def test_eight_sessions_in_output():
    """Output must contain exactly 8 session records."""
    records = load_sessions()
    assert len(records) == 8, f"Expected 8 sessions, got {len(records)}"
    session_ids = {r["session_id"] for r in records}
    expected = {f"sess-{i:03d}" for i in range(1, 9)}
    assert session_ids == expected


def test_sessions_sorted_by_id():
    """Sessions in JSONL must be sorted lexicographically by session_id."""
    records = load_sessions()
    ids = [r["session_id"] for r in records]
    assert ids == sorted(ids), "Sessions not sorted by session_id"


def test_retransmissions_detected():
    """Exactly 5 retransmissions must be detected."""
    stats = load_stats()
    assert stats["retransmissions_detected"] == 5, (
        f"Expected 5, got {stats['retransmissions_detected']}"
    )


def test_total_sessions_count():
    """Stats must report 8 total sessions."""
    stats = load_stats()
    assert stats["total_sessions"] == 8


def test_max_fragment_offset():
    """Highest byte offset seen must be 768 (sess-004's last DATA)."""
    stats = load_stats()
    assert stats["max_fragment_offset"] == 768, (
        f"Expected 768, got {stats['max_fragment_offset']}"
    )


# ============================================================
# TIER 2: Medium tests (require fixing Bugs 3, 4, 5)
# ============================================================

def test_total_bytes_reassembled():
    """Total bytes across all sessions must be 3888."""
    stats = load_stats()
    assert stats["total_bytes_reassembled"] == 3888, (
        f"Expected 3888, got {stats['total_bytes_reassembled']}"
    )


def test_per_session_payload_bytes():
    """Each session must have correct payload byte counts."""
    expected_bytes = {
        "sess-001": 576,
        "sess-002": 256,
        "sess-003": 640,
        "sess-004": 896,
        "sess-005": 384,
        "sess-006": 448,
        "sess-007": 288,
        "sess-008": 400,
    }
    records = load_sessions()
    for r in records:
        sid = r["session_id"]
        assert r["payload_bytes"] == expected_bytes[sid], (
            f"{sid} payload_bytes={r['payload_bytes']}, expected {expected_bytes[sid]}"
        )


def test_avg_rtt_positive():
    """Average RTT must be positive (approximately 752 ms)."""
    stats = load_stats()
    assert stats["estimated_avg_rtt_ms"] > 0, (
        f"RTT must be positive, got {stats['estimated_avg_rtt_ms']}"
    )
    assert 700 < stats["estimated_avg_rtt_ms"] < 800, (
        f"Expected RTT ~752ms, got {stats['estimated_avg_rtt_ms']}"
    )


def test_bloom_filter_fpr():
    """Bloom filter FPR must use correct formula: sessions/(sessions+fragments)."""
    stats = load_stats()
    # 8 sessions, 26 total fragments -> 8/34 = 0.235294
    expected = round(8 / (8 + 26), 6)
    assert abs(stats["bloom_filter_fpr"] - expected) < 0.0001, (
        f"Expected bloom_fpr={expected}, got {stats['bloom_filter_fpr']}"
    )


# ============================================================
# TIER 3: Hard tests (require fixing Bugs 1 + 2 together)
# ============================================================

def test_all_sessions_complete():
    """All 8 sessions must have is_complete=True (no gaps, FIN matches)."""
    records = load_sessions()
    for r in records:
        assert r["is_complete"] is True, (
            f"{r['session_id']} is_complete={r['is_complete']}, expected True"
        )


def test_complete_sessions_stat():
    """Stats must report 8 complete sessions."""
    stats = load_stats()
    assert stats["complete_sessions"] == 8, (
        f"Expected 8, got {stats['complete_sessions']}"
    )


def test_fragment_counts_per_session():
    """Each session must have correct unique fragment counts."""
    expected_frags = {
        "sess-001": 4,
        "sess-002": 3,
        "sess-003": 3,
        "sess-004": 3,
        "sess-005": 4,
        "sess-006": 3,
        "sess-007": 3,
        "sess-008": 3,
    }
    records = load_sessions()
    for r in records:
        sid = r["session_id"]
        assert r["total_fragments"] == expected_frags[sid], (
            f"{sid} total_fragments={r['total_fragments']}, expected {expected_frags[sid]}"
        )


# ============================================================
# TIER 4: Hardest test (requires ALL bugs fixed including hash sort)
# ============================================================

def test_reassembly_checksum():
    """The reassembly checksum must match the expected deterministic value."""
    stats = load_stats()
    assert stats["reassembly_checksum"] == "c5298ab47eccaec6", (
        f"Expected 'c5298ab47eccaec6', got '{stats['reassembly_checksum']}'"
    )
