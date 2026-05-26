"""
Test suite for WAL compaction tool.

14 tests in 4 tiers:
- Tier 1 (6 tests): Structural checks - pass with buggy code
- Tier 2 (3 tests): Visibility/abort checks - need Bug 1 fixed
- Tier 3 (3 tests): Ordering/tombstone checks - need Bugs 2+3 fixed
- Tier 4 (2 tests): Full consistency checks - need all bugs fixed
"""

import json
import os
import hashlib

# Output file paths
RUNTIME_DIR = "/app/runtime"
STATE_PATH = os.path.join(RUNTIME_DIR, "compacted_state.json")
REPORT_PATH = os.path.join(RUNTIME_DIR, "compaction_report.json")


def load_state():
    """Load compacted_state.json."""
    with open(STATE_PATH, "r") as f:
        return json.load(f)


def load_report():
    """Load compaction_report.json."""
    with open(REPORT_PATH, "r") as f:
        return json.load(f)


# =============================================================================
# TIER 1: Structural tests (pass with buggy code)
# =============================================================================

class TestTier1Structural:
    """Basic structural checks that pass even with buggy compaction logic."""

    def test_output_files_exist(self):
        """Both output files must exist after compaction."""
        assert os.path.exists(STATE_PATH), f"Missing: {STATE_PATH}"
        assert os.path.exists(REPORT_PATH), f"Missing: {REPORT_PATH}"

    def test_compacted_state_is_dict(self):
        """Compacted state must be a valid JSON object (dict)."""
        state = load_state()
        assert isinstance(state, dict), "Compacted state must be a JSON object"
        assert len(state) > 0, "Compacted state must not be empty"

    def test_report_has_required_fields(self):
        """Report must contain all required fields."""
        report = load_report()
        required_top = ["compaction_summary", "state_summary", "compaction_fingerprint"]
        for field in required_top:
            assert field in report, f"Missing top-level field: {field}"

        summary_fields = ["total_transactions", "committed_transactions",
                         "aborted_transactions", "total_data_operations"]
        for field in summary_fields:
            assert field in report["compaction_summary"], f"Missing summary field: {field}"

        state_fields = ["live_key_count", "deleted_key_count", "keys"]
        for field in state_fields:
            assert field in report["state_summary"], f"Missing state field: {field}"

    def test_total_transactions_count(self):
        """Total transaction count must be 10."""
        report = load_report()
        assert report["compaction_summary"]["total_transactions"] == 10, (
            f"Expected 10 transactions, got {report['compaction_summary']['total_transactions']}"
        )

    def test_committed_count(self):
        """Committed transaction count must be 8."""
        report = load_report()
        assert report["compaction_summary"]["committed_transactions"] == 8, (
            f"Expected 8 committed, got {report['compaction_summary']['committed_transactions']}"
        )

    def test_aborted_count(self):
        """Aborted transaction count must be 2."""
        report = load_report()
        assert report["compaction_summary"]["aborted_transactions"] == 2, (
            f"Expected 2 aborted, got {report['compaction_summary']['aborted_transactions']}"
        )


# =============================================================================
# TIER 2: Visibility/abort checks (need Bug 1 fixed)
# =============================================================================

