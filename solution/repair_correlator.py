#!/usr/bin/env python3
"""Repair script for the Geospatial Event Correlation Engine.

Patches defects in zone filtering, coordinate mapping, score computation,
and event ordering, then re-runs the correlator.
"""
import os
import sys


def patch_run_correlator():
    """Fix zone filter parsing to strip whitespace from zone names."""
    path = "/app/runtime/run_correlator.py"
    with open(path, "r") as f:
        content = f.read()

    content = content.replace(
        'active_zones = set(raw_zones.split(","))',
        'active_zones = set(z.strip() for z in raw_zones.split(","))'
    )

    with open(path, "w") as f:
        f.write(content)


def patch_grid():
    """Fix cell coordinate computation for negative values."""
    path = "/app/runtime/grid.py"
    with open(path, "r") as f:
        content = f.read()

    # Add math import
    content = content.replace(
        '"""Spatial Grid Index — assigns events to grid cells for proximity queries."""',
        '"""Spatial Grid Index — assigns events to grid cells for proximity queries."""\nimport math'
    )

    # Fix int() to math.floor() for correct negative coordinate handling
    content = content.replace(
        'cx = int((x - self._origin_x) / self._cell_size)',
        'cx = math.floor((x - self._origin_x) / self._cell_size)'
    )
    content = content.replace(
        'cy = int((y - self._origin_y) / self._cell_size)',
        'cy = math.floor((y - self._origin_y) / self._cell_size)'
    )

    with open(path, "w") as f:
        f.write(content)


def patch_correlator():
    """Fix window score computation: use assignment instead of accumulation."""
    path = "/app/runtime/correlator.py"
    with open(path, "r") as f:
        content = f.read()

    # Fix accumulation bug in window scores
    content = content.replace(
        'cell_readings[cell] += event["reading"]',
        'cell_readings[cell] = event["reading"]'
    )

    # Fix time window config section
    content = content.replace(
        'self._time_window = config.getint("correlation", "time_window_sec")',
        'self._time_window = config.getint("correlation.scoring", "time_window_sec")'
    )

    with open(path, "w") as f:
        f.write(content)


def patch_ingest():
    """Fix event merge sort to include zone_id as tiebreaker."""
    path = "/app/runtime/ingest.py"
    with open(path, "r") as f:
        content = f.read()

    content = content.replace(
        'merged.sort(key=lambda e: (e["timestamp"], e["seq"]))',
        'merged.sort(key=lambda e: (e["timestamp"], e["zone_id"], e["seq"]))'
    )

    with open(path, "w") as f:
        f.write(content)


def main():
    patch_run_correlator()
    patch_grid()
    patch_correlator()
    patch_ingest()

    # Remove stale output
    output_dir = "/app/runtime/output"
    for fname in os.listdir(output_dir):
        if fname.endswith(".json"):
            os.remove(os.path.join(output_dir, fname))

    # Re-run with fixed code
    sys.path.insert(0, "/app")
    for key in list(sys.modules.keys()):
        if key.startswith("runtime"):
            del sys.modules[key]

    from runtime.run_correlator import main as run_main
    run_main()


if __name__ == "__main__":
    main()
