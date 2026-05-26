# Graph Reachability Repair — Debugging Task

## Overview

A graph reachability analysis engine processes directed network topologies from multiple sources, computes bounded hop-distance reachability between all node pairs, and produces weighted path quality scores per traversal level. The engine currently produces incorrect reachability counts, inflated scores, and non-deterministic output ordering.

## System Environment

- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source, config, data, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **Configuration**: `/app/runtime/config/topology.ini`
- **Data**: `/app/runtime/data/` (three network topology JSON files)
- **Output**: `/app/runtime/output/` (reachability.json, scores.json)

## Processing Stages

1. **Loading** — Reads directed edge definitions from network topology files. Each network contributes edges with typed links and weights.

2. **Filtering** — Only edges whose link type appears in the configured active set are included in analysis.

3. **Merging** — Edges from all networks are combined into a single deterministic stream. The merge ordering uses source node, then target node, then the originating network identifier, then sequence number.

4. **Traversal** — Bounded BFS from each node computes reachability. The hop limit comes from the operational constraints configuration section. Cycle detection prevents revisiting nodes.

5. **Scoring** — For each reachable node, a path quality score is computed based on edge weights. Level summaries aggregate scores per BFS depth. Each level's summary value represents only that level's own contribution.

## Problem

The engine runs without errors but produces incorrect output:
- Some edge types appear to be missing from processing
- Reachability distances are larger than expected for certain paths
- Level score summaries grow monotonically when they should vary independently
- Output ordering shows inconsistencies across runs

## Expected Correct Output

When operating correctly:
- All four link types (direct, relay, tunnel, mesh) contribute edges totaling 42
- 14 nodes are present with 122 total reachable pairs
- Node A reaches 13 others with maximum depth 3
- Level scores from A are: level 1 = 335.0, level 2 = 226.5, level 3 = 27.3

## Output Schema

### `/app/runtime/output/reachability.json`

| Field | Type | Description |
|-------|------|-------------|
| `total_nodes` | integer | Number of unique nodes in graph |
| `total_edges` | integer | Number of edges after filtering |
| `total_reachable_pairs` | integer | Sum of reachable nodes across all sources |
| `active_link_types` | array | Sorted list of active link type names |
| `reachability_map` | object | Per-node reachability data |
| `reachability_map.<node>.reachable_count` | integer | Nodes reachable from this source |
| `reachability_map.<node>.max_depth` | integer | Maximum hop distance reached |
| `reachability_map.<node>.nodes` | object | Map of reachable node to hop distance |

### `/app/runtime/output/scores.json`

| Field | Type | Description |
|-------|------|-------------|
| `node_scores` | object | Per-source map of target node to path score |
| `level_summaries` | object | Per-source map of depth level to score total |
| `total_scored_sources` | integer | Number of sources with score data |

## Key Files

| File | Purpose |
|------|---------|
| `/app/runtime/run_reachability.py` | Main entry point orchestrating all stages |
| `/app/runtime/loader.py` | Network loading and edge merging |
| `/app/runtime/traversal.py` | BFS reachability computation |
| `/app/runtime/scorer.py` | Path scoring and level summaries |
| `/app/runtime/config/topology.ini` | Link types, traversal limits, scoring params |
| `/app/runtime/data/network_core.json` | Core network topology |
| `/app/runtime/data/network_edge.json` | Edge network topology |
| `/app/runtime/data/network_backup.json` | Backup network topology |

## Your Task

Identify and fix defects in the runtime source files so that the reachability engine produces correct output. The issues span configuration parsing, parameter sourcing, score aggregation logic, and merge ordering.
