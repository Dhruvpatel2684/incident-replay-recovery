#!/usr/bin/env python3
"""Repair script for job scheduler system. Patches all defects and re-runs."""
import os
import sys


def patch_loader():
    """Fix pool config parsing to strip whitespace from pool names."""
    path = "/app/runtime/loader.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        'self._active_pools = set(raw_pools.split(","))',
        'self._active_pools = set(item.strip() for item in raw_pools.split(","))'
    )
    with open(path, "w") as f:
        f.write(content)


def patch_scheduler_section():
    """Fix config section name to use deadline-specific parameters."""
    path = "/app/runtime/scheduler.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        'self._max_retries = self._config.getint("scheduling", "max_retries")',
        'self._max_retries = self._config.getint("scheduling.deadlines", "max_retries")'
    )
    with open(path, "w") as f:
        f.write(content)


def patch_scheduler_accumulation():
    """Fix max_wait_ms to track maximum instead of accumulating."""
    path = "/app/runtime/scheduler.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        'self._stats["max_wait_ms"] += batch_max_wait',
        'self._stats["max_wait_ms"] = max(self._stats["max_wait_ms"], batch_max_wait)'
    )
    with open(path, "w") as f:
        f.write(content)


def patch_dispatcher_sort():
    """Fix dispatch sort to include pool_id for deterministic ordering."""
    path = "/app/runtime/dispatcher.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        'queue.sort(key=lambda x: (x["priority_rank"], x["submit_time"], x["job_id"]))',
        'queue.sort(key=lambda x: (x["priority_rank"], x["submit_time"], x["pool_id"], x["job_id"]))'
    )
    with open(path, "w") as f:
        f.write(content)


def main():
    patch_loader()
    patch_scheduler_section()
    patch_scheduler_accumulation()
    patch_dispatcher_sort()

    # Re-run with fixed code
    sys.path.insert(0, "/app")
    for key in list(sys.modules.keys()):
        if key.startswith("runtime"):
            del sys.modules[key]
    from runtime.run_scheduler import main as run_main
    run_main()


if __name__ == "__main__":
    main()
