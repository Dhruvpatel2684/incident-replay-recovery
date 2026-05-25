# Consensus Log Replay — Broken After Refactor

## What happened

We have a log replayer that reads raw Raft cluster communication logs (elections, appends, commits) and spits out a summary of the final cluster state. It was passing all our integration checks two weeks ago.

Then someone refactored the event processing "for performance" and now the output is garbage. Multiple fields are wrong and we can't figure out what's going on because the bugs seem to interact with each other.

## How it works

Four Python files in `/app/runtime/`:

- `consensus_engine.py` — entry point, just wires stuff together (this file is fine)
- `log_parser.py` — reads `cluster_logs.txt`, turns lines into event dicts
- `state_machine.py` — takes events and updates per-node state (elections, log replication, commits)
- `output_formatter.py` — takes final state, writes `cluster_state.jsonl` and `integrity.json`

The input log (`cluster_logs.txt`) has 3 nodes going through 4 election terms with appends and commits. The log itself is correct — don't modify it.

## What's broken (symptoms we're seeing)

Honestly there are a bunch of things wrong and they seem related:

- **Commit counting is off** — we get way more total_commits than there are COMMIT events in the log. Looks like it's counting something per-node instead of per-event.

- **Split vote detection broken** — there's clearly a failed election in the log (term 3, only got 1 vote) but split_votes shows 0. Something wrong with how quorum is calculated maybe?

- **Nodes have different log lengths** — they shouldn't. Every append in the log gets ACK'd by all nodes, so they should all converge to the same state. Instead we see different log_length values and NULL gaps where entries should be.

- **The hash is wrong** — consistency_hash gives different results between runs. The iteration over nodes isn't deterministic. Also even when we manually verify the node ordering, the hash still doesn't match what we expect, so something else feeding into it is wrong too.

- **committed_entries are inconsistent across nodes** — some nodes show no committed entries at all, others show a partial set. The commit state should propagate to everyone since all appends succeeded.

- **Leader has extra log entry** — total_events_processed (sum of all log lengths) is wrong. One node has more entries than it should.

## Output file format

The replayer produces two files in `/app/runtime/`:

**`cluster_state.jsonl`** — one JSON record per line (sorted by node_id), each with these fields:
- `node_id` (string): the node identifier
- `term` (int): final election term for this node
- `role` (string): "leader" or "follower"
- `log_length` (int): total entries in this node's replicated log
- `commit_index` (int): index of last committed entry
- `committed_entries` (array of strings): serialized log entries through commit_index, formatted as "termN:OPERATION" or "NULL" for empty sentinel slots
- `leader_id` (string): node_id of the current leader

**`integrity.json`** — summary statistics with these fields:
- `total_commits` (int): number of COMMIT events processed
- `leader_elections` (int): number of successful elections
- `split_votes` (int): elections that failed due to insufficient votes
- `consistency_hash` (string): 16-char hex SHA-256 prefix computed from per-node state
- `total_events_processed` (int): sum of all nodes' log_length values
- `final_term` (int): highest term reached by any node

## How to run

```bash
python3 /app/runtime/consensus_engine.py
```

This regenerates `cluster_state.jsonl` and `integrity.json` in `/app/runtime/`.

## What we need

Fix the bugs in the processing modules so the output is correct. The entry point (`consensus_engine.py`) is fine — the problems are in how events get parsed, how state gets tracked, and how the output gets formatted.

Fair warning: these bugs interact with each other. Fixing one thing might not show improvement until you also fix the related issue in another file. The hash in particular depends on multiple fields being correct simultaneously.

Python 3 standard library is available system-wide. No external packages needed.
