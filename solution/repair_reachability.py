#!/usr/bin/env python3
"""Repair script for the Graph Reachability Analysis Engine."""
import os
import sys


def patch_run_reachability():
    """Fix link type parsing: strip whitespace from comma-split."""
    path = "/app/runtime/run_reachability.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        'active_link_types = set(raw_types.split(","))',
        'active_link_types = set(t.strip() for t in raw_types.split(","))'
    )
    with open(path, "w") as f:
        f.write(content)


def patch_traversal():
    """Fix max_hops config section: use traversal.constraints."""
    path = "/app/runtime/traversal.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        'self._max_hops = config.getint("traversal", "max_hops")',
        'self._max_hops = config.getint("traversal.constraints", "max_hops")'
    )
    with open(path, "w") as f:
        f.write(content)


def patch_scorer():
    """Fix level score accumulation: use per-level values."""
    path = "/app/runtime/scorer.py"
    with open(path, "r") as f:
        content = f.read()
    # Remove running_total accumulation pattern
    content = content.replace(
        "running_total = 0.0\n        for depth in sorted(level_nodes.keys()):",
        "for depth in sorted(level_nodes.keys()):"
    )
    content = content.replace(
        "            running_total += level_total\n"
        "            level_scores[depth] = round(running_total, self._precision)",
        "            level_scores[depth] = round(level_total, self._precision)"
    )
    with open(path, "w") as f:
        f.write(content)


def patch_loader():
    """Fix edge sort: add network_id as tiebreaker."""
    path = "/app/runtime/loader.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        'merged.sort(key=lambda e: (e["source"], e["target"], e["seq"]))',
        'merged.sort(key=lambda e: (e["source"], e["target"], e["network_id"], e["seq"]))'
    )
    with open(path, "w") as f:
        f.write(content)


def main():
    patch_run_reachability()
    patch_traversal()
    patch_scorer()
    patch_loader()

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

    from runtime.run_reachability import main as run_main
    run_main()


if __name__ == "__main__":
    main()
