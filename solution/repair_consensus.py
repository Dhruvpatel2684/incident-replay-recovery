"""
Repair script for consensus-log-repair task.
Re-processes the raw cluster log with correct logic and overwrites
the broken output files with correct results.

Fixes applied:
1. log_parser.py Bug 1: VOTE_REQUEST term extraction uses parsed payload value
2. log_parser.py Bug 2: Full microsecond precision in timestamp parsing
3. state_machine.py Bug 3: Reset votes_received after election is won
4. state_machine.py Bug 4: Correct commit counting (one per COMMIT event, not per-node)
5. state_machine.py Bug 5: Use prev_log_idx+1 for follower log index
6. output_formatter.py Bug 6: Sort nodes in consistency hash computation
7. output_formatter.py Bug 7: Correct quorum calculation (n//2 + 1)
"""

import json
import hashlib
import os

RUNTIME_DIR = "/app/runtime"
LOG_FILE = os.path.join(RUNTIME_DIR, "cluster_logs.txt")
CLUSTER_NODES = ["node-1", "node-2", "node-3"]


# ============================================================
# FIXED Log Parser
# ============================================================

def parse_payload(payload_str):
    """Parse comma-separated key=value pairs into a dict."""
    result = {}
    for pair in payload_str.split(","):
        if "=" in pair:
            key, value = pair.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def parse_timestamp(ts_str):
    """
    FIX for Bug 2: Parse timestamp with FULL precision.
    No truncation - use the complete float value.
    """
    return float(ts_str)


