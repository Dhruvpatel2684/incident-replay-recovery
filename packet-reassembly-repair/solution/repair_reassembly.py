#!/usr/bin/env python3
"""Repair script for packet reassembly system."""
import os
import sys


def patch_reassembler():
    """Fix datagram length: use max(offset+length) not sum of lengths."""
    path = "/app/runtime/engine/reassembler.py"
    with open(path, "r") as f:
        content = f.read()
    old = '''        # Compute total datagram length from fragment extents
        total_length = 0
        for frag in fragments:
            total_length += frag["length"]'''
    new = '''        # Compute total datagram length from fragment extents
        total_length = 0
        for frag in fragments:
            end = frag["offset"] + frag["length"]
            if end > total_length:
                total_length = end'''
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)


def patch_overlap_policy():
    """Fix 'first' policy: must return existing (already-written) value."""
    path = "/app/runtime/policy/overlap_policy.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        '''    if policy == "first":
        # First-arriving data wins: keep incoming (new fragment)
        return incoming''',
        '''    if policy == "first":
        # First-arriving data wins: keep existing (already written)
        return existing'''
    )
    with open(path, "w") as f:
        f.write(content)


def patch_checksum():
    """Fix checksum word order: big-endian (high byte first)."""
    path = "/app/runtime/metrics/integrity.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        '        # Form 16-bit word: first byte is LOW byte, second is HIGH byte\n'
        '        word = data[i] | (data[i + 1] << 8)',
        '        # Form 16-bit word: first byte is HIGH byte, second is LOW byte\n'
        '        word = (data[i] << 8) | data[i + 1]'
    )
    with open(path, "w") as f:
        f.write(content)


def patch_fragment_sort():
    """Fix fragment ordering: must be stable by (offset, frag_id)."""
    path = "/app/runtime/engine/fragment_buffer.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        '        # Keep sorted by offset for sequential reassembly\n'
        '        self._fragments.sort(key=lambda f: f["offset"])',
        '        # Keep sorted by offset, then by arrival order (frag_id) for stability\n'
        '        self._fragments.sort(key=lambda f: (f["offset"], f["frag_id"]))'
    )
    with open(path, "w") as f:
        f.write(content)


def main():
    patch_reassembler()
    patch_overlap_policy()
    patch_checksum()
    patch_fragment_sort()

    sys.path.insert(0, "/app")
    for key in list(sys.modules.keys()):
        if key.startswith("runtime"):
            del sys.modules[key]
    from runtime.run_reassembly import main as run_main
    run_main()


if __name__ == "__main__":
    main()
