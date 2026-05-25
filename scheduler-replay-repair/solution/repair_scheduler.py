"""
Oracle repair script for the task scheduler replay engine.

Re-processes the execution log from scratch with correct logic:
- Correct preemption resource return (+= not -=)
- Granted-amount tracking (records what was actually given, not requested)
- Strictly-greater priority comparison (new_weight > running_weight)
- Time-weighted average utilization (integral / (capacity * total_time))

Writes corrected allocation_history.json and scheduler_report.json to
/app/runtime/.
"""

import hashlib
import json
import os
import sys


RUNTIME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "environment", "runtime")
# When running inside container, use /app/runtime
if os.path.exists("/app/runtime/execution_log.txt"):
    RUNTIME_DIR = "/app/runtime"

POOL_CAPACITIES = {"cpu": 32, "mem": 65536, "gpu": 4, "network": 10000}
PRIORITY_LEVELS = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}


def parse_execution_log():
    """Parse the execution log file."""
    log_path = os.path.join(RUNTIME_DIR, "execution_log.txt")
    events = []
    with open(log_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            if len(parts) != 6:
                continue
            timestamp_str, event_type, task_id, priority, resource_str, details = parts
            resources = {}
            if resource_str.strip():
                for part in resource_str.strip().split(","):
                    key, value = part.split("=")
                    resources[key.strip()] = int(value.strip())
            events.append({
                "timestamp": int(timestamp_str.strip()),
                "event": event_type.strip(),
                "task_id": task_id.strip(),
                "priority": priority.strip(),
                "resources": resources,
                "details": details.strip(),
            })
    return events


def compute_allocation_integrity_hash(allocation_history, report_data):
    """Compute SHA-256 integrity hash over canonical allocation state."""
    hasher = hashlib.sha256()
    for task_id in sorted(allocation_history.keys()):
        events = allocation_history[task_id].get("events", [])
        events_str = json.dumps(events, sort_keys=True)
        line = f"{task_id}:{events_str}\n"
        hasher.update(line.encode("utf-8"))

    # Include preemption chain in hash
    chain = report_data.get("preemption_chain", [])
    chain_str = json.dumps(chain, sort_keys=True)
    hasher.update(f"preemption_chain:{chain_str}\n".encode("utf-8"))

    # Include utilization metrics in hash
    utilization = report_data.get("utilization", {})
    util_str = json.dumps(utilization, sort_keys=True)
    hasher.update(f"utilization:{util_str}\n".encode("utf-8"))

    return hasher.hexdigest()[:16]


def main():
    events = parse_execution_log()

    # Correct resource allocator state
    available = dict(POOL_CAPACITIES)
    active_allocations = {}  # task_id -> granted resources (FIX for Bug 2)

    # State tracking
    allocation_history = {}
    active_tasks = {}  # task_id -> priority
    preemption_chain = []
    preemption_count = 0
    contention_count = 0

    # Utilization tracking (for time-weighted average - FIX for Bug 4)
    usage_samples = {}  # resource -> [(timestamp, amount)]

    def record_usage(timestamp):
        """Record current usage for all resources."""
        for resource in POOL_CAPACITIES:
            usage = POOL_CAPACITIES[resource] - available.get(resource, 0)
            if resource not in usage_samples:
                usage_samples[resource] = []
            usage_samples[resource].append((timestamp, usage))

    for event in events:
        timestamp = event["timestamp"]
        event_type = event["event"]
        task_id = event["task_id"]
        priority = event["priority"]
        resources = event["resources"]
        details = event["details"]

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
            # Best-effort partial allocation
            granted = {}
            for resource, amount in resources.items():
                avail = available.get(resource, 0)
                grant = min(amount, max(0, avail))
                available[resource] -= grant
                granted[resource] = grant

            # FIX Bug 2: store GRANTED amounts, not requested
            active_allocations[task_id] = granted
            active_tasks[task_id] = priority

            # Check for contention
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

            record_usage(timestamp)

        elif event_type == "PREEMPT":
            # FIX Bug 1: preemption RETURNS resources to pool (+= not -=)
            # Use the actual granted amounts from active_allocations
            released = active_allocations.pop(task_id, resources)
            for resource, amount in released.items():
                available[resource] += amount

            active_tasks.pop(task_id, None)
            preemption_count += 1

            # Extract preempting info from details
            preempting_task = details.split("by ")[-1].split(" ")[0] if "by " in details else "unknown"
            preempting_priority = "unknown"
            if "(" in details and ">" in details:
                prio_part = details.split("(")[1].split(")")[0]
                preempting_priority = prio_part.split(" > ")[0].strip()

            preemption_chain.append({
                "preempted_task": task_id,
                "preempted_priority": priority,
                "preempting_task": preempting_task,
                "preempting_priority": preempting_priority,
                "priority_delta": PRIORITY_LEVELS.get(preempting_priority, 0) - PRIORITY_LEVELS.get(priority, 0),
                "resources_released": released,
                "timestamp": timestamp,
            })

            allocation_history[task_id]["events"].append({
                "timestamp": timestamp,
                "type": "PREEMPT",
                "resources_released": released,
                "details": details,
            })
            allocation_history[task_id]["final_state"] = "preempted"

            record_usage(timestamp)

        elif event_type == "RELEASE":
            # Release using the GRANTED amounts (FIX Bug 2 effect)
            if task_id in active_allocations:
                for resource, amount in active_allocations[task_id].items():
                    available[resource] += amount
                del active_allocations[task_id]

            active_tasks.pop(task_id, None)

            allocation_history[task_id]["events"].append({
                "timestamp": timestamp,
                "type": "RELEASE",
                "resources_released": resources,
                "details": details,
            })

            if "allocate_time" in allocation_history[task_id]:
                alloc_time = timestamp - allocation_history[task_id]["allocate_time"]
                allocation_history[task_id]["total_allocated_time"] = alloc_time

            record_usage(timestamp)

        elif event_type == "COMPLETE":
            allocation_history[task_id]["events"].append({
                "timestamp": timestamp,
                "type": "COMPLETE",
                "details": details,
            })
            if allocation_history[task_id]["final_state"] != "preempted":
                allocation_history[task_id]["final_state"] = "completed"

    # FIX Bug 4: compute time-weighted average utilization
    utilization = {}
    for resource, capacity in POOL_CAPACITIES.items():
        samples = usage_samples.get(resource, [])
        if not samples:
            utilization[resource] = 0.0
            continue

        # Sort samples by timestamp
        samples.sort(key=lambda x: x[0])

        # Compute time-weighted average: sum of (usage * duration) / (capacity * total_time)
        total_time = samples[-1][0] - samples[0][0]
        if total_time == 0:
            utilization[resource] = round(samples[0][1] / capacity, 4)
            continue

        weighted_sum = 0.0
        for i in range(len(samples) - 1):
            duration = samples[i + 1][0] - samples[i][0]
            weighted_sum += samples[i][1] * duration

        utilization[resource] = round(weighted_sum / (capacity * total_time), 4)

    # Build report
    report_data = {
        "total_tasks": len(allocation_history),
        "total_events": len(events),
        "preemptions": preemption_count,
        "resource_contentions": contention_count,
        "pool_capacities": POOL_CAPACITIES,
        "final_pool_available": available,
        "utilization": utilization,
        "preemption_chain": preemption_chain,
    }

    # Compute integrity hash
    integrity_hash = compute_allocation_integrity_hash(allocation_history, report_data)
    report_data["allocation_integrity_hash"] = integrity_hash

    # Write outputs
    history_path = os.path.join(RUNTIME_DIR, "allocation_history.json")
    with open(history_path, "w") as f:
        json.dump(allocation_history, f, indent=2, sort_keys=True)

    report_path = os.path.join(RUNTIME_DIR, "scheduler_report.json")
    with open(report_path, "w") as f:
        json.dump(report_data, f, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
