"""
Test suite for Merkle-tree anti-entropy sync engine.

14 tests in 4 tiers:
- Tier 1 (6 tests): Structural checks - pass with buggy code
- Tier 2 (3 tests): Tree construction checks - need Bugs 1+2 fixed
- Tier 3 (3 tests): Diff precision and resolution checks - need Bugs 3+4 fixed
- Tier 4 (2 tests): Full integrity checks - need all 4 bugs fixed
"""

import json
import os

# Output file paths
RUNTIME_DIR = "/app/runtime"
RESULT_PATH = os.path.join(RUNTIME_DIR, "sync_result.json")
REPORT_PATH = os.path.join(RUNTIME_DIR, "sync_report.json")


def load_result():
    """Load sync_result.json."""
    with open(RESULT_PATH, "r") as f:
        return json.load(f)


def load_report():
    """Load sync_report.json."""
    with open(REPORT_PATH, "r") as f:
        return json.load(f)


# =============================================================================
# TIER 1: Structural tests (pass with buggy code)
# =============================================================================

class TestTier1Structural:
    """Basic structural checks that pass even with buggy sync logic."""

    def test_output_files_exist(self):
        """Both output files must exist after sync."""
        assert os.path.exists(RESULT_PATH), f"Missing: {RESULT_PATH}"
        assert os.path.exists(REPORT_PATH), f"Missing: {REPORT_PATH}"

    def test_sync_result_is_dict(self):
        """Sync result must be a valid JSON object (dict)."""
        result = load_result()
        assert isinstance(result, dict), "Sync result must be a JSON object"
        assert len(result) > 0, "Sync result must not be empty"

    def test_report_has_required_fields(self):
        """Report must contain all required fields."""
        report = load_report()
        required_fields = [
            "replicas_processed",
            "total_keys_seen",
            "divergent_keys_detected",
            "conflicts_resolved",
            "sync_operations",
            "integrity_hash"
        ]
        for field in required_fields:
            assert field in report, f"Missing required field: {field}"

    def test_total_replicas_count(self):
        """Report must show 3 replicas processed."""
        report = load_report()
        assert report["replicas_processed"] == 3, (
            f"Expected 3 replicas processed, got {report['replicas_processed']}"
        )

    def test_total_keys_across_replicas(self):
        """Total unique keys across all replicas must be 22."""
        report = load_report()
        assert report["total_keys_seen"] == 22, (
            f"Expected 22 total unique keys, got {report['total_keys_seen']}"
        )

    def test_report_has_sync_operations(self):
        """Sync operations field must exist and be a list."""
        report = load_report()
        assert isinstance(report["sync_operations"], list), (
            "sync_operations must be a list"
        )


# =============================================================================
# TIER 2: Tree construction tests (need Bugs 1+2 fixed)
# =============================================================================

class TestTier2TreeConstruction:
    """Tests that require correct Merkle tree hashing to pass.

    Bug 1 makes leaf hashes ignore entry content (only hashes key names),
    causing all trees to appear identical despite differing values.
    Bug 2 uses reversed concatenation order (right||left instead of left||right)
    for interior nodes, producing incorrect positional hashes.

    With these bugs, divergent_keys_detected = 0 because tree comparison
    sees no difference. Fixing them exposes the actual divergence.
    """

    def test_divergent_keys_detected(self):
        """At least 10 divergent keys must be detected.

        The replica data has exactly 10 keys that differ across replicas:
        6 with causal dominance, 2 tombstone-concurrent conflicts,
        and 2 that exist on only one replica (live vs tombstone).

        With Bug 1 (key-only hashing), trees look identical and
        divergent_keys_detected = 0. Fixing tree construction reveals
        the actual divergence.
        """
        report = load_report()
        assert report["divergent_keys_detected"] >= 10, (
            f"Expected at least 10 divergent keys detected, got "
            f"{report['divergent_keys_detected']}. If this is 0, the Merkle "
            f"tree leaf hashing is not incorporating entry content (value, "
            f"vclock, version) into the hash. Check _compute_leaf_hash."
        )

    def test_no_false_positives_in_identical(self):
        """Keys that exist only on one replica must be properly detected.

        data:1021 is live on replica B but tombstoned on A and C. The sync
        engine must detect this as divergent and resolve it (B's live version
        wins since its vclock dominates the tombstone vclock of {A:0,B:0,C:0}).

        With Bug 1, no divergence is detected, so data:1021 is treated as
        'identical' across replicas. The engine picks from replica A first,
        finds a tombstone, and the key is lost from sync_result entirely.
        """
        result = load_result()
        assert "data:1021" in result, (
            "data:1021 is missing from sync_result. This key is live on replica B "
            "(value: {queue: priority, max_size: 10000}) but tombstoned on A and C. "
            "If the Merkle tree hashing only uses key names (Bug 1), no divergence "
            "is detected, and the key is lost when the engine encounters A's "
            "tombstone first. Fix leaf hashing to include entry content."
        )

    def test_tree_depth_consistency(self):
        """Sync operations must reflect actual conflict resolution work.

        When the tree correctly identifies divergent keys, the conflict
        resolver processes them and generates sync operations. The report
        must show conflicts_resolved >= 6 (at minimum: 4 causal dominance +
        2 concurrent keys that need resolution).

        With Bug 1, divergent set is empty and conflicts_resolved = 0.
        """
        report = load_report()
        assert report["conflicts_resolved"] >= 6, (
            f"Expected at least 6 conflicts resolved, got "
            f"{report['conflicts_resolved']}. If this is 0, the tree "
            f"comparison found no divergence (all trees appear identical). "
            f"This indicates the leaf hash is not content-sensitive."
        )


