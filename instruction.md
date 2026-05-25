# Consensus Log Replay Recovery

## Background

A distributed systems team built a **consensus log replayer** that processes raw cluster communication logs from a 3-node Raft-like consensus protocol. The replayer reads event logs (elections, vote grants, log appends, commits) and produces two output files summarizing the final cluster state.

The tool was working in development but after a recent refactor, the output has become incorrect. The operations team reports multiple symptoms.

## System Architecture

The replayer consists of four Python modules in `/app/runtime/`:

- **`consensus_engine.py`** — Main entrypoint. Orchestrates the replay.
- **`log_parser.py`** — Parses raw log lines from `cluster_logs.txt` into structured event objects.
- **`state_machine.py`** — Applies parsed events to per-node state (elections, log replication, commits).
- **`output_formatter.py`** — Generates final output files from the computed cluster state.

Input data is in `/app/runtime/cluster_logs.txt`.

## Expected Output Files

The system must produce two files in `/app/runtime/`:

### `cluster_state.jsonl`

One JSON record per line (sorted by `node_id`), each containing:

```json
{
  "node_id": "<string>",
  "term": "<int>",
  "role": "<string: leader|follower>",
  "log_length": "<int>",
  "commit_index": "<int>",
  "committed_entries": ["<string>"],
  "leader_id": "<string or null>"
}
```

### `integrity.json`

```json
{
  "total_commits": "<int>",
  "leader_elections": "<int>",
  "split_votes": "<int>",
  "consistency_hash": "<string: 16-char hex>",
  "total_events_processed": "<int>",
  "final_term": "<int>"
}
```

## Observed Symptoms

1. **Commit count is wrong**: The `total_commits` value does not match the number of COMMIT events in the cluster log. It appears to be counting something per-node rather than per-event.

2. **Election analysis is incomplete**: A failed election in the log is not being detected as a split vote. The quorum calculation may be incorrect.

3. **Node state divergence**: Nodes that should have identical replicated logs show different lengths and content. Some nodes appear to be missing entries or have entries at wrong positions.

4. **Hash instability**: The consistency hash produces different values across runs, suggesting non-deterministic iteration. Additionally, the hash value doesn't match even when node states are manually verified to be correct, implying the hash formula may depend on fields that aren't being computed correctly.

5. **Commit propagation issue**: The committed entries reported by different nodes are inconsistent. Some nodes report no committed entries while others show a partial set. The commit advancement mechanism appears to only update a subset of nodes.

## Available Tooling

- Python 3 standard library is available system-wide (no external packages needed beyond pytest for testing)
- All source files are in `/app/runtime/`
- The input log file `cluster_logs.txt` is correct and should NOT be modified
- The `consensus_engine.py` entrypoint orchestration logic is correct

## Task

Debug and repair the consensus log replayer so that it produces correct output. The bugs are in the data processing modules. Pay careful attention to how the modules interact — fixing an issue in one module may require understanding how its output feeds into another.

Run the entrypoint to regenerate output:
```bash
python3 /app/runtime/consensus_engine.py
```
