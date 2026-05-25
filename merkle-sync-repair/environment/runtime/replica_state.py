"""
Replica state loader for the anti-entropy sync engine.

Loads replica data from JSON files and provides structured access
to per-key entries including value, vector clock, version, tombstone
flag, and last_modified timestamp.
"""

import json
import os


RUNTIME_DIR = "/app/runtime"


def load_replica(name):
    """Load a replica JSON file by name (e.g., 'a', 'b', 'c').

    Returns a dict mapping key -> entry dict with fields:
        value, vclock, version, tombstone, last_modified
    """
    path = os.path.join(RUNTIME_DIR, f"replica_{name}.json")
    with open(path, "r") as f:
        return json.load(f)


def load_all_replicas():
    """Load all three replicas.

    Returns dict mapping replica ID ('A', 'B', 'C') to their data dicts.
    """
    replicas = {}
    for name in ["a", "b", "c"]:
        replicas[name.upper()] = load_replica(name)
    return replicas


def get_all_keys(replicas):
    """Get the union of all keys across all replicas."""
    all_keys = set()
    for replica_data in replicas.values():
        all_keys.update(replica_data.keys())
    return all_keys
