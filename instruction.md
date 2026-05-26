# Spatial Index Repair — Debugging Task

## Overview

A geospatial event correlation engine ingests sensor readings from multiple monitoring zones, indexes them into a spatial grid, computes temporal correlation scores across time windows, and groups related events into clusters. The system currently produces incorrect results across several output dimensions.

## System Environment

- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source, config, data, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **Configuration**: `/app/runtime/config/cluster.ini`
- **Data**: `/app/runtime/data/` (four zone data files with sensor events)
- **Output**: `/app/runtime/output/` (spatial_index.json, correlation.json)

## Processing Stages

1. **Ingestion** — Loads sensor events from zone data files. Each zone contributes timestamped readings with spatial coordinates. Events are merged into a single ordered stream for processing.

2. **Zone Filtering** — Only events from configured active zones are processed. The system reads the active zone list from configuration.

3. **Grid Indexing** — Each event is assigned to a cell in the spatial grid based on its coordinates. The grid uses a configurable cell size and the cell coordinate for a point at position `p` relative to origin is `floor(p / cell_size)`.

4. **Temporal Correlation** — Events within the same spatial neighborhood are correlated across time windows. The scoring section of the configuration controls window duration. For each window, each cell's score reflects the most recent contributing event's reading value within that window period.

5. **Clustering** — Events in spatial and temporal proximity are grouped into clusters with correlation scores.

## Problem

The system runs without errors but produces incorrect output:
- Some zone data appears to be missing from results
- Spatial cell assignments are inconsistent for certain coordinate ranges
- Correlation window scores are inflated beyond expected values
- Event ordering is non-deterministic when multiple zones report simultaneously

## Expected Correct Output

When operating correctly:
- All four zones (north, south, east, west) contribute events, totaling 58 events
- The spatial grid contains 11 occupied cells
- 7 scored time windows are produced
- 13 event clusters are formed covering all 58 events
- Event ordering is deterministic using zone identity as a stable tiebreaker

## Output Schema

### `/app/runtime/output/spatial_index.json`

| Field | Type | Description |
|-------|------|-------------|
| `total_events` | integer | Count of all ingested events |
| `active_zones` | array | Sorted list of zone names that contributed events |
| `cell_count` | integer | Number of occupied grid cells |
| `cell_assignments` | object | Map of event key (zone_seq) to [cell_x, cell_y] pair |

### `/app/runtime/output/correlation.json`

| Field | Type | Description |
|-------|------|-------------|
| `window_scores` | object | Map of window index to correlation score |
| `clusters` | array | List of cluster objects |
| `clusters[].anchor_zone` | string | Zone of the cluster's anchor event |
| `clusters[].anchor_timestamp` | integer | Timestamp of the anchor event |
| `clusters[].cell` | array | Grid cell [x, y] of the anchor |
| `clusters[].event_count` | integer | Number of events in cluster |
| `clusters[].raw_score` | number | Sum of member event readings |
| `clusters[].adjusted_score` | number | Score after decay adjustment |
| `total_clusters` | integer | Number of clusters formed |
| `total_correlated_events` | integer | Total events assigned to clusters |

## Key Files

| File | Purpose |
|------|---------|
| `/app/runtime/run_correlator.py` | Main entry point orchestrating all stages |
| `/app/runtime/ingest.py` | Event loading and stream merging |
| `/app/runtime/grid.py` | Spatial grid indexing |
| `/app/runtime/correlator.py` | Temporal correlation and clustering |
| `/app/runtime/config/cluster.ini` | System configuration |
| `/app/runtime/data/zone_north.json` | North zone sensor events |
| `/app/runtime/data/zone_south.json` | South zone sensor events |
| `/app/runtime/data/zone_east.json` | East zone sensor events |
| `/app/runtime/data/zone_west.json` | West zone sensor events |

## Your Task

Identify and fix defects in the runtime source files so that the correlation engine produces correct output matching the expected values documented above.
