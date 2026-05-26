"""
Test suite for WAL compaction system.

Validates compaction correctness, snapshot integrity, and
checksum computation against expected behavioral invariants.
"""
import json
import os
import hashlib

OUTPUT_DIR = "/app/runtime/output"
COMPACTED_PATH = os.path.join(OUTPUT_DIR, "compacted_log.json")
SNAPSHOT_PATH = os.path.join(OUTPUT_DIR, "snapshot_state.json")
SUMMARY_PATH = os.path.join(OUTPUT_DIR, "compaction_summary.json")
DATA_DIR = "/app/runtime/data"


def load_compacted():
    """Load compacted log."""
    with open(COMPACTED_PATH, "r") as f:
        return json.load(f)


def load_snapshot():
    """Load snapshot state."""
    with open(SNAPSHOT_PATH, "r") as f:
        return json.load(f)


def load_summary():
    """Load compaction summary."""
    with open(SUMMARY_PATH, "r") as f:
        return json.load(f)


def reference_checksum(data_bytes, seed=0xDEADBEEF):
    """Compute reference XOR-fold checksum (correct implementation)."""
    accumulator = seed & 0xFFFFFFFFFFFFFFFF
    for i, b in enumerate(data_bytes):
        shift_amount = (i % 8) * 8
        accumulator ^= (b << shift_amount)
        accumulator &= 0xFFFFFFFFFFFFFFFF
    upper = (accumulator >> 32) & 0xFFFFFFFF
    lower = accumulator & 0xFFFFFFFF
    return upper ^ lower


# === BASIC TESTS ===


def test_output_files_exist():
    """Verify all output files are generated."""
    assert os.path.isfile(COMPACTED_PATH), f"Missing: {COMPACTED_PATH}"
    assert os.path.isfile(SNAPSHOT_PATH), f"Missing: {SNAPSHOT_PATH}"
    assert os.path.isfile(SUMMARY_PATH), f"Missing: {SUMMARY_PATH}"


def test_compacted_entry_schema():
    """Verify compacted entries have required fields."""
    compacted = load_compacted()
    assert len(compacted) > 0, "Compacted log must not be empty"
    for entry in compacted:
        assert "lsn" in entry
        assert "op" in entry
        assert "key" in entry
        assert "ts" in entry


def test_summary_schema():
    """Verify summary has required structure."""
    summary = load_summary()
    assert "compaction_stats" in summary
    assert "snapshot_size" in summary
    assert "namespace_stats" in summary
    assert "segment_checksums" in summary
    assert "output_checksum" in summary
    assert "compacted_entry_count" in summary


def test_compacted_entries_ordered_by_lsn():
    """Verify compacted log is ordered by LSN ascending."""
    compacted = load_compacted()
    for i in range(len(compacted) - 1):
        assert compacted[i]["lsn"] < compacted[i + 1]["lsn"], (
            f"Compacted entries not in LSN order at index {i}"
        )


# === MEDIUM TESTS ===


def test_all_segments_scanned():
    """Verify all 3 WAL segments are detected and scanned.

    The data directory contains segments 0, 1, and 2. Segment number
    extraction must correctly map LSNs to their segment.
    With segment_size=256: LSNs 0-255→seg 0, 256-511→seg 1, 512+→seg 2.
    """
    summary = load_summary()
    scanned = summary["compaction_stats"]["segments_scanned"]
    assert scanned == 3, (
        f"Expected 3 segments scanned, got {scanned}. "
        "Check LSN-to-segment mapping in the segment number extraction."
    )


def test_segment_checksums_correct():
    """Verify per-segment checksums match reference computation.

    Each segment's checksum must be computed with correct XOR-fold:
    fold 64-bit to 32-bit using full 32-bit lower mask (0xFFFFFFFF).
    """
    summary = load_summary()
    checksums = summary["segment_checksums"]

    # Verify we have 3 segments (keys "0", "1", "2")
    assert "0" in checksums, "Segment 0 checksum missing"
    assert "1" in checksums, "Segment 1 checksum missing"
    assert "2" in checksums, "Segment 2 checksum missing"

    # Verify segment 0 checksum matches reference
    with open(os.path.join(DATA_DIR, "wal_segment_0.json"), "r") as f:
        seg0_entries = json.load(f)
    seg0_data = json.dumps(seg0_entries, sort_keys=True, separators=(',', ':')).encode()
    expected_cs = reference_checksum(seg0_data)
    assert checksums["0"] == expected_cs, (
        f"Segment 0 checksum mismatch: got {checksums['0']}, "
        f"expected {expected_cs}. Check XOR-fold bit width."
    )