class TestTier2Visibility:
    """Tests that verify aborted transaction changes are not visible in output."""

    def test_aborted_keys_not_in_state(self):
        """Keys written ONLY by aborted transactions must not exist in state.

        txn_003 (ABORTED) inserted cache:7001, cache:7002.
        txn_007 (ABORTED) inserted session:3003, event:4001.
        No committed transaction ever wrote these keys, so they must not exist.
        """
        state = load_state()

        # These keys were ONLY written by aborted transactions
        phantom_keys = ["cache:7002", "session:3003", "event:4001"]
        for key in phantom_keys:
            assert key not in state, (
                f"Key '{key}' exists in compacted state but was only written by an "
                f"aborted transaction. Aborted changes must not be visible — the "
                f"visibility predicate should only include committed transactions."
            )

    def test_aborted_values_not_in_report(self):
        """The reported key list must not include keys only from aborted txns.

        The compaction report's state_summary.keys field lists all live keys.
        Keys that were only written by aborted transactions (cache:7002,
        session:3003, event:4001) must not appear in this list.
        """
        report = load_report()
        reported_keys = set(report["state_summary"]["keys"])

        phantom_keys = ["cache:7002", "session:3003", "event:4001"]
        found_phantoms = [k for k in phantom_keys if k in reported_keys]
        assert len(found_phantoms) == 0, (
            f"Report's key list contains phantom keys from aborted transactions: "
            f"{found_phantoms}. These keys were never written by a committed "
            f"transaction and should not appear in the compacted output."
        )

    def test_live_key_count(self):
        """Exactly 12 keys should be live in the compacted state.

        Committed transactions write to these unique keys:
          user:1001, user:1002, order:5001, order:5002, session:3001,
          session:3002, metric:9001, metric:9002, audit:2001, config:1001,
          order:5003, notification:6001, invoice:8001, deploy:1101
        That's 14 unique keys from committed transactions.

        Of those, 2 are deleted by committed transactions:
          - order:5002 (DELETEd by txn_005)
          - session:3002 (DELETEd by txn_009)

        Final live count: 14 - 2 = 12
        """
        report = load_report()
        assert report["state_summary"]["live_key_count"] == 12, (
            f"Expected 12 live keys, got {report['state_summary']['live_key_count']}. "
            f"Common errors: 14 means phantom keys from aborted txns are included. "
            f"13 means a committed key was incorrectly tombstoned by an aborted DELETE."
        )


# =============================================================================
# TIER 3: Ordering and tombstone tests (need Bugs 2+3 fixed)
# =============================================================================

class TestTier3OrderingAndTombstones:
    """Tests that verify LSN-based ordering and correct tombstone handling."""

    def test_last_writer_wins_by_lsn(self):
        """When multiple committed txns write the same key, highest LSN wins.

        user:1001 is written by:
        - txn_001 at LSN=2  (INSERT, role="admin")
        - txn_002 at LSN=10 (UPDATE, role="admin" + last_login)
        - txn_005 at LSN=24 (UPDATE, role="superadmin")
        - txn_006 at LSN=29 (UPDATE, role="owner")

        Correct: highest LSN (29) wins -> txn_006 -> role="owner"

        The conflict resolution must sort writes by LSN ascending and take
        the last element, OR sort descending and take the first element.
        Getting the wrong element from the sorted list gives a stale value.
        """
        state = load_state()
        assert "user:1001" in state, "user:1001 must exist in compacted state"

        user = state["user:1001"]
        assert user["role"] == "owner", (
            f"user:1001 role should be 'owner' (from txn_006, highest LSN=29), "
            f"got '{user['role']}'. The last-writer-wins rule requires selecting "
            f"the write with the highest LSN as the winner. Check that the sort "
            f"direction and element selection are consistent (e.g., ascending sort "
            f"with [-1], or descending sort with [0])."
        )

    def test_committed_tombstone_removes_key(self):
        """DELETE operations from committed txns must remove keys from state.

        txn_005 (committed) DELETEs order:5002 at LSN=26.
        txn_009 (committed) DELETEs session:3002 at LSN=46.
        These keys must NOT appear in the final compacted state.
        """
        state = load_state()

        assert "order:5002" not in state, (
            "order:5002 was DELETEd by committed txn_005 but still exists in state. "
            "Committed DELETEs must remove keys from the compacted output."
        )
        assert "session:3002" not in state, (
            "session:3002 was DELETEd by committed txn_009 but still exists in state. "
            "Committed DELETEs must remove keys from the compacted output."
        )

    def test_aborted_tombstone_does_not_remove_key(self):
        """DELETE operations from aborted txns must NOT remove committed keys.

        txn_003 (ABORTED) DELETEs session:3001 at LSN=16. But session:3001
        was INSERTed by txn_002 (committed) at LSN=8. Since txn_003 was
        aborted, its DELETE should have no effect — session:3001 must remain.

        This tests that tombstones are only effective for committed transactions.
        Recording tombstones from aborted transactions incorrectly removes
        keys that should remain in the compacted state.
        """
        state = load_state()

        assert "session:3001" in state, (
            "session:3001 was INSERTed by committed txn_002 but is missing from "
            "the compacted state. txn_003 DELETEd it but txn_003 was ABORTED. "
            "Tombstones from aborted transactions must not affect the compacted "
            "output — only committed DELETEs should remove keys."
        )


