"""
Output Formatter Module
Generates cluster_state.jsonl and integrity.json from final cluster state.
"""

import json
import hashlib


def compute_consistency_hash(cluster_state):
    """
    Compute a deterministic hash of the cluster state.
    Used to verify log replay produces consistent results.
    """
    # BUG 6: Iterates over cluster_state dict in insertion order instead
    # of sorted node order. With Python 3.7+ dicts maintain insertion order,
    # but the insertion order depends on which nodes are processed first
    # during replay. Combined with Bug 3 (phantom votes affecting which
    # node becomes leader first), the iteration order may vary.
    hash_input = ""
    for node_id, state in cluster_state.items():  # BUG: should be sorted()
        hash_input += f"{node_id}:{state['term']}:{state['role']}:"
        hash_input += f"{state['log_length']}:{state['commit_index']}|"

    return hashlib.sha256(hash_input.encode()).hexdigest()[:16]


def count_split_votes(election_history, total_nodes):
    """
    Count elections where no candidate achieved quorum (split votes).
    A split vote occurs when the highest vote count is less than quorum.
    """
    # BUG 7: Calculates quorum as total_nodes/2 instead of (total_nodes/2)+1.
    # For 3 nodes: bug gives quorum=1 (3//2=1), correct is quorum=2 ((3//2)+1=2).
    # This means elections with 2 votes are incorrectly counted as successful
    # (not split), when with 3 nodes you actually need 2 votes for majority.
    # Wait - actually for 3 nodes, (3//2)+1 = 2 which IS correct quorum.
    # The bug here: uses total_nodes/2 = 1 as quorum threshold, meaning
    # it thinks ANY election with >= 1 vote succeeded, so nothing counts
    # as a split vote. The correct check should use (total_nodes // 2) + 1.
    quorum = total_nodes // 2  # BUG: should be (total_nodes // 2) + 1
    split_count = 0

    for term, candidate, votes, result in election_history:
        if result == "failed" and votes < quorum:
            split_count += 1

    return split_count


def format_output(cluster_state, election_history, total_commits, total_nodes, output_dir):
    """
    Write final output files:
    - cluster_state.jsonl: one JSON line per node (sorted by node_id)
    - integrity.json: summary statistics
    """
    import os

    # Write cluster_state.jsonl
    jsonl_path = os.path.join(output_dir, "cluster_state.jsonl")
    with open(jsonl_path, "w") as f:
        # Sort by node_id for deterministic output
        for node_id in sorted(cluster_state.keys()):
            state = cluster_state[node_id]
            # Serialize committed_entries as strings
            entries = []
            for entry in state.get("committed_entries", []):
                if entry is not None:
                    if isinstance(entry, tuple):
                        entries.append(f"term{entry[0]}:{entry[1]}")
                    else:
                        entries.append(str(entry))
                else:
                    entries.append("NULL")
            record = {
                "node_id": node_id,
                "term": state["term"],
                "role": state["role"],
                "log_length": state["log_length"],
                "commit_index": state["commit_index"],
                "committed_entries": entries,
                "leader_id": state.get("leader_id"),
            }
            f.write(json.dumps(record) + "\n")

    # Compute integrity stats
    leader_elections = sum(1 for _, _, _, r in election_history if r == "won")
    split_votes = count_split_votes(election_history, total_nodes)
    consistency_hash = compute_consistency_hash(cluster_state)

    integrity = {
        "total_commits": total_commits,
        "leader_elections": leader_elections,
        "split_votes": split_votes,
        "consistency_hash": consistency_hash,
        "total_events_processed": sum(
            state["log_length"] for state in cluster_state.values()
        ),
        "final_term": max(state["term"] for state in cluster_state.values()),
    }

    integrity_path = os.path.join(output_dir, "integrity.json")
    with open(integrity_path, "w") as f:
        json.dump(integrity, f, indent=2)

    return jsonl_path, integrity_path
