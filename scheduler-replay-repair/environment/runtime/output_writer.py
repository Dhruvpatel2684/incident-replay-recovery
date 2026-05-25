"""
Output writer for the task scheduler replay engine.

Writes allocation_history.json and scheduler_report.json to the runtime
directory after the replay engine has processed all events.
"""

import hashlib
import json
import os


RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))


def compute_allocation_integrity_hash(allocation_history, report_data):
    """Compute SHA-256 integrity hash over canonical allocation state.

    Combines allocation events, preemption chain, and utilization metrics
    into a single hash. For each task_id in sorted order, hashes:
        "task_id:json.dumps(events, sort_keys=True)\n"
    Then appends preemption chain and utilization data.

    Returns first 16 hex characters of the SHA-256 digest.
    """
    hasher = hashlib.sha256()
    for task_id in sorted(allocation_history.keys()):
        events = allocation_history[task_id].get("events", [])
        events_str = json.dumps(events, sort_keys=True)
        line = f"{task_id}:{events_str}\n"
        hasher.update(line.encode("utf-8"))

    # Include preemption chain in hash (affected by Bug 3)
    chain = report_data.get("preemption_chain", [])
    chain_str = json.dumps(chain, sort_keys=True)
    hasher.update(f"preemption_chain:{chain_str}\n".encode("utf-8"))

    # Include utilization metrics in hash (affected by Bug 4)
    utilization = report_data.get("utilization", {})
    util_str = json.dumps(utilization, sort_keys=True)
    hasher.update(f"utilization:{util_str}\n".encode("utf-8"))

    return hasher.hexdigest()[:16]


def write_output(allocation_history, report_data):
    """Write allocation_history.json and scheduler_report.json.

    Args:
        allocation_history: dict mapping task_id to task record
            {priority, events list, final_state, total_allocated_time}
        report_data: dict with summary fields
            {total_tasks, total_events, preemptions, resource_contentions,
             pool_capacities, final_pool_available, utilization,
             preemption_chain}
    """
    # Compute integrity hash (includes allocation events, preemption chain, utilization)
    integrity_hash = compute_allocation_integrity_hash(allocation_history, report_data)
    report_data["allocation_integrity_hash"] = integrity_hash

    # Write allocation history
    history_path = os.path.join(RUNTIME_DIR, "allocation_history.json")
    with open(history_path, "w") as f:
        json.dump(allocation_history, f, indent=2, sort_keys=True)

    # Write scheduler report
    report_path = os.path.join(RUNTIME_DIR, "scheduler_report.json")
    with open(report_path, "w") as f:
        json.dump(report_data, f, indent=2, sort_keys=True)