# =============================================================================
# TIER 3: Diff precision and conflict resolution (need Bugs 3+4 fixed)
# =============================================================================

class TestTier3DiffAndResolution:
    """Tests that require correct diff traversal and causal resolution.

    Bug 3 terminates diff traversal early at divergent interior nodes,
    returning entire subtrees instead of recursing to leaf level.
    Bug 4 uses wall-clock timestamps instead of vector clock causality.

    These tests check that resolution produces causally correct winners
    and that the diff set has the right precision.
    """

    def test_conflict_resolution_causal(self):
        """Keys where replica B's vclock dominates must resolve to B's value.

        data:1012: B has vclock {A:5,B:3,C:3}, A has {A:4,B:3,C:2}.
        B strictly dominates A. Correct resolution: B's value.

        But A has last_modified='2024-01-15T11:45:00Z' while B has
        '2024-01-15T09:30:00Z'. Wall-clock (Bug 4) picks A incorrectly.

        data:1013: B has vclock {A:6,B:4,C:4}, A has {A:5,B:4,C:3}.
        B strictly dominates A. Correct resolution: B's value.
        Same wall-clock trap: A's timestamp is later.
        """
        result = load_result()

        assert "data:1012" in result, "data:1012 must exist in sync_result"
        assert result["data:1012"]["status"] == "active", (
            f"data:1012 status should be 'active' (from replica B, whose vclock "
            f"{{A:5,B:3,C:3}} dominates A's {{A:4,B:3,C:2}}), got "
            f"'{result['data:1012']['status']}'. If you got 'inactive', the "
            f"resolver is using wall-clock timestamps instead of vector clock "
            f"causality. Check _resolve_conflict."
        )

        assert "data:1013" in result, "data:1013 must exist in sync_result"
        assert result["data:1013"]["region"] == "us-east", (
            f"data:1013 region should be 'us-east' (from replica B, whose vclock "
            f"{{A:6,B:4,C:4}} dominates A's {{A:5,B:4,C:3}}), got "
            f"'{result['data:1013']['region']}'. Wall-clock resolution picks A "
            f"(later timestamp) instead of the causally correct B."
        )

    def test_additional_causal_resolution(self):
        """Additional keys where replica B's vclock dominates must resolve to B.

        data:1016: B has vclock {A:4,B:5,C:3}, A has {A:3,B:2,C:2}.
        B strictly dominates A. Correct resolution: B's value (mode='batch').

        But A has last_modified='2024-01-15T11:30:00Z' while B has
        '2024-01-15T09:15:00Z'. Wall-clock (Bug 4) picks A incorrectly.

        data:1017: B has vclock {A:4,B:5,C:2}, A has {A:3,B:2,C:1}.
        B strictly dominates A. Correct resolution: B's value (level='error').
        Same wall-clock trap: A's timestamp is later.
        """
        result = load_result()

        assert "data:1016" in result, "data:1016 must exist in sync_result"
        assert result["data:1016"]["mode"] == "batch", (
            f"data:1016 mode should be 'batch' (from replica B, whose vclock "
            f"{{A:4,B:5,C:3}} dominates A's {{A:3,B:2,C:2}}), got "
            f"'{result['data:1016']['mode']}'. If you got 'stream', the "
            f"resolver is using wall-clock timestamps instead of vector clock "
            f"causality."
        )

        assert "data:1017" in result, "data:1017 must exist in sync_result"
        assert result["data:1017"]["level"] == "error", (
            f"data:1017 level should be 'error' (from replica B, whose vclock "
            f"{{A:4,B:5,C:2}} dominates A's {{A:3,B:2,C:1}}), got "
            f"'{result['data:1017']['level']}'. Wall-clock resolution picks A "
            f"(later timestamp) instead of the causally correct B."
        )

    def test_diff_precision(self):
        """Diff detection must return exactly the divergent keys, not inflated.

        With correct tree construction and traversal, exactly 10 keys should
        be identified as divergent (data:1012 through data:1021). The 12
        identical keys (data:1000 through data:1011) must not be in the set.

        Bug 3 (early termination) returns entire subtrees at the first
        divergent interior node, inflating the count to 22 (all keys).
        """
        report = load_report()
        assert report["divergent_keys_detected"] == 10, (
            f"Expected exactly 10 divergent keys, got "
            f"{report['divergent_keys_detected']}. If this is 22 (all keys), "
            f"the diff traversal is terminating early at interior nodes and "
            f"returning entire subtrees instead of recursing to leaf level. "
            f"Check _find_divergent_keys - it should recurse into children "
            f"when hashes differ at non-leaf depth."
        )


