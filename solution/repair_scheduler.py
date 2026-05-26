#!/usr/bin/env python3
"""Repair script for the priority task scheduler.

Fixes four defects:
1. Group name parsing - strip whitespace from comma-separated config values
2. Config section - read batch_window from scheduler.execution, not scheduler
3. Window stats - use assignment (last-write-wins) not accumulation
4. Sort order - add priority_class to sort key for deterministic ordering
"""

import os
import sys


def patch_scheduler():
    """Patch the scheduler.py source file."""
    path = "/app/runtime/scheduler.py"
    with open(path, "r") as f:
        content = f.read()

    # Fix 1: Strip whitespace in group parsing
    content = content.replace(
        'return set(raw.split(","))',
        'return set(item.strip() for item in raw.split(","))'
    )

    # Fix 2: Read batch_window from correct section
    content = content.replace(
        'return config.getint("scheduler", "batch_window")',
        'return config.getint("scheduler.execution", "batch_window")'
    )

    # Fix 3: Window stats - use assignment not accumulation
    content = content.replace(
        '            load_by_priority[pclass] += snapshot["duration_seconds"]',
        '            load_by_priority[pclass] = snapshot["duration_seconds"]'
    )

    # Fix 4: Add priority_class to sort key for deterministic ordering
    content = content.replace(
        """        key=lambda j: (
            j["scheduled_at"],
            -priority_map.get(j["priority_class"], 0),
            j["seq"]
        )""",
        """        key=lambda j: (
            j["scheduled_at"],
            -priority_map.get(j["priority_class"], 0),
            j["priority_class"],
            j["seq"]
        )"""
    )

    with open(path, "w") as f:
        f.write(content)


def main():
    patch_scheduler()

    # Re-run with fixed code
    sys.path.insert(0, "/app")
    for key in list(sys.modules.keys()):
        if "scheduler" in key or "runtime" in key:
            del sys.modules[key]

    sys.path.insert(0, "/app/runtime")
    from run_scheduler import main as run_main
    run_main()

    return 0


if __name__ == "__main__":
    sys.exit(main())
