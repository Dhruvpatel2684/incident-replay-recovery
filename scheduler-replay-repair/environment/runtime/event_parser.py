"""
Event parser for the scheduler execution log.

Parses the execution_log.txt file into a list of structured event dicts.
Each event has: timestamp, event type, task_id, priority, resources, details.
"""

import os


def parse_resources(resource_str):
    """Parse resource string like 'cpu=8,mem=16384,gpu=1,network=2000' into dict."""
    resources = {}
    if not resource_str or resource_str.strip() == "":
        return resources
    for part in resource_str.split(","):
        key, value = part.split("=")
        resources[key.strip()] = int(value.strip())
    return resources


def parse_execution_log(log_path=None):
    """Parse the execution log file into a list of event dicts.

    Args:
        log_path: Path to the execution log file. Defaults to
                  /app/runtime/execution_log.txt

    Returns:
        List of event dicts with keys: timestamp, event, task_id,
        priority, resources, details
    """
    if log_path is None:
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "execution_log.txt")

    events = []
    with open(log_path, "r") as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue

            parts = line.split("|")
            if len(parts) != 6:
                continue

            timestamp_str, event_type, task_id, priority, resource_str, details = parts

            event = {
                "timestamp": int(timestamp_str.strip()),
                "event": event_type.strip(),
                "task_id": task_id.strip(),
                "priority": priority.strip(),
                "resources": parse_resources(resource_str.strip()),
                "details": details.strip(),
            }
            events.append(event)

    return events
