# Priority Scheduler Repair — Debugging Task

## Overview

A priority-based task scheduling engine reads job definitions from multiple queue sources, resolves priority conflicts, groups jobs into time windows, and produces a consolidated execution plan. The system is producing incorrect output: some job groups are being silently excluded, the time window granularity is wrong, window statistics are inflated, and job ordering within shared timestamps is non-deterministic.

## System Environment

- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (scheduler engine, configuration, job data)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **Dependencies**: Python standard library only (configparser, json, os, datetime)

## Processing Stages

1. **Configuration Loading** — Reads `/app/runtime/config.ini` for scheduler parameters including allowed groups, batch window size, and priority mappings
2. **Job Ingestion** — Loads job definitions from JSON files in `/app/runtime/data/` (one file per queue)
3. **Group Filtering** — Excludes jobs whose group is not in the allowed set
4. **Priority Sorting** — Orders jobs by scheduled time, then priority value (highest first), then deterministic tiebreakers for same-timestamp same-priority jobs from different queues
5. **Window Assignment** — Groups jobs into fixed-size time windows based on the batch window parameter from the execution configuration
6. **Statistics Computation** — Computes per-window load metrics where each job represents a point-in-time snapshot of that priority class's load (last value wins, not cumulative)
7. **Output Generation** — Writes `/app/runtime/output/execution_plan.json` and `/app/runtime/output/schedule_summary.json`

## Configuration

The config at `/app/runtime/config.ini` uses INI format with sections. The `[scheduler]` section has general defaults. The `[scheduler.execution]` section has precise execution parameters that override the general section for scheduling decisions. The `[scheduler.priorities]` section maps priority class names to numeric values.

The correct sort order for jobs at the same timestamp uses: scheduled_at (ascending), priority_value (descending), priority_class (alphabetical — provides deterministic ordering when numeric priority is equal), then seq (ascending).

## Problem

The scheduler runs without errors but produces incorrect results:
- Fewer jobs than expected appear in the output
- Time windows are too large (fewer windows than expected)
- Window load statistics appear inflated
- Job ordering at shared timestamps is inconsistent between runs

## Expected Correct Output

### `/app/runtime/output/execution_plan.json`

| Field | Type | Description |
|-------|------|-------------|
| `scheduler_name` | string | Name from config |
| `batch_window_minutes` | integer | Window size (should be 15) |
| `total_jobs_loaded` | integer | Total jobs read from all files |
| `total_jobs_scheduled` | integer | Jobs after filtering (should equal loaded) |
| `jobs_filtered_out` | integer | Jobs excluded (should be 0) |
| `time_windows` | object | Map of window_N to window data |
| `schedule` | array | Ordered list of scheduled job entries |

Each time window contains:

| Field | Type | Description |
|-------|------|-------------|
| `start_offset_minutes` | integer | Minutes from first job |
| `jobs` | array | Job IDs in this window |
| `total_duration` | integer | Sum of durations |
| `job_count` | integer | Number of jobs |
| `load_by_priority` | object | Per-class load (last-value snapshot) |

### `/app/runtime/output/schedule_summary.json`

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | "completed" |
| `total_scheduled` | integer | Total jobs scheduled |
| `window_count` | integer | Number of time windows |
| `groups_processed` | array | Sorted list of processed groups |
| `priority_distribution` | object | Count per priority class |

## Key Files

| File | Purpose |
|------|---------|
| `/app/runtime/scheduler.py` | Core scheduling engine with all logic |
| `/app/runtime/run_scheduler.py` | Entry point that invokes the scheduler |
| `/app/runtime/config.ini` | Scheduler configuration (INI format) |
| `/app/runtime/data/batch_jobs.json` | Batch queue job definitions (10 jobs) |
| `/app/runtime/data/realtime_jobs.json` | Realtime queue job definitions (10 jobs) |
| `/app/runtime/data/analytics_jobs.json` | Analytics queue job definitions (10 jobs) |

## Your Task

Identify and fix the defects in `/app/runtime/scheduler.py` that cause incorrect filtering, wrong window sizes, inflated statistics, and non-deterministic ordering. The configuration file and job data files are correct — the bugs are in the scheduler logic.
