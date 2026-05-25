# Merkle Sync Engine -- Completely Broken After "Performance Optimization"

## What's going on

We have an anti-entropy sync engine that uses Merkle trees to detect and repair divergence between replicas of our distributed key-value store. Three replicas (A, B, C), each holding a subset of keys with vector clocks for causality tracking.

Last week someone rewrote chunks of the tree construction and conflict resolution code to "optimize for throughput." Now the whole thing is busted and I've been staring at it for two hours.

## Architecture

Six Python modules in `/app/runtime/`:

- `sync_engine.py` -- entry point, wires everything together (this one is fine, don't touch it)
- `replica_state.py` -- loads the three replica JSON files
- `merkle_tree.py` -- builds a depth-4 Merkle tree (16 leaf buckets) per replica
- `diff_detector.py` -- compares two trees, returns the set of divergent keys
- `conflict_resolver.py` -- takes divergent keys, resolves conflicts using vector clocks
- `output_writer.py` -- writes `sync_result.json` and `sync_report.json`

Replica data is in `replica_a.json`, `replica_b.json`, `replica_c.json`. Each key has a value, vector clock, version, tombstone flag, and last_modified timestamp. Don't modify the data files.

## Symptoms

The sync engine runs without crashing but produces garbage:

1. **Diff detection returns empty set** -- even though replicas clearly have different values for several keys, the Merkle tree comparison says everything is identical. The tree hashes shouldn't match when values diverge, but somehow they do.

2. **When I hack past the diff issue, wrong winners get picked** -- keys where replica B clearly has the newer vector clock are resolving to replica A's value instead. I checked the data three times. B dominates A's vclock on those keys. But the resolver picks A anyway. There's a `vclock_dominates` function right there in the file that looks correct, so I have no idea why resolution is wrong.

3. **Tombstoned keys aren't being removed** -- we have keys where one replica has a tombstone with a vector clock that strictly dominates all live entries. Those keys should be deleted from the merged output. But they're showing up anyway because (I think) the diff detector never identifies them as divergent in the first place, so the conflict resolver never gets a chance to apply tombstone logic.

4. **Inflated diff sets** -- on a test run where I manually forced tree divergence, the diff set included keys that are actually identical across replicas. It's returning entire subtrees instead of just the actually-divergent keys.

## What I think is happening

The "performance optimization" touched the tree hashing (something about "traversal order optimization"), the tree comparison (something about "batch processing"), and the conflict resolution (something about "reducing coordination overhead"). Each of those areas seems broken in a different way, and the bugs mask each other -- fixing the tree hash alone doesn't help because the diff traversal is also wrong.

## How to run

```bash
python3 /app/runtime/sync_engine.py
```

Produces `sync_result.json` and `sync_report.json` in `/app/runtime/`.

## Output Schema

### sync_result.json

A flat JSON object mapping data keys to their resolved values:

```json
{
  "data:1000": {"name": "item_0", "score": 10},
  "data:1012": {"priority": "high", "status": "active"},
  ...
}
```

Keys that are correctly tombstoned (deleted) should not appear. Keys that survive conflict resolution should have the winning replica's value as-is.

### sync_report.json

```json
{
  "replicas_processed": 3,
  "total_keys_seen": <int>,
  "divergent_keys_detected": <int>,
  "conflicts_resolved": <int>,
  "sync_operations": [
    {"key": "data:XXXX", "action": "resolve"|"delete", "source_replica": "<id>"}
  ],
  "integrity_hash": "<16-char hex string>"
}
```

- `replicas_processed`: always 3
- `total_keys_seen`: count of unique keys across all replicas
- `divergent_keys_detected`: how many keys the Merkle diff found as different
- `conflicts_resolved`: how many divergent keys got resolved to a live value
- `sync_operations`: one entry per divergent key describing what happened
- `integrity_hash`: SHA-256 (first 16 hex chars) of the merged state, computed by hashing `key=json.dumps(value, sort_keys=True)\n` for each key in sorted order

## What to fix

The problems are in `merkle_tree.py`, `diff_detector.py`, and `conflict_resolver.py`. The sync engine, replica loader, and output writer are all fine.

I'd guess there are around 4 distinct bugs across those three files. They interact, so fixing them one at a time won't necessarily show progress in the tests until you get the related ones too.

Standard library only. No external packages.
