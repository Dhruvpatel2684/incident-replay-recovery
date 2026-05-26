# Cache Eviction Repair — Debugging Task

## Overview

A multi-tier cache eviction analysis system processes cache entries from tiered storage feeds, computes eviction priority scores using LRU-based algorithms, and produces a deterministic ranking of entries to evict. The system manages entries across hot, warm, cold, and archive tiers with configurable staleness thresholds and scoring parameters.

## System Environment

- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source, config, data, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **Entry point**: `python3 -m runtime.run_eviction`

## Processing Stages

1. **Tier Loading** — Reads active tier list from configuration. For each active tier, loads the corresponding data feed and attaches tier-specific configuration (TTL, capacity, priority floor). Tier configuration sections follow the pattern `[tier.<tier_id>]` in the config file.

2. **Eviction Scoring** — A separate scoring utility computes eviction priority for each entry. The LRU-specific algorithm parameters are defined in the `[eviction.lru]` section of the configuration file. Scores combine staleness relative to the threshold, inverse access frequency, and size penalty, modulated by weight decay.

3. **Window Processing** — The eviction engine processes entries in configurable window sizes. For each window, it identifies stale candidates (those exceeding the staleness threshold) and tracks the peak eviction score observed across all windows (the single highest score in any window).

4. **Candidate Ranking** — Eviction candidates are ranked by access_time ascending (oldest first). For entries with the same access_time, ordering uses tier_id alphabetically, then entry_id within the same tier, to ensure deterministic output across runs.

5. **Output Generation** — Writes ranked eviction list and summary statistics to `/app/runtime/output/`.

## Problem

The system runs without errors but produces incorrect results. Symptoms include:

- Fewer entries than expected are loaded for analysis
- The eviction candidate count is suspiciously low given the data
- Peak eviction score metrics appear inflated beyond reasonable single-entry bounds
- Ranking output exhibits non-deterministic ordering in certain positions

## Expected Correct Output

When operating correctly, the system should:

- Load 60 entries from 3 active tier feeds (hot: 20, warm: 22, archive: 18)
- Identify at least 30 eviction candidates using the LRU staleness threshold (3600 seconds)
- Report peak_eviction_score as the highest individual score from any single processing window
- Produce ranking ordered by `(access_time, tier_id, entry_id)` for stable cross-tier ordering

## Output Schema

### `/app/runtime/output/eviction_ranking.json`

A JSON array of ranked eviction candidate objects:

| Field | Type | Description |
|-------|------|-------------|
| `entry_id` | string | Entry identifier within its tier feed |
| `tier_id` | string | Cache tier the entry belongs to |
| `key` | string | Cache key for the entry |
| `access_time` | string | ISO 8601 timestamp of last access |
| `access_count` | integer | Total access count for this entry |
| `size_bytes` | integer | Size of the cached entry in bytes |
| `eviction_score` | float | Computed eviction priority score |
| `staleness_sec` | float | Seconds since last access relative to reference time |
| `eviction_rank` | integer | Position in the eviction ranking (0-indexed) |

### `/app/runtime/output/eviction_summary.json`

| Field | Type | Description |
|-------|------|-------------|
| `eviction_stats` | object | Statistics from the eviction analysis |
| `total_candidates` | integer | Number of entries marked for eviction |
| `total_entries_loaded` | integer | Total entries loaded from all tier feeds |

Fields within `eviction_stats`:

| Field | Type | Description |
|-------|------|-------------|
| `total_processed` | integer | Number of entries processed through windows |
| `windows_processed` | integer | Number of processing windows completed |
| `hit_count` | integer | Entries not exceeding staleness threshold |
| `miss_count` | integer | Entries exceeding staleness threshold (candidates) |
| `hit_rate` | float | Ratio of hits to total processed |
| `peak_eviction_score` | float | Highest eviction score in any single window |
| `eviction_params` | object | Active algorithm parameters |
| `active_tiers` | array | List of active tier identifiers |
| `tier_configs` | object | Per-tier configuration values |

Fields within `eviction_params`:

| Field | Type | Description |
|-------|------|-------------|
| `max_capacity` | integer | Maximum cache capacity |
| `staleness_threshold_sec` | integer | Seconds before entry considered stale |
| `weight_decay` | float | Decay factor for score computation |

## Key Files

| File | Purpose |
|------|---------|
| `/app/runtime/run_eviction.py` | Main entry point orchestrating the full process |
| `/app/runtime/loader.py` | Loads tier data and attaches tier configurations |
| `/app/runtime/scorer.py` | Utility module for eviction score computation |
| `/app/runtime/evictor.py` | Window-based eviction engine with statistics |
| `/app/runtime/ranker.py` | Deterministic candidate ranking with tiebreaking |
| `/app/runtime/config.ini` | Configuration for tiers, eviction, and scoring |
| `/app/runtime/data/hot_tier.json` | Cache entries for hot tier (20 entries) |
| `/app/runtime/data/warm_tier.json` | Cache entries for warm tier (22 entries) |
| `/app/runtime/data/archive_tier.json` | Cache entries for archive tier (18 entries) |
| `/app/runtime/output/eviction_ranking.json` | Generated eviction ranking |
| `/app/runtime/output/eviction_summary.json` | Generated eviction summary |

## Your Task

Identify and fix defects in the runtime source files so that the system produces correct output matching the expected behavior described above. The defects are in the processing logic across multiple modules, not in the data files or configuration structure.
