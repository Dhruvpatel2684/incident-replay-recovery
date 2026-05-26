#!/usr/bin/env python3
"""Repair script for rate limiter system. Patches all defects and re-runs."""
import os
import sys


def patch_bucket():
    """Fix token refill calculation: remove off-by-one in interval count."""
    path = "/app/runtime/bucket.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        'new_tokens = (intervals + 1) * self._refill_rate',
        'new_tokens = intervals * self._refill_rate'
    )
    with open(path, "w") as f:
        f.write(content)


def patch_enforcer():
    """Fix strict mode: must pass ALL limiters, not ANY."""
    path = "/app/runtime/enforcer.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        'allow_any = bucket_ok or window_ok',
        'allow_any = bucket_ok and window_ok'
    )
    with open(path, "w") as f:
        f.write(content)


def patch_classifier():
    """Fix pattern matching: strip regex anchors for startswith comparison."""
    path = "/app/runtime/classifier.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        "self._static_pattern = config.get(\"classifier\", \"static_pattern\")",
        "self._static_pattern = config.get(\"classifier\", \"static_pattern\").lstrip('^')"
    )
    content = content.replace(
        "self._ws_pattern = config.get(\"classifier\", \"ws_pattern\")",
        "self._ws_pattern = config.get(\"classifier\", \"ws_pattern\").lstrip('^')"
    )
    content = content.replace(
        "self._health_pattern = config.get(\"classifier\", \"health_pattern\")",
        "self._health_pattern = config.get(\"classifier\", \"health_pattern\").lstrip('^')"
    )
    with open(path, "w") as f:
        f.write(content)


def patch_window():
    """Fix window boundary: use exclusive start for proper sliding window."""
    path = "/app/runtime/window.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        'if start_slot <= slot_idx <= end_slot:',
        'if start_slot < slot_idx <= end_slot:'
    )
    with open(path, "w") as f:
        f.write(content)


def patch_stats():
    """Fix rate calculation: divide by milliseconds/1000, not milliseconds/100."""
    path = "/app/runtime/stats.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        'time_span_sec = time_span_ms / 100.0',
        'time_span_sec = time_span_ms / 1000.0'
    )
    with open(path, "w") as f:
        f.write(content)


def main():
    patch_bucket()
    patch_enforcer()
    patch_classifier()
    patch_window()
    patch_stats()

    sys.path.insert(0, "/app")
    for key in list(sys.modules.keys()):
        if key.startswith("runtime"):
            del sys.modules[key]
    from runtime.run_limiter import main as run_main
    run_main()


if __name__ == "__main__":
    main()
