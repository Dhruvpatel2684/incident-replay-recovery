#!/usr/bin/env python3
"""Repair script for WAL compaction system. Patches all defects and re-runs."""
import os
import sys


def patch_lsn_segment():
    """Fix segment number extraction: use right-shift not bitwise-AND."""
    path = "/app/runtime/lsn.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        'return lsn & shift',
        'return lsn >> shift'
    )
    with open(path, "w") as f:
        f.write(content)


def patch_checksum_fold():
    """Fix XOR fold lower mask: must be 32-bit not 16-bit."""
    path = "/app/runtime/checksum.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        'lower = accumulator & 0x0000FFFF',
        'lower = accumulator & 0xFFFFFFFF'
    )
    with open(path, "w") as f:
        f.write(content)


def patch_snapshot_boundary():
    """Fix checkpoint boundary: must round UP to include current epoch."""
    path = "/app/runtime/snapshot.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        'boundary = (max_lsn // self._checkpoint_interval) * self._checkpoint_interval',
        'boundary = ((max_lsn // self._checkpoint_interval) + 1) * self._checkpoint_interval'
    )
    with open(path, "w") as f:
        f.write(content)


def patch_compactor_gc():
    """Fix GC watermark comparison: tombstones AT watermark must be retained."""
    path = "/app/runtime/compactor.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        'if entry["op"] == "del" and entry["lsn"] <= gc_watermark:',
        'if entry["op"] == "del" and entry["lsn"] < gc_watermark:'
    )
    with open(path, "w") as f:
        f.write(content)


def main():
    patch_lsn_segment()
    patch_checksum_fold()
    patch_snapshot_boundary()
    patch_compactor_gc()

    sys.path.insert(0, "/app")
    for key in list(sys.modules.keys()):
        if key.startswith("runtime"):
            del sys.modules[key]
    from runtime.run_compaction import main as run_main
    run_main()


if __name__ == "__main__":
    main()
