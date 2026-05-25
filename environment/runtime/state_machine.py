"""
State Machine Module
Processes structured events and maintains per-node cluster state.
Implements simplified Raft: elections, log replication, commits.
"""


class NodeState:
    """Represents the state of a single node in the cluster."""

    def __init__(self, node_id):
        self.node_id = node_id
        self.term = 0
        self.role = "follower"  # follower, candidate, leader
        self.voted_for = None
        self.log = []  # list of (term, entry) tuples
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
    """Manages the state of all nodes in the cluster."""

    def __init__(self, node_ids):
        self.nodes = {}
        for nid in node_ids:
            self.nodes[nid] = NodeState(nid)
        self.total_nodes = len(node_ids)
        self.election_history = []  # list of (term, candidate, votes, result)
        self.total_commits = 0

    def get_quorum(self):
        """Calculate quorum size (majority)."""
        return (self.total_nodes // 2) + 1

    def process_event(self, event):
        """Route event to appropriate handler."""
        event_type = event["event_type"]
        handler = getattr(self, f"_handle_{event_type.lower()}", None)
        if handler:
            handler(event)

    def _handle_election_timeout(self, event):
        """Node starts an election."""
        node_id = event["source_node"]
        term = event["term"]
        node = self.nodes[node_id]
        node.term = term
        node.role = "candidate"
        node.voted_for = node_id
        node.votes_received = 1  # votes for self

    def _handle_vote_request(self, event):
        """Candidate requests votes from peers."""
        # Uses the term from the parsed event (BUG 1 interaction: this term
        # may be wrong for VOTE_REQUEST events due to parser bug)
        candidate = event["payload"].get("candidate", event["source_node"])
        term = event["term"]
        node = self.nodes.get(candidate)
        if node:
            node.term = term

    def _handle_vote_grant(self, event):
        """A node grants its vote to a candidate."""
        candidate = event["payload"].get("candidate")
        voter = event["payload"].get("voter", event["source_node"])
        term = event["term"]

        if candidate and candidate in self.nodes:
            self.nodes[candidate].votes_received += 1

        # Update voter state
        if voter in self.nodes:
            self.nodes[voter].term = term
            self.nodes[voter].voted_for = candidate

    def _handle_vote_deny(self, event):
        """A node denies its vote."""
        voter = event["payload"].get("voter", event["source_node"])
        term = event["term"]
        if voter in self.nodes:
            self.nodes[voter].term = term

    def _handle_leader_elected(self, event):
        """A candidate wins the election."""
        leader = event["payload"].get("leader", event["source_node"])
        term = event["term"]
        votes = int(event["payload"].get("votes", 0))

        # Record election
        self.election_history.append((term, leader, votes, "won"))

        # BUG 3: Updates leader state but does NOT reset votes_received for
        # the new term. The votes_received from THIS election persist and
        # carry over, affecting future vote counting if the node becomes
        # candidate again. Also does not reset other nodes' votes_received.
        if leader in self.nodes:
            node = self.nodes[leader]
            node.term = term
            node.role = "leader"
            node.leader_id = leader
            # Missing: node.votes_received = 0  (should reset after winning)

        # Update all other nodes to recognize new leader
        for nid, node in self.nodes.items():
            if nid != leader:
                node.term = term
                node.role = "follower"
                node.leader_id = leader

    def _handle_election_failed(self, event):
        """Election did not achieve quorum."""
        candidate = event["payload"].get("candidate", event["source_node"])
        term = event["term"]
        votes = int(event["payload"].get("votes", 0))

        self.election_history.append((term, candidate, votes, "failed"))

        if candidate in self.nodes:
            self.nodes[candidate].role = "follower"
            self.nodes[candidate].term = term

    def _handle_append_entry(self, event):
        """Leader replicates a log entry to a follower."""
        leader = event["payload"].get("leader")
        target = event["payload"].get("target")
        entry = event["payload"].get("entry", "")
        term = event["term"]
        prev_log_idx = int(event["payload"].get("prev_log_idx", 0))

        if target not in self.nodes:
            return

        target_node = self.nodes[target]

        # BUG 5: Computes new_idx using prev_log_idx without adding 1.
        # In Raft, prev_log_idx is the index of the PRECEDING entry, so the
        # new entry should go at prev_log_idx + 1. Using just prev_log_idx
        # causes entries to OVERWRITE the previous entry instead of being
        # appended after it. For the first entry (prev_log_idx=0), this puts
        # it at index 0 instead of index 1, eliminating the NULL prefix.
        new_idx = prev_log_idx  # BUG: should be prev_log_idx + 1

        # Append entry to target's log at the calculated position
        # If log is shorter than expected, pad with None entries
        while len(target_node.log) < new_idx:
            target_node.log.append(None)

        if new_idx == len(target_node.log):
            target_node.log.append((term, entry))
        elif new_idx < len(target_node.log):
            target_node.log[new_idx] = (term, entry)

        # Also append to leader's own log (leader tracks its own entries)
        # BUG 5b: The guard condition uses `prev_log_idx` to decide whether
        # to append to the leader's log, but it checks against the CURRENT
        # log length AFTER potentially modifying it from a previous
        # APPEND_ENTRY to the other follower in the same batch. This means
        # for the SECOND follower's append message (same entry, same
        # prev_log_idx), the guard may incorrectly trigger a duplicate
        # append because len(leader_node.log) has already grown.
        # The correct approach: only append if the entry at prev_log_idx+1
        # doesn't already exist in the leader's log.
        if leader in self.nodes:
            leader_node = self.nodes[leader]
            expected_new_idx = prev_log_idx + 1
            if len(leader_node.log) <= prev_log_idx:
                # Leader log is behind - pad and append
                while len(leader_node.log) <= prev_log_idx:
                    leader_node.log.append(None)
                leader_node.log.append((term, entry))
            elif len(leader_node.log) == expected_new_idx:
                # Leader log is exactly at the right spot - append
                leader_node.log.append((term, entry))
            # BUG 5b: Missing the case where len > expected_new_idx
            # (entry already exists). In this case we should do nothing,
            # but the elif above catches ONLY the == case. If another
            # code path sets the leader log to exactly expected_new_idx
            # between the two APPEND messages, this double-appends.

    def _handle_append_ack(self, event):
        """Follower acknowledges a log entry."""
        # ACKs are informational; commit is handled by COMMIT events
        pass

    def _handle_commit(self, event):
        """Leader commits an entry (quorum achieved)."""
        leader = event["payload"].get("leader")
        commit_idx = int(event["payload"].get("commit_idx", 0))
        term = event["term"]

        # BUG 4: Counts a commit for EACH node that needs to advance,
        # instead of counting just one commit per COMMIT event.
        # A single COMMIT event means one entry was committed cluster-wide,
        # but this code increments total_commits for every node whose
        # commit_index is behind, tripling the count (3 nodes).
        for nid, node in self.nodes.items():
            if node.commit_index < commit_idx:
                self.total_commits += 1  # BUG: should only count once per event
            node.commit_index = commit_idx

    def get_cluster_state(self):
        """Return final state of all nodes."""
        return {nid: node.to_dict() for nid, node in self.nodes.items()}

    def get_election_history(self):
        """Return election history."""
        return self.election_history