# =============================================================================
# TIER 4: Full consistency tests (need ALL bugs fixed)
# =============================================================================

class TestTier4FullConsistency:
    """Tests that require all bugs to be fixed simultaneously."""

    def test_compaction_fingerprint(self):
        """The compaction fingerprint must match the expected value.

        This is a SHA-256 hash of sorted key=value pairs. It depends on:
        - Correct visibility (Bug 1) — only committed txn changes included
        - Correct LSN ordering (Bug 2) — correct winning values for conflicts
        - Correct tombstone handling (Bug 3) — only committed DELETEs count
        - Correct sorted iteration (Bug 4) — deterministic hash computation

        All four bugs must be fixed for this to match.
        """
        report = load_report()
        expected_fingerprint = "ea8386e7e4f8b5d2"
        assert report["compaction_fingerprint"] == expected_fingerprint, (
            f"Compaction fingerprint mismatch. Expected '{expected_fingerprint}', "
            f"got '{report['compaction_fingerprint']}'. This hash depends on the "
            f"entire compacted state being correct (visibility filtering, LSN-based "
            f"conflict resolution, tombstone handling, and sorted key iteration)."
        )

    def test_full_state_consistency(self):
        """Cross-validate the complete compacted state for internal consistency.

        Verifies:
        - Exact key set matches expected (12 specific keys)
        - Key values are correct for conflict-resolved keys
        - Counts in report match actual state
        - No phantom keys from aborted transactions
        - No incorrectly tombstoned keys
        """
        state = load_state()
        report = load_report()

        # Exact expected key set
        expected_keys = sorted([
            "audit:2001", "config:1001", "deploy:1101", "invoice:8001",
            "metric:9001", "metric:9002", "notification:6001", "order:5001",
            "order:5003", "session:3001", "user:1001", "user:1002"
        ])
        actual_keys = sorted(state.keys())
        assert actual_keys == expected_keys, (
            f"Key set mismatch.\n"
            f"Expected: {expected_keys}\n"
            f"Got: {actual_keys}\n"
            f"Extra: {sorted(set(actual_keys) - set(expected_keys))}\n"
            f"Missing: {sorted(set(expected_keys) - set(actual_keys))}"
        )

        # Verify conflict-resolved values (highest LSN wins)
        assert state["user:1001"]["role"] == "owner", (
            f"user:1001 role should be 'owner' (txn_006, LSN=29), got '{state['user:1001']['role']}'"
        )
        assert state["user:1002"]["role"] == "admin", (
            f"user:1002 role should be 'admin' (txn_008, LSN=42), got '{state['user:1002']['role']}'"
        )
        assert state["metric:9001"]["value"] == 55.0, (
            f"metric:9001 value should be 55.0 (txn_006, LSN=31), got {state['metric:9001']['value']}"
        )
        assert state["order:5001"]["status"] == "pending", (
            f"order:5001 status should be 'pending' (txn_001, LSN=4 — only committed writer), "
            f"got '{state['order:5001']['status']}'"
        )
        assert state["config:1001"]["feature_flags"]["beta"] == True, (
            f"config:1001 beta flag should be True (txn_010, LSN=51), "
            f"got {state['config:1001']['feature_flags']['beta']}"
        )
        assert state["order:5003"]["status"] == "confirmed", (
            f"order:5003 status should be 'confirmed' (txn_009, LSN=47), "
            f"got '{state['order:5003']['status']}'"
        )

        # Report counts must match state
        assert report["state_summary"]["live_key_count"] == len(state), (
            f"Report says {report['state_summary']['live_key_count']} live keys "
            f"but state has {len(state)} keys"
        )
        assert report["state_summary"]["live_key_count"] == 12
        assert report["state_summary"]["deleted_key_count"] == 2
        assert report["compaction_summary"]["total_transactions"] == 10
        assert report["compaction_summary"]["committed_transactions"] == 8
        assert report["compaction_summary"]["aborted_transactions"] == 2
