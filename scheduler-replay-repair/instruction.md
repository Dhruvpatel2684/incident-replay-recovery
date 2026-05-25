# Task Scheduler Replay Engine -- Broken After "Capacity Planning Refactor"

## What's going on

We have a deterministic task scheduler that replays execution event logs to reconstruct resource allocation state. It processes a recorded log of scheduling decisions (submissions, allocations, preemptions, releases) and rebuilds the exact sequence of resource pool changes, preemption chains, and utilization metrics.

Last sprint someone refactored the resource accounting and priority comparison logic to "prepare for capacity planning integration." Now the replay produces completely wrong results and our cluster analytics dashboards are showing impossible numbers.

## Architecture

Six Python modules in `/app/runtime/`:

- `scheduler_engine.py` -- entry point, replays events in order (this one is fine, don't touch it)
- `event_parser.py` -- parses the execution log into structured events (correct)
- `resource_allocator.py` -- manages resource pool state (allocations, preemptions, releases)
- `priority_resolver.py` -- validates preemption eligibility based on task priority
- `utilization_tracker.py` -- computes resource utilization metrics over time
- `output_writer.py` -- writes `allocation_history.json` and `scheduler_report.json` (correct)

The execution log is in `execution_log.txt`. It contains 12 tasks across 4 priority levels (CRITICAL, HIGH, MEDIUM, LOW) with submission, allocation, preemption, release, and completion events. Pool capacities are: cpu=32, mem=65536, gpu=4, network=10000.

Don't modify the execution log, the engine, the parser, or the output writer.

## Symptoms

The replay engine runs without crashing but produces garbage:

1. **Resource pools exceed capacity** -- After all tasks complete, the final available resources are *higher* than the pool capacities. For example, cpu shows 36 available when the max is 32. Something is double-counting or returning resources that were never deducted.

2. **Preemptions not being validated** -- The execution log contains 3 clear preemption events where higher-priority tasks displace lower-priority ones. But the report shows 0 validated preemptions with an empty preemption chain. The priority resolver seems to reject every valid preemption.

3. **Massive resource contention count** -- The report shows 7 resource contentions when there should only be 2 tasks that got partial allocations. It seems like the pool goes to zero (or negative) early on, making every subsequent allocation look like contention.

4. **Utilization metrics above 100%** -- CPU utilization shows 1.375 (137.5%), which is physically impossible. The tracker is computing something wrong, or the underlying usage data is corrupted by the pool accounting bugs.

## What I think is happening

The "capacity planning refactor" touched the preemption resource return logic, the allocation tracking, the priority comparison semantics, and the utilization computation. Each area seems broken in a slightly different way. The resource accounting bugs cascade into the utilization metrics, making it hard to tell which numbers to trust.

## How to run

```bash
python3 /app/runtime/scheduler_engine.py
```

Produces `allocation_history.json` and `scheduler_report.json` in `/app/runtime/`.

## Output Schema

### allocation_history.json

A JSON object mapping task_id to its allocation record:

```json
{
  "task_001": {
    "priority": "MEDIUM",
    "events": [
      {"timestamp": 1000, "type": "SUBMIT", "resources_requested": {...}, "details": "..."},
      {"timestamp": 1001, "type": "ALLOCATE", "resources_requested": {...}, "resources_granted": {...}, "contention": false, "details": "..."},
      {"timestamp": 1140, "type": "RELEASE", "resources_released": {...}, "details": "..."},
      {"timestamp": 1141, "type": "COMPLETE", "details": "..."}
    ],
    "final_state": "completed",
    "total_allocated_time": 139
  }
}
```

Each task has a priority, event list, final state ("completed" or "preempted"), and total time resources were held.

### scheduler_report.json

```json
{
  "total_tasks": 12,
  "total_events": 45,
  "preemptions": 3,
  "resource_contentions": 2,
  "pool_capacities": {"cpu": 32, "mem": 65536, "gpu": 4, "network": 10000},
  "final_pool_available": {"cpu": 32, "mem": 65536, "gpu": 4, "network": 10000},
  "utilization": {"cpu": 0.69, "mem": 0.69, "gpu": 0.66, "network": 0.66},
  "preemption_chain": [
    {"preempted_task": "...", "preempted_priority": "...", "preempting_task": "...", "preempting_priority": "...", "priority_delta": 2, "resources_released": {...}, "timestamp": 1041}
  ],
  "allocation_integrity_hash": "<16-char hex string>"
}
```

- `total_tasks`: number of unique tasks in the log
- `total_events`: total event count
- `preemptions`: number of validated preemption events
- `resource_contentions`: tasks that got partial allocation (less than requested)
- `pool_capacities`: maximum resource capacity per pool
- `final_pool_available`: available resources after all events processed
- `utilization`: time-weighted average utilization per resource (fraction of capacity)
- `preemption_chain`: validated preemption events with priority deltas
- `allocation_integrity_hash`: SHA-256 (first 16 hex chars) over canonical allocation state, preemption chain, and utilization metrics

## What to fix

The problems are in `resource_allocator.py`, `priority_resolver.py`, and `utilization_tracker.py`. The scheduler engine, event parser, and output writer are all correct.

I'd estimate there are 4 bugs across those three files. The resource accounting bugs (in the allocator) affect downstream metrics, so fixing them first will make it easier to see what else is wrong. The priority resolver has a subtle comparison issue that the misleading comments make look correct. The utilization tracker computes the wrong aggregate.

Standard library only. No external packages.
