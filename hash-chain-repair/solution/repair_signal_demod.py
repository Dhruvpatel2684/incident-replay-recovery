#!/usr/bin/env python3
"""Repair script for cryptographic verification system. Patches all defects and re-runs."""
import os
import sys


def patch_hasher():
    """Fix leaf hash domain separation: prefix must precede data."""
    path = "/app/runtime/hasher.py"
    with open(path, "r") as f:
        content = f.read()
    # Bug: H(data || prefix) - prefix appended after
    # Fix: H(prefix || data) - prefix prepended before
    content = content.replace(
        'h.update(data + self._leaf_prefix)',
        'h.update(self._leaf_prefix + data)'
    )
    with open(path, "w") as f:
        f.write(content)


def patch_merkle_verify():
    """Fix proof verification direction logic."""
    path = "/app/runtime/merkle.py"
    with open(path, "r") as f:
        content = f.read()
    # Bug: direction semantics are inverted
    # When direction is 'right', sibling is on right -> H(current, sibling)
    # When direction is 'left', sibling is on left -> H(sibling, current)
    content = content.replace(
        '''        current = leaf_hash
        for step in proof:
            if step["direction"] == "right":
                current = self._hasher.hash_internal(step["hash"], current)
            else:
                current = self._hasher.hash_internal(current, step["hash"])''',
        '''        current = leaf_hash
        for step in proof:
            if step["direction"] == "left":
                current = self._hasher.hash_internal(step["hash"], current)
            else:
                current = self._hasher.hash_internal(current, step["hash"])'''
    )
    with open(path, "w") as f:
        f.write(content)


def patch_merkle_depth():
    """Fix tree depth to include leaf level."""
    path = "/app/runtime/merkle.py"
    with open(path, "r") as f:
        content = f.read()
    # Bug: returns len(levels) - 1, excluding leaf level
    # Fix: returns len(levels) which includes all levels
    content = content.replace(
        'return len(self._levels) - 1',
        'return len(self._levels)'
    )
    with open(path, "w") as f:
        f.write(content)


def patch_commitment():
    """Fix nonce byte encoding to use big-endian as specified."""
    path = "/app/runtime/commitment.py"
    with open(path, "r") as f:
        content = f.read()
    # Bug: little-endian encoding
    # Fix: big-endian encoding per specification
    content = content.replace(
        "byteorder='little'",
        "byteorder='big'"
    )
    with open(path, "w") as f:
        f.write(content)


def main():
    patch_hasher()
    patch_merkle_verify()
    patch_merkle_depth()
    patch_commitment()

    # Re-run with fixed code
    sys.path.insert(0, "/app")
    for key in list(sys.modules.keys()):
        if key.startswith("runtime"):
            del sys.modules[key]
    from runtime.run_verify import main as run_main
    run_main()


if __name__ == "__main__":
    main()
