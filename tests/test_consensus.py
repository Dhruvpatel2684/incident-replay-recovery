"""
Tests for consensus-log-repair task.
Validates the consensus log replayer output files.
"""

import json
import os


RUNTIME_DIR = "/app/runtime"
JSONL_PATH = os.path.join(RUNTIME_DIR, "cluster_state.jsonl")
INTEGRITY_PATH = os.path.join(RUNTIME_DIR, "integrity.json")


def load_cluster_state():
    """Load cluster_state.jsonl and return list of node records."""
    records = []
    with open(JSONL_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_integrity():
    """Load integrity.json and return dict."""
    with open(INTEGRITY_PATH, "r") as f:
        return json.load(f)


# ============================================================
# TIER 1: Basic structure tests (pass even with buggy code)
# These verify the output format is correct
# ============================================================

def test_output_files_exist():
    """Both output files must be created."""
    assert os.path.exists(JSONL_PATH), "cluster_state.jsonl not found"
    assert os.path.exists(INTEGRITY_PATH), "integrity.json not found"


def test_three_nodes_in_output():
    """Output must contain exactly 3 node records."""
    records = load_cluster_state()
    assert len(records) == 3, f"Expected 3 nodes, got {len(records)}"
    node_ids = {r["node_id"] for r in records}
    assert node_ids == {"node-1", "node-2", "node-3"}


def test_node_roles_correct():
    """node-3 must be leader, others followers (term 4 election)."""
    records = load_cluster_state()
    roles = {r["node_id"]: r["role"] for r in records}
    assert roles["node-3"] == "leader"
    assert roles["node-1"] == "follower"
    assert roles["node-2"] == "follower"


def test_final_term_is_four():
    """All nodes should be at term 4."""
    integrity = load_integrity()
    assert integrity["final_term"] == 4
    records = load_cluster_state()
    for r in records:
        assert r["term"] == 4, f"{r['node_id']} term={r['term']}, expected 4"


def test_leader_elections_count():
    """Three successful elections occurred (terms 1, 2, 4)."""
    integrity = load_integrity()
    assert integrity["leader_elections"] == 3


def test_all_nodes_have_leader_id():
    """All nodes must recognize node-3 as current leader."""
    records = load_cluster_state()
    for r in records:
        assert r["leader_id"] == "node-3", (
            f"{r['node_id']} has leader_id={r['leader_id']}"
        )


# ============================================================
# TIER 2: Medium tests (require fixing Bug 4 and/or Bug 7)
# ============================================================

def test_commit_count_matches_event_count():
    """total_commits must equal 6 (one per COMMIT event in the log)."""
    integrity = load_integrity()
    assert integrity["total_commits"] == 6, (
        f"Expected total_commits=6, got {integrity['total_commits']}"
    )


def test_split_vote_detection():
    """Failed election in term 3 (1 vote < quorum 2) must be detected."""
    integrity = load_integrity()
    assert integrity["split_votes"] == 1, (
        f"Expected split_votes=1, got {integrity['split_votes']}"
    )


def test_total_events_processed():
    """Sum of all log_length values must be 24 (8 entries x 3 nodes)."""
    integrity = load_integrity()
    assert integrity["total_events_processed"] == 24, (
        f"Expected 24, got {integrity['total_events_processed']}"
    )


def test_uniform_log_length():
    """All nodes must have log_length=8."""
    records = load_cluster_state()
    for r in records:
        assert r["log_length"] == 8, (
            f"{r['node_id']} log_length={r['log_length']}, expected 8"
        )


# ============================================================
# TIER 3: Hard tests (require fixing Trap 2 - commit propagation)
# ============================================================

def test_uniform_commit_index():
    """All nodes must have commit_index=6 (commits propagate to all)."""
    records = load_cluster_state()
    for r in records:
        assert r["commit_index"] == 6, (
            f"{r['node_id']} commit_index={r['commit_index']}, expected 6"
        )


def test_committed_entries_identical_across_nodes():
    """All nodes must have the same committed_entries array."""
    records = load_cluster_state()
    entries_sets = [tuple(r["committed_entries"]) for r in records]
    assert entries_sets[0] == entries_sets[1] == entries_sets[2], (
        f"Committed entries differ across nodes"
    )


def test_committed_entries_content():
    """committed_entries must contain the correct 7-entry sequence."""
    expected = [
        "NULL",
        "term1:SET:x=1",
        "term1:SET:y=2",
        "term1:SET:z=3",
        "term2:SET:x=10",
        "term2:SET:w=5",
        "term4:SET:y=20",
    ]
    records = load_cluster_state()
    for r in records:
        assert r["committed_entries"] == expected, (
            f"{r['node_id']} committed_entries mismatch.\n"
            f"Expected: {expected}\n"
            f"Got:      {r['committed_entries']}"
        )


# ============================================================
# TIER 4: Hardest test (requires ALL bugs fixed including hash sort)
# ============================================================

def test_consistency_hash():
    """The consistency hash must match the expected deterministic value."""
    integrity = load_integrity()
    assert integrity["consistency_hash"] == "c767f2c76fbddae8", (
        f"Expected 'c767f2c76fbddae8', got '{integrity['consistency_hash']}'"
    )
