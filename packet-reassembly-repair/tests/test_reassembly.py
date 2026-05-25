"""
Tests for packet-reassembly-repair task.
Validates the packet fragment reassembler output files against known-correct values.

The capture contains 12 flows with specific fragment patterns:
  - flow-alpha: 5 DATA frags, 1472 bytes total
  - flow-beta: 3 DATA frags, 2560 bytes total
  - flow-gamma: 6 DATA frags, 1024 bytes total
  - flow-delta: 2 DATA frags, 3072 bytes total
  - flow-epsilon: 3 DATA frags, 384 bytes total
  - flow-zeta: 7 DATA frags, 448 bytes total
  - flow-eta: 3 DATA frags, 2048 bytes total
  - flow-theta: 5 DATA frags, 480 bytes total
  - flow-iota: 4 DATA frags, 800 bytes total
  - flow-kappa: 3 DATA frags, 1000 bytes total
  - flow-lambda: 5 DATA frags, 800 bytes total
  - flow-mu: 3 DATA frags, 1200 bytes total

Additionally: 7 explicit retransmissions (R-flagged) and 5 implicit duplicates
(out-of-order late arrivals that match already-seen offset+length pairs).
"""

import json
import os
import pytest


RUNTIME_DIR = "/app/runtime"
JSONL_PATH = os.path.join(RUNTIME_DIR, "sessions.jsonl")
STATS_PATH = os.path.join(RUNTIME_DIR, "reassembly_stats.json")


