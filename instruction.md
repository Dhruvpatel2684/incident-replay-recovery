# Consensus Log Replay Recovery

## Background

A distributed systems team built a **consensus log replayer** that processes raw cluster communication logs from a 3-node Raft-like consensus protocol. The replayer reads event logs (elections, vote grants, log appends, commits) and produces two output files summarizing the final cluster state.

The tool was working in development but after a recent refactor to "optimize" event parsing and state tracking, the output has become incorrect. The operations team reports multiple symptoms across different aspects of the output.

## System Architecture

The replayer consists of four Python modules in `/app/runtime/`:

- **`consensus_engine.py`** — Main entrypoint. Orchestrates the replay pipeline.
- **`log_parser.py`** — Parses raw log lines from `cluster_logs.txt` into structured event objects.
- **`state_machine.py`** — Applies parsed events to per-node state (elections, log replication, commits).
- **`output_formatter.py`** — Generates final output files from the computed cluster state.

Input data is in `/app/runtime/cluster_logs.txt` (a 3-node cluster log with elections across 4 terms).

## Expected Output Files

The system must produce two files in `/app/runtime/`:

### `cluster_state.jsonl`

One JSON record per line (sorted by `node_id`), each containing:

```json
{
  "node_id": "<string: node-1|node-2|node-3>",
  "term": "<int: final term number for this node>",
  "role": "<string: leader|follower>",
  "log_length": "<int: total entries in this node's log including nulls>",
  "commit_index": "<int: highest committed log index>",
  "committed_entries": ["<string: termN:ENTRY or NULL for empty slots>"],
  "leader_id": "<string: node_id of current leader or null>"
}
```

### `integrity.json`

A single JSON object with summary statistics:

```json
{
  "total_commits": "<int: number of COMMIT events processed>",
  "leader_elections": "<int: number of successful elections>",
  "split_votes": "<int: elections that failed due to insufficient votes>",
  "consistency_hash": "<string: 16-char hex hash of cluster state>",
  "total_events_processed": "<int: sum of all nodes' log_length>",
  "final_term": "<int: highest term reached by any node>"
}
```

## Observed Symptoms

The operations team reports these issues when running the replayer:

1. **Inflated commit count**: The `total_commits` in `integrity.json` shows a value roughly 3× higher than the actual number of COMMIT events in the log. There are 6 COMMIT events in the input, but the output reports 18.

2. **Missing split vote detection**: The cluster log contains a failed election in term 3 where a candidate received only its own self-vote (1 vote) and failed to reach quorum. However, `split_votes` reports 0 instead of 1.

3. **Inconsistent node logs**: When the system is working correctly, all three nodes should end up with identical log contents and lengths (since all appends are acknowledged successfully). Instead, nodes show different `log_length` values and some have `NULL` entries where real data should be.

4. **Non-deterministic hash**: The `consistency_hash` changes between runs on different Python implementations, suggesting the computation depends on iteration order rather than a canonical ordering.

5. **Incorrect committed entries**: The `committed_entries` arrays should contain only entries that have been committed (i.e., entries for which a COMMIT event exists in the log). Some nodes show `NULL` gaps and wrong entries in their committed_entries arrays.

6. **Wrong total events**: The `total_events_processed` (sum of log lengths) is 22 when it should be 24 (8 entries × 3 nodes = 24 for a fully-replicated log).

## Correct Expected Values

When functioning correctly, the system should produce:

- `total_commits`: **6**
- `leader_elections`: **3**
- `split_votes`: **1**
- `consistency_hash`: **`066bdf57a78828c6`**
- `total_events_processed`: **24**
- `final_term`: **4**
- All three nodes should have `log_length`: **8** and `commit_index`: **6**
- All nodes' `committed_entries` should be identical (6 committed operations plus 1 NULL prefix = 7 entries; the uncommitted entry at index 7 must NOT be included)

## Available Tooling

- Python 3 standard library (no external packages needed beyond pytest for testing)
- All source files are in `/app/runtime/`
- The input log file `cluster_logs.txt` is correct and should NOT be modified
- The `consensus_engine.py` entrypoint orchestration logic is correct

## Task

Debug and repair the consensus log replayer so that it produces the correct output files matching the expected values above. The bugs are in the data processing modules — the input data and the main orchestration logic are sound.

Run the entrypoint to regenerate output:
```bash
python3 /app/runtime/consensus_engine.py
```