def parse_log_line(line):
    """Parse a single log line into a structured event dict."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    parts = line.split("|")
    if len(parts) != 4:
        return None

    timestamp_str, source_node, event_type, payload_str = parts
    timestamp = parse_timestamp(timestamp_str)
    payload = parse_payload(payload_str)

    event = {
        "timestamp": timestamp,
        "source_node": source_node,
        "event_type": event_type,
        "payload": payload,
    }

    # FIX for Bug 1: Always use the parsed payload value for term.
    # No special-case position-based extraction for VOTE_REQUEST.
    if "term" in payload:
        event["term"] = int(payload["term"])
    else:
        event["term"] = 0

    return event


def load_events():
    """Load all events from the log file, sorted by timestamp."""
    events = []
    with open(LOG_FILE, "r") as f:
        for line in f:
            event = parse_log_line(line)
            if event is not None:
                events.append(event)

    # Sort by full-precision timestamp
    events.sort(key=lambda e: e["timestamp"])
    return events


# ============================================================
# FIXED State Machine
# ============================================================

class NodeState:
    def __init__(self, node_id):
        self.node_id = node_id
        self.term = 0
        self.role = "follower"
        self.voted_for = None
        self.log = []
        self.commit_index = 0
        self.votes_received = 0
        self.leader_id = None

    def to_dict(self):
        return {
            "node_id": self.node_id,
            "term": self.term,
            "role": self.role,
            "log_length": len(self.log),
            "commit_index": self.commit_index,
            "committed_entries": self.log[:self.commit_index + 1],
            "leader_id": self.leader_id,
        }


class ClusterStateMachine:
    def __init__(self, node_ids):
        self.nodes = {}
        for nid in node_ids:
            self.nodes[nid] = NodeState(nid)
        self.total_nodes = len(node_ids)
        self.election_history = []
        self.total_commits = 0

    def get_quorum(self):
        return (self.total_nodes // 2) + 1

    def process_event(self, event):
        event_type = event["event_type"]
        handler = getattr(self, f"_handle_{event_type.lower()}", None)
        if handler:
            handler(event)

    def _handle_election_timeout(self, event):
        node_id = event["source_node"]
        term = event["term"]
        node = self.nodes[node_id]
        node.term = term
        node.role = "candidate"
        node.voted_for = node_id
        node.votes_received = 1

    def _handle_vote_request(self, event):
        candidate = event["payload"].get("candidate", event["source_node"])
        term = event["term"]
        node = self.nodes.get(candidate)
        if node:
            node.term = term

    def _handle_vote_grant(self, event):
        candidate = event["payload"].get("candidate")
        voter = event["payload"].get("voter", event["source_node"])
        term = event["term"]

        if candidate and candidate in self.nodes:
            self.nodes[candidate].votes_received += 1

        if voter in self.nodes:
            self.nodes[voter].term = term
            self.nodes[voter].voted_for = candidate

    def _handle_vote_deny(self, event):
        voter = event["payload"].get("voter", event["source_node"])
        term = event["term"]
        if voter in self.nodes:
            self.nodes[voter].term = term

    def _handle_leader_elected(self, event):
        leader = event["payload"].get("leader", event["source_node"])
        term = event["term"]
        votes = int(event["payload"].get("votes", 0))

        self.election_history.append((term, leader, votes, "won"))

        # FIX for Bug 3: Reset votes_received after winning election
        if leader in self.nodes:
            node = self.nodes[leader]
            node.term = term
            node.role = "leader"
            node.leader_id = leader
            node.votes_received = 0  # FIX: reset votes after winning

        for nid, node in self.nodes.items():
            if nid != leader:
                node.term = term
                node.role = "follower"
                node.leader_id = leader
                node.votes_received = 0  # FIX: also reset others

    def _handle_election_failed(self, event):
        candidate = event["payload"].get("candidate", event["source_node"])
        term = event["term"]
        votes = int(event["payload"].get("votes", 0))

        self.election_history.append((term, candidate, votes, "failed"))

        if candidate in self.nodes:
            self.nodes[candidate].role = "follower"
            self.nodes[candidate].term = term

    def _handle_append_entry(self, event):
        leader = event["payload"].get("leader")
        target = event["payload"].get("target")
        entry = event["payload"].get("entry", "")
        term = event["term"]
        prev_log_idx = int(event["payload"].get("prev_log_idx", 0))

        if target not in self.nodes:
            return

        target_node = self.nodes[target]

        # FIX for Bug 5: Use prev_log_idx + 1 (receiver's perspective)
        new_idx = prev_log_idx + 1

        # Append entry to target's log
        while len(target_node.log) < new_idx:
            target_node.log.append(None)

        if new_idx == len(target_node.log):
            target_node.log.append((term, entry))
        elif new_idx < len(target_node.log):
            target_node.log[new_idx] = (term, entry)

        # Also append to leader's own log
        if leader in self.nodes:
            leader_node = self.nodes[leader]
            if prev_log_idx == len(leader_node.log) - 1 or len(leader_node.log) <= prev_log_idx:
                while len(leader_node.log) <= prev_log_idx:
                    leader_node.log.append(None)
                leader_node.log.append((term, entry))

    def _handle_append_ack(self, event):
        pass

    def _handle_commit(self, event):
        leader = event["payload"].get("leader")
        commit_idx = int(event["payload"].get("commit_idx", 0))

        # FIX for Bug 4: Count exactly ONE commit per COMMIT event
        # (a COMMIT event means one entry achieved quorum cluster-wide)
        self.total_commits += 1

        # Advance all nodes' commit index
        for nid, node in self.nodes.items():
            node.commit_index = commit_idx

    def get_cluster_state(self):
        return {nid: node.to_dict() for nid, node in self.nodes.items()}

    def get_election_history(self):
        return self.election_history


# ============================================================
# FIXED Output Formatter
# ============================================================

def compute_consistency_hash(cluster_state):
    """FIX for Bug 6: Sort nodes for deterministic hash."""
    hash_input = ""
    for node_id in sorted(cluster_state.keys()):  # FIX: sorted iteration
        state = cluster_state[node_id]
        hash_input += f"{node_id}:{state['term']}:{state['role']}:"
        hash_input += f"{state['log_length']}:{state['commit_index']}|"

    return hashlib.sha256(hash_input.encode()).hexdigest()[:16]


def count_split_votes(election_history, total_nodes):
    """FIX for Bug 7: Correct quorum = (n//2) + 1."""
    quorum = (total_nodes // 2) + 1  # FIX: correct quorum calculation
    split_count = 0

    for term, candidate, votes, result in election_history:
        if result == "failed" and votes < quorum:
            split_count += 1

    return split_count


def format_output(cluster_state, election_history, total_commits, total_nodes):
    """Write corrected output files."""
    output_dir = RUNTIME_DIR

    # Write cluster_state.jsonl
    jsonl_path = os.path.join(output_dir, "cluster_state.jsonl")
    with open(jsonl_path, "w") as f:
        for node_id in sorted(cluster_state.keys()):
            state = cluster_state[node_id]
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


# ============================================================
# Main execution
# ============================================================

def main():
    # Load events with fixed parser
    events = load_events()

    # Process with fixed state machine
    sm = ClusterStateMachine(CLUSTER_NODES)
    for event in events:
        sm.process_event(event)

    # Get results
    cluster_state = sm.get_cluster_state()
    election_history = sm.get_election_history()

    # Write output with fixed formatter
    format_output(
        cluster_state=cluster_state,
        election_history=election_history,
        total_commits=sm.total_commits,
        total_nodes=sm.total_nodes,
    )

    print(f"Repair complete. Processed {len(events)} events.")
    print(f"Total commits: {sm.total_commits}")
    print(f"Elections: {len(election_history)}")


if __name__ == "__main__":
    main()
