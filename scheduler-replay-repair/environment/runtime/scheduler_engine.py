"""
Scheduler replay engine - main orchestrator.

Replays an execution event log to reconstruct resource allocation state.
Processes events in order: SUBMIT, ALLOCATE, PREEMPT, RELEASE, COMPLETE.
Tracks allocation history, preemption chains, utilization, and integrity.

This module is correct and should not be modified. Bugs exist in
resource_allocator.py, priority_resolver.py, and utilization_tracker.py.
"""

import os
import sys

# Ensure runtime directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from event_parser import parse_execution_log
from resource_allocator import ResourceAllocator
from priority_resolver import PriorityResolver, PRIORITY_LEVELS
from utilization_tracker import UtilizationTracker
from output_writer import write_output


POOL_CAPACITIES = {"cpu": 32, "mem": 65536, "gpu": 4, "network": 10000}


def compute_usage(capacities, available):
    """Compute current usage for each resource pool."""
    usage = {}
    for resource in capacities:
        usage[resource] = capacities[resource] - available.get(resource, 0)
    return usage


def main():
    """Replay the execution log and produce output files."""
    # Parse events
    events = parse_execution_log()

    # Initialize components
    allocator = ResourceAllocator(POOL_CAPACITIES)
    resolver = PriorityResolver()
    tracker = UtilizationTracker()

    # State tracking
    allocation_history = {}
    active_tasks = {}  # task_id -> priority
    preemption_chain = []
    preemption_count = 0
    contention_count = 0

    for event in events:
        timestamp = event["timestamp"]
        event_type = event["event"]
        task_id = event["task_id"]
        priority = event["priority"]
        resources = event["resources"]
        details = event["details"]

        # Ensure task entry exists in history
        if task_id not in allocation_history:
            allocation_history[task_id] = {
                "priority": priority,
                "events": [],
                "final_state": "unknown",
                "total_allocated_time": 0,
            }

        if event_type == "SUBMIT":
            allocation_history[task_id]["events"].append({
                "timestamp": timestamp,
                "type": "SUBMIT",
                "resources_requested": resources,
                "details": details,
            })

        elif event_type == "ALLOCATE":
            # Perform allocation through the allocator
            granted = allocator.allocate_resources(task_id, resources)
            active_tasks[task_id] = priority

            # Check for partial allocation (contention)
            is_contention = any(
                granted.get(r, 0) < resources.get(r, 0)
                for r in resources
            )
            if is_contention:
                contention_count += 1

            allocation_history[task_id]["events"].append({
                "timestamp": timestamp,
                "type": "ALLOCATE",
                "resources_requested": resources,
                "resources_granted": granted,
                "contention": is_contention,
                "details": details,
            })
            allocation_history[task_id]["allocate_time"] = timestamp

            # Record utilization after allocation
            usage = compute_usage(POOL_CAPACITIES, allocator.get_available())
            for resource, amount in usage.items():
                tracker.record_usage(resource, timestamp, amount)

        elif event_type == "PREEMPT":
            # The preempted task loses its resources
            preempting_task = details.split("by ")[-1].split(" ")[0] if "by " in details else "unknown"

            # Extract preempting priority from details
            preempting_priority = "unknown"
            if "(" in details and ">" in details:
                prio_part = details.split("(")[1].split(")")[0]
                preempting_priority = prio_part.split(" > ")[0].strip()

            # Process resource return regardless of validation
            allocator.handle_preemption(task_id, resources)
            active_tasks.pop(task_id, None)

            # Validate preemption using priority resolver
            if resolver.can_preempt(preempting_priority, priority):
                preemption_count += 1
                preemption_chain.append({
                    "preempted_task": task_id,
                    "preempted_priority": priority,
                    "preempting_task": preempting_task,
                    "preempting_priority": preempting_priority,
                    "priority_delta": PRIORITY_LEVELS.get(preempting_priority, 0) - PRIORITY_LEVELS.get(priority, 0),
                    "resources_released": resources,
                    "timestamp": timestamp,
                })

            allocation_history[task_id]["events"].append({
                "timestamp": timestamp,
                "type": "PREEMPT",
                "resources_released": resources,
                "details": details,
            })
            allocation_history[task_id]["final_state"] = "preempted"

            # Record utilization after preemption
            usage = compute_usage(POOL_CAPACITIES, allocator.get_available())
            for resource, amount in usage.items():
                tracker.record_usage(resource, timestamp, amount)

        elif event_type == "RELEASE":
            allocator.release_resources(task_id)
            active_tasks.pop(task_id, None)

            allocation_history[task_id]["events"].append({
                "timestamp": timestamp,
                "type": "RELEASE",
                "resources_released": resources,
                "details": details,
            })

            # Compute allocated time
            if "allocate_time" in allocation_history[task_id]:
                alloc_time = timestamp - allocation_history[task_id]["allocate_time"]
                allocation_history[task_id]["total_allocated_time"] = alloc_time

            # Record utilization after release
            usage = compute_usage(POOL_CAPACITIES, allocator.get_available())
            for resource, amount in usage.items():
                tracker.record_usage(resource, timestamp, amount)

        elif event_type == "COMPLETE":
            allocation_history[task_id]["events"].append({
                "timestamp": timestamp,
                "type": "COMPLETE",
                "details": details,
            })
            if allocation_history[task_id]["final_state"] != "preempted":
                allocation_history[task_id]["final_state"] = "completed"

    # Compute utilization metrics
    utilization = {}
    for resource, capacity in POOL_CAPACITIES.items():
        utilization[resource] = tracker.compute_utilization(resource, capacity)

    # Build report
    report_data = {
        "total_tasks": len(allocation_history),
        "total_events": len(events),
        "preemptions": preemption_count,
        "resource_contentions": contention_count,
        "pool_capacities": POOL_CAPACITIES,
        "final_pool_available": allocator.get_available(),
        "utilization": utilization,
        "preemption_chain": preemption_chain,
    }

    # Write output
    write_output(allocation_history, report_data)


if __name__ == "__main__":
    main()