def load_sessions():
    """Load sessions.jsonl records."""
    records = []
    with open(JSONL_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_stats():
    """Load reassembly_stats.json."""
    with open(STATS_PATH, "r") as f:
        return json.load(f)


# ===========================================================================
# Structure and format tests (should pass even with bugs)
# ===========================================================================

class TestStructure:
    """Basic output structure validation."""

    def test_output_files_exist(self):
        assert os.path.exists(JSONL_PATH), "sessions.jsonl missing"
        assert os.path.exists(STATS_PATH), "reassembly_stats.json missing"

    def test_twelve_flows_in_output(self):
        records = load_sessions()
        assert len(records) == 12, f"Expected 12 flows, got {len(records)}"

    def test_flows_sorted_by_id(self):
        records = load_sessions()
        ids = [r["flow_id"] for r in records]
        assert ids == sorted(ids), "Flows not sorted by flow_id"

    def test_all_required_stats_fields(self):
        stats = load_stats()
        required = [
            "total_flows", "complete_flows", "total_payload_bytes",
            "total_retransmits", "avg_rtt_ms", "rtt_jitter_ms",
            "integrity_checksum", "avg_fragments_per_flow",
            "max_single_flow_bytes", "packet_loss_estimate",
        ]
        for field in required:
            assert field in stats, f"Missing stats field: {field}"


# ===========================================================================
# Retransmission detection tests (requires fixing Bug 1)
# ===========================================================================

class TestRetransmissions:
    """Validates retransmission detection and counting."""

    def test_total_retransmit_count(self):
        """Only 7 explicit R-flagged retransmissions exist in the capture."""
        stats = load_stats()
        assert stats["total_retransmits"] == 7, (
            f"Expected 7 retransmits (R-flagged only), got {stats['total_retransmits']}. "
            "Implicit duplicates (out-of-order arrivals) should NOT be counted."
        )

    def test_per_flow_retransmit_counts(self):
        """Each flow's retransmit_count must reflect only R-flagged packets."""
        records = load_sessions()
        expected = {
            "flow-alpha": 1, "flow-beta": 1, "flow-gamma": 1,
            "flow-delta": 1, "flow-eta": 1, "flow-iota": 1,
            "flow-mu": 1,
            # These flows have NO retransmits (only implicit dups or nothing):
            "flow-epsilon": 0, "flow-zeta": 0, "flow-kappa": 0,
            "flow-lambda": 0, "flow-theta": 0,
        }
        for r in records:
            fid = r["flow_id"]
            assert r["retransmit_count"] == expected[fid], (
                f"{fid}: retransmit_count={r['retransmit_count']}, "
                f"expected {expected[fid]}"
            )

    def test_avg_rtt_from_explicit_retransmits_only(self):
        """RTT should be computed from R-flagged retransmit pairs only."""
        stats = load_stats()
        # The 7 retransmits arrive ~1.3s after their originals on average
        # (originals at t=0.2-1.3, retransmits at t=1.5)
        # Expected avg RTT ≈ 857ms (computed from exact timestamps)
        assert 800 < stats["avg_rtt_ms"] < 920, (
            f"avg_rtt_ms={stats['avg_rtt_ms']} out of expected range [800, 920]. "
            "RTT should only use R-flagged retransmit pairs, not implicit duplicates."
        )


# ===========================================================================
# Byte counting tests (requires fixing Bug 3)
# ===========================================================================

class TestPayloadBytes:
    """Validates payload byte counting accuracy."""

    def test_total_payload_bytes(self):
        """Sum of all flow payload bytes must equal 15288."""
        stats = load_stats()
        assert stats["total_payload_bytes"] == 15288, (
            f"Expected 15288, got {stats['total_payload_bytes']}"
        )

    def test_per_flow_payload_bytes(self):
        """Each flow must have exact correct byte count."""
        records = load_sessions()
        expected = {
            "flow-alpha": 1472, "flow-beta": 2560, "flow-gamma": 1024,
            "flow-delta": 3072, "flow-epsilon": 384, "flow-zeta": 448,
            "flow-eta": 2048, "flow-theta": 480, "flow-iota": 800,
            "flow-kappa": 1000, "flow-lambda": 800, "flow-mu": 1200,
        }
        for r in records:
            fid = r["flow_id"]
            assert r["total_payload_bytes"] == expected[fid], (
                f"{fid}: total_payload_bytes={r['total_payload_bytes']}, "
                f"expected {expected[fid]}"
            )

    def test_max_single_flow_bytes(self):
        """Largest single flow is flow-delta at 3072 bytes."""
        stats = load_stats()
        assert stats["max_single_flow_bytes"] == 3072, (
            f"Expected 3072, got {stats['max_single_flow_bytes']}"
        )


# ===========================================================================
# Completeness tests (requires fixing Bugs 3+4 together)
# ===========================================================================

class TestCompleteness:
    """Validates flow completeness detection."""

    def test_all_flows_complete(self):
        """All 12 flows should be complete (no gaps, FIN matches end)."""
        records = load_sessions()
        for r in records:
            assert r["is_complete"] is True, (
                f"{r['flow_id']}: is_complete={r['is_complete']}, expected True"
            )

    def test_complete_flows_count(self):
        stats = load_stats()
        assert stats["complete_flows"] == 12

    def test_no_gaps_in_any_flow(self):
        """All flows should have gap_count=0."""
        records = load_sessions()
        for r in records:
            assert r["gap_count"] == 0, (
                f"{r['flow_id']}: gap_count={r['gap_count']}, expected 0"
            )


# ===========================================================================
# Network quality metrics (requires fixing Bug 5)
# ===========================================================================

class TestNetworkMetrics:
    """Validates network quality metric calculations."""

    def test_packet_loss_estimate(self):
        """Loss rate = retransmits / (unique_frags + retransmits) = 7/56 ≈ 0.125."""
        stats = load_stats()
        # 49 unique fragments + 7 retransmits = 56 total observed
        expected_loss = 7 / (49 + 7)  # = 0.125
        assert abs(stats["packet_loss_estimate"] - expected_loss) < 0.001, (
            f"Expected loss≈{expected_loss:.6f}, got {stats['packet_loss_estimate']}"
        )


# ===========================================================================
# Integrity checksum (requires ALL bugs fixed)
# ===========================================================================

class TestIntegrity:
    """Validates the deterministic integrity checksum."""

    def test_integrity_checksum(self):
        """
        The checksum must match the expected value computed from correct output.
        This test fails unless ALL other bugs are fixed, because the checksum
        depends on correct values for fragment_count, total_payload_bytes,
        is_complete, and gap_count — AND requires sorted iteration order.
        """
        stats = load_stats()
        assert stats["integrity_checksum"] == "6e66d7e4ef19a678", (
            f"Expected '6e66d7e4ef19a678', got '{stats['integrity_checksum']}'"
        )
