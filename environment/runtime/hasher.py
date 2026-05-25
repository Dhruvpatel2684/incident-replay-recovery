"""Deterministic shard assignment using a custom hash function."""


def assign_shard(event_id, num_shards):
    """Assign an event to a shard using deterministic hashing.

    Uses a simple polynomial rolling hash (base 31) to ensure
    consistent shard assignment across Python versions and runs.
    """
    h = 0
    for c in event_id:
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    return h % num_shards