# =============================================================================
# TIER 4: Full integrity tests (need ALL 4 bugs fixed)
# =============================================================================

class TestTier4FullIntegrity:
    """Tests that require all bugs to be fixed simultaneously.

    These tests verify the complete pipeline works end-to-end:
    correct tree construction, precise diff detection, causal
    conflict resolution, and tombstone dominance propagation.
    """

    def test_tombstone_propagation(self):
        """Tombstoned keys with dominating vclock must not appear in result.

        data:1018: B has tombstone with vclock {A:7,B:6,C:5} which dominates
        A's live {A:5,B:3,C:3} and C's live {A:3,B:3,C:3}. Causal deletion
        wins - key must not be in sync_result.

        data:1019: B has tombstone with vclock {A:5,B:6,C:4} which dominates
        A's live {A:4,B:3,C:3} and C's live {A:3,B:2,C:3}. Same logic.

        With Bug 4 (wall-clock), the resolver uses timestamps instead of
        vector clocks. But the tombstone check in _merge_entries is separate
        from conflict resolution - it correctly uses vclock_dominates. So this
        test passes once Bugs 1-3 are fixed (diff detection works) even if
        Bug 4 is not fixed, because tombstone dominance checking is independent.
        
        Actually this test requires ALL of Bugs 1+2+3 to be fixed first so that
        the diff detector correctly identifies data:1018 and data:1019 as divergent.
        """
        result = load_result()

        assert "data:1018" not in result, (
            "data:1018 should NOT be in sync_result. Replica B has a tombstone "
            "with vclock {A:7,B:6,C:5} that causally dominates all live copies "
            "(A: {A:5,B:3,C:3}, C: {A:3,B:3,C:3}). The tombstone represents a "
            "causal deletion that must propagate."
        )

        assert "data:1019" not in result, (
            "data:1019 should NOT be in sync_result. Replica B has a tombstone "
            "with vclock {A:5,B:6,C:4} that causally dominates all live copies "
            "(A: {A:4,B:3,C:3}, C: {A:3,B:2,C:3})."
        )

    def test_sync_integrity_hash(self):
        """The integrity hash must match the expected value.

        This is a SHA-256 hash (first 16 hex chars) computed over the sorted
        merged state. It depends on:
        - Correct tree construction (Bugs 1+2) - divergence detected
        - Correct diff traversal (Bug 3) - precise divergent set
        - Correct causal resolution (Bug 4) - right winners picked
        - Correct tombstone propagation - deleted keys excluded

        All four bugs must be fixed for the hash to match.
        """
        report = load_report()
        expected_hash = "2d9ee0d792bac20a"
        assert report["integrity_hash"] == expected_hash, (
            f"Integrity hash mismatch. Expected '{expected_hash}', got "
            f"'{report['integrity_hash']}'. This hash depends on the entire "
            f"merged state being correct: content-sensitive tree hashing, "
            f"recursive diff detection, vector clock causal resolution with "
            f"replica ID tiebreaking, and tombstone dominance propagation. "
            f"All four bugs in merkle_tree.py, diff_detector.py, and "
            f"conflict_resolver.py must be fixed simultaneously."
        )
