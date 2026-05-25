"""Helper module for data transformation."""

from lib.constants import MAX_ITEMS, DEFAULT_SEPARATOR


def process_data(items):
    """Process a list of items with transformation rules."""
    if not items:
        return []
    truncated = items[:MAX_ITEMS]
    return [transform(item) for item in truncated]


def transform(item):
    """Apply transformation to a single item."""
    return str(item).upper().strip()
