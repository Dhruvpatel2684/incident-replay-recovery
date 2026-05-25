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


def test_commit_count_matches_event_count():
    """Verify total_commits matches the actual COMMIT event count in the log."""
    integrity = load_integrity()
    assert integrity["total_commits"] == 6, (
        f"Expected total_commits=6, got {integrity['total_commits']}"
    )


def test_split_vote_detection():
    """Verify failed elections with insufficient votes are detected."""
    integrity = load_integrity()
    assert integrity["split_votes"] == 1, (
        f"Expected split_votes=1, got {integrity['split_votes']}"
    )


def test_consistency_hash_deterministic():
    """Verify the consistency hash is correct and deterministic."""
    integrity = load_integrity()
    assert integrity["consistency_hash"] == "c767f2c76fbddae8", (
        f"Expected consistency_hash='c767f2c76fbddae8', "
        f"got '{integrity['consistency_hash']}'"
    )


def test_uniform_log_length_across_nodes():
    """Verify all nodes converge to the same log state."""
    records = load_cluster_state()
    log_lengths = {r["node_id"]: r["log_length"] for r in records}

    assert len(records) == 3, f"Expected 3 node records, got {len(records)}"

    for node_id, length in log_lengths.items():
        assert length == 8, (
            f"Expected log_length=8 for {node_id}, got {length}"
        )

    lengths = list(log_lengths.values())
    assert lengths[0] == lengths[1] == lengths[2], (
        f"Log lengths are not uniform: {log_lengths}"
    )

    for record in records:
        assert record["commit_index"] == 6, (
            f"Expected commit_index=6 for {record['node_id']}, "
            f"got {record['commit_index']}"
        )


def test_committed_entries_complete():
    """Verify committed_entries contains exactly the committed log prefix."""
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
    """Verify derived integrity statistics are correct."""
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
