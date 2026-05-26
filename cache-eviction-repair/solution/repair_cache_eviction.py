#!/usr/bin/env python3
"""Repair script for cache eviction system. Patches all defects and re-runs."""
import os
import sys


def patch_loader():
    """Fix tier config parsing to strip whitespace from tier names."""
    path = "/app/runtime/loader.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        'self._active_tiers = set(raw_tiers.split(","))',
        'self._active_tiers = set(item.strip() for item in raw_tiers.split(","))'
    )
    with open(path, "w") as f:
        f.write(content)


def patch_scorer():
    """Fix config section to use LRU-specific eviction parameters."""
    path = "/app/runtime/scorer.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        '"max_capacity": config.getint("eviction", "max_capacity")',
        '"max_capacity": config.getint("eviction.lru", "max_capacity")'
    )
    content = content.replace(
        '"staleness_threshold_sec": config.getint(\n            "eviction", "staleness_threshold_sec"\n        )',
        '"staleness_threshold_sec": config.getint(\n            "eviction.lru", "staleness_threshold_sec"\n        )'
    )
    with open(path, "w") as f:
        f.write(content)


def patch_evictor():
    """Fix peak score tracking to use max instead of accumulating."""
    path = "/app/runtime/evictor.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        'self._stats["peak_eviction_score"] += window_max_score',
        'self._stats["peak_eviction_score"] = max(self._stats["peak_eviction_score"], window_max_score)'
    )
    with open(path, "w") as f:
        f.write(content)


def patch_ranker():
    """Fix eviction ranking sort to include tier_id for deterministic ordering."""
    path = "/app/runtime/ranker.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        '''ranked.sort(key=lambda x: (
            x["access_time"],
            x["entry_id"],
        ))''',
        '''ranked.sort(key=lambda x: (
            x["access_time"],
            x["tier_id"],
            x["entry_id"],
        ))'''
    )
    with open(path, "w") as f:
        f.write(content)


def main():
    patch_loader()
    patch_scorer()
    patch_evictor()
    patch_ranker()

    # Re-run with fixed code
    sys.path.insert(0, "/app")
    for key in list(sys.modules.keys()):
        if key.startswith("runtime"):
            del sys.modules[key]
    from runtime.run_eviction import main as run_main
    run_main()


if __name__ == "__main__":
    main()
