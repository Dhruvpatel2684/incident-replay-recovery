# Job Scheduler Repair — Debugging Task

## Overview

A priority-based job scheduling system loads job definitions from multiple worker pool feeds, processes them through a deadline-aware scheduler in batches, and dispatches them in deterministic priority order. The system handles jobs across compute, storage, network, and GPU worker pools with configurable retry budgets and wait time tracking.

## System Environment

- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source, config, data, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **Entry point**: `python3 -m runtime.run_scheduler`

## Processing Stages

1. **Pool Loading** — Reads active pool list from configuration, loads job definitions from matching feed files in `/app/runtime/data/`. Each feed file contains jobs for a single worker pool.

2. **Batch Scheduling** — Processes jobs in configurable batch sizes, assigning time slots and retry budgets. The deadline-specific retry limit is defined in the `[scheduling.deadlines]` section of the configuration. Statistics track the maximum wait time observed across all batch windows (the single highest wait_ms value).

3. **Dispatch Ordering** — Builds a dispatch queue sorted by `(priority_rank, submit_time, pool_id, job_id)` to ensure deterministic execution ordering across worker pool feeds. Priority ranks are: critical=0, high=1, normal=2, low=3.

4. **Output Generation** — Writes dispatch queue and scheduler summary to `/app/runtime/output/`.

## Problem

The system runs without errors but produces incorrect results. Symptoms include:

- Some worker pools appear to be missing from the dispatch queue despite having feed files present
- The scheduler summary reports an unexpectedly high max_wait_ms value
- The retry budget per job seems too generous for deadline-sensitive workloads
- Dispatch queue ordering is non-deterministic when jobs share the same priority and submit time

## Expected Correct Output

When operating correctly, the system should:

- Load 55 jobs from 4 active pools (compute: 18, storage: 18, gpu: 19)
- Use a max_retries value of 2 (from the deadline-aware configuration)
- Report max_wait_ms as the single highest wait time across all batches (not a sum)
- Dispatch jobs sorted by `(priority_rank, submit_time, pool_id, job_id)`
- Include jobs from all active pools in the dispatch queue

## Output Schema

### `/app/runtime/output/dispatch_queue.json`

A JSON array of dispatch entry objects:

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | string | Job identifier, unique within its pool feed |
| `pool_id` | string | Worker pool the job belongs to |
| `priority` | string | Priority level: critical, high, normal, or low |
| `priority_rank` | integer | Numeric rank: 0=critical, 1=high, 2=normal, 3=low |
| `submit_time` | string | ISO 8601 timestamp when job was submitted |
| `wait_ms` | integer | Estimated wait time in milliseconds |
| `retries_allowed` | integer | Maximum retry attempts for this job |
| `overdue` | boolean | Whether wait_ms exceeds the job deadline |
| `dispatch_position` | integer | Position in the final dispatch queue (0-indexed) |

### `/app/runtime/output/scheduler_summary.json`

| Field | Type | Description |
|-------|------|-------------|
| `scheduler_stats` | object | Statistics about the scheduling run |
| `dispatch_queue_length` | integer | Number of jobs in the dispatch queue |
| `total_jobs_loaded` | integer | Total jobs loaded from all pool feeds |

Fields within `scheduler_stats`:

| Field | Type | Description |
|-------|------|-------------|
| `total_scheduled` | integer | Number of jobs processed through scheduler |
| `batch_count` | integer | Number of batches processed |
| `max_wait_ms` | integer | Maximum wait time observed across all batches |
| `total_retries_allocated` | integer | Sum of retry budgets across all jobs |
| `overdue_count` | integer | Number of jobs exceeding their deadline |
| `max_retries` | integer | Configured maximum retries per job |
| `active_pools` | array | List of active pool identifiers |

## Key Files

| File | Purpose |
|------|---------|
| `/app/runtime/run_scheduler.py` | Main entry point orchestrating the full process |
| `/app/runtime/loader.py` | Loads job data from pool feeds based on config |
| `/app/runtime/scheduler.py` | Processes jobs in batches with deadline-aware retry logic |
| `/app/runtime/dispatcher.py` | Builds deterministic dispatch queue with priority ordering |
| `/app/runtime/config.ini` | Configuration for pools, scheduling, and priority |
| `/app/runtime/data/compute_pool.json` | Job data for compute pool (18 jobs) |
| `/app/runtime/data/storage_pool.json` | Job data for storage pool (18 jobs) |
| `/app/runtime/data/gpu_pool.json` | Job data for GPU pool (19 jobs) |
| `/app/runtime/output/dispatch_queue.json` | Generated dispatch queue |
| `/app/runtime/output/scheduler_summary.json` | Generated scheduler summary |

## Your Task

Identify and fix defects in the runtime source files so that the system produces correct output matching the expected behavior described above. The defects are in the processing logic, not in the data files.