def test_tombstone_at_watermark_retained():
    """Verify tombstones at exactly the GC watermark are retained.

    GC watermark = max_lsn - gc_offset = 527 - 14 = 513.
    A tombstone at LSN 513 must NOT be garbage collected because
    the GC condition is strictly-less-than (not less-or-equal).
    """
    summary = load_summary()
    stats = summary["compaction_stats"]
    assert stats["tombstones_retained"] == 5, (
        f"Expected 5 tombstones retained, got {stats['tombstones_retained']}. "
        "Tombstones at exactly the GC watermark must be kept."
    )
    assert stats["live_entries"] == 33, (
        f"Expected 33 live entries, got {stats['live_entries']}"
    )


# === HARD TESTS ===


def test_snapshot_includes_all_epochs():
    """Verify snapshot includes entries up to the checkpoint boundary.

    The checkpoint boundary rounds UP to include the current epoch:
    boundary = ((max_lsn // interval) + 1) * interval
    With max_lsn=527, interval=64: boundary = 576.
    All compacted entries (max LSN 527) should be in the snapshot.
    """
    summary = load_summary()
    assert summary["snapshot_size"] == 28, (
        f"Expected snapshot with 28 live keys, got {summary['snapshot_size']}. "
        "Check checkpoint boundary calculation direction."
    )


def test_namespace_stats_complete():
    """Verify per-namespace stats reflect full snapshot state.

    With correct boundary (all entries included), the snapshot
    should contain keys from all three namespaces with proper
    put/del counts reflecting the complete compacted state.
    """
    summary = load_summary()
    ns = summary["namespace_stats"]

    assert "users" in ns, "users namespace missing from stats"
    assert "orders" in ns, "orders namespace missing from stats"
    assert "config" in ns, "config namespace missing from stats"

    # Users namespace should have substantial activity
    assert ns["users"]["live_keys"] >= 8, (
        f"Expected at least 8 live user keys, got {ns['users']['live_keys']}"
    )

    # Config namespace should show both puts and deletes
    assert ns["config"]["del_count"] >= 1, (
        f"Expected at least 1 config deletion in snapshot, "
        f"got {ns['config']['del_count']}"
    )


def test_output_checksum_verifiable():
    """Verify the output checksum over compacted data is correct.

    The output_checksum must match a reference XOR-fold computation
    over the JSON-serialized compacted log.
    """
    summary = load_summary()
    compacted = load_compacted()

    compacted_json = json.dumps(compacted, sort_keys=True, separators=(',', ':')).encode()
    expected_cs = reference_checksum(compacted_json)

    assert summary["output_checksum"] == expected_cs, (
        f"Output checksum mismatch: got {summary['output_checksum']}, "
        f"expected {expected_cs}. "
        "This indicates the XOR-fold algorithm has a bit-width error."
    )


def test_complete_system_integrity():
    """Verify end-to-end system produces correct compaction results.

    Checks multiple invariants simultaneously:
    - 3 segments scanned
    - Correct GC behavior (tombstone at watermark retained)
    - Full snapshot (28 keys)
    - Checksums match reference
    """
    summary = load_summary()
    compacted = load_compacted()
    snapshot = load_snapshot()

    stats = summary["compaction_stats"]
    assert stats["segments_scanned"] == 3
    assert stats["live_entries"] == 33
    assert stats["tombstones_retained"] == 5
    assert summary["snapshot_size"] == 28
    assert summary["compacted_entry_count"] == 33

    # Verify snapshot has expected key
    assert "users:1001" in snapshot, "users:1001 must be in snapshot"
    assert snapshot["users:1001"] == "alice_v5", (
        f"users:1001 should be alice_v5 (latest), got {snapshot.get('users:1001')}"
    )

    # Verify checksums
    assert len(summary["segment_checksums"]) == 3
