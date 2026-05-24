"""
Tests for consensus-log-repair task.
Validates that the consensus log replayer produces correct output files
with proper cluster state and integrity statistics.
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


def test_commit_count_matches_event_count():
    """
    The total_commits field must equal the number of COMMIT events in the log.
    There are exactly 7 COMMIT events in cluster_logs.txt (commits for indices
    1 through 7). Each COMMIT event represents one entry being committed
    cluster-wide, so total_commits must be 7.
    """
    integrity = load_integrity()
    assert integrity["total_commits"] == 7, (
        f"Expected total_commits=7 (one per COMMIT event), "
        f"got {integrity['total_commits']}"
    )


def test_split_vote_detection():
    """
    The split_votes field must count elections that failed because the
    candidate received fewer votes than quorum. With 3 nodes, quorum is 2.
    Term 3 has an election where node-3 received only 1 vote (self-vote)
    and failed, so split_votes must be 1.
    """
    integrity = load_integrity()
    assert integrity["split_votes"] == 1, (
        f"Expected split_votes=1 (term 3 election failed with 1 vote < quorum 2), "
        f"got {integrity['split_votes']}"
    )


def test_consistency_hash_deterministic():
    """
    The consistency_hash must be computed from nodes in sorted order
    (node-1, node-2, node-3) with correct state values. This ensures
    deterministic output regardless of internal dict ordering.
    Expected hash: 5b819d9c3b5e3642
    """
    integrity = load_integrity()
    assert integrity["consistency_hash"] == "5b819d9c3b5e3642", (
        f"Expected consistency_hash='5b819d9c3b5e3642', "
        f"got '{integrity['consistency_hash']}'"
    )


def test_uniform_log_length_across_nodes():
    """
    All three nodes must have identical log_length values. Since every
    APPEND_ENTRY in the log is successfully ACK'd by all followers,
    all nodes should converge to the same log length of 8 entries
    (1 null prefix + 7 committed entries).
    """
    records = load_cluster_state()
    log_lengths = {r["node_id"]: r["log_length"] for r in records}

    assert len(records) == 3, f"Expected 3 node records, got {len(records)}"

    for node_id, length in log_lengths.items():
        assert length == 8, (
            f"Expected log_length=8 for {node_id}, got {length}"
        )

    # All must be equal
    lengths = list(log_lengths.values())
    assert lengths[0] == lengths[1] == lengths[2], (
        f"Log lengths are not uniform: {log_lengths}"
    )


def test_committed_entries_complete():
    """
    Each node's committed_entries must contain the full sequence of
    7 committed operations. The entries should be:
    NULL, term1:SET:x=1, term1:SET:y=2, term1:SET:z=3,
    term2:SET:x=10, term2:SET:w=5, term4:SET:y=20
    (The NULL at index 0 is expected since log indexing starts at 1.)
    """
    expected_entries = [
        "NULL",
        "term1:SET:x=1",
        "term1:SET:y=2",
        "term1:SET:z=3",
        "term2:SET:x=10",
        "term2:SET:w=5",
        "term4:SET:y=20",
    ]

    records = load_cluster_state()
    for record in records:
        node_id = record["node_id"]
        entries = record["committed_entries"]
        assert entries == expected_entries, (
            f"Node {node_id} committed_entries mismatch.\n"
            f"Expected: {expected_entries}\n"
            f"Got:      {entries}"
        )


def test_total_events_and_final_term():
    """
    Validates derived integrity statistics:
    - total_events_processed must be 24 (sum of all log_length = 8*3)
    - final_term must be 4 (highest term reached in the cluster)
    - leader_elections must be 3 (terms 1, 2, and 4 had successful elections)
    """
    integrity = load_integrity()

    assert integrity["total_events_processed"] == 24, (
        f"Expected total_events_processed=24, "
        f"got {integrity['total_events_processed']}"
    )

    assert integrity["final_term"] == 4, (
        f"Expected final_term=4, got {integrity['final_term']}"
    )

    assert integrity["leader_elections"] == 3, (
        f"Expected leader_elections=3, got {integrity['leader_elections']}"
    )
