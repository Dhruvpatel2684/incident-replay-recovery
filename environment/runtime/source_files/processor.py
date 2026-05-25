"""Batch data transformation module."""

from lib.constants import MAX_ITEMS, BATCH_SIZE


def transform_batch(items):
    """Transform items in batches."""
    if not items:
        return []
    results = []
    for i in range(0, min(len(items), MAX_ITEMS), BATCH_SIZE):
        batch = items[i:i + BATCH_SIZE]
        results.extend([item.upper() for item in batch])
    return results
