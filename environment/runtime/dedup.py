"""Event deduplication using an in-memory registry."""

import json
import os


class DedupRegistry:
    """Tracks seen event IDs to prevent duplicate processing."""

    def __init__(self, registry_path):
        self.registry_path = registry_path
        self.seen = set()
        self._load()

    def _load(self):
        """Load the dedup registry from disk."""
        if os.path.exists(self.registry_path):
            with open(self.registry_path, 'r') as f:
                data = json.load(f)
                self.seen = set(data.get("seen", []))

    def is_duplicate(self, event_id):
        """Check if an event has already been processed."""
        return event_id in self.seen

    def mark_seen(self, event_id):
        """Mark an event as processed."""
        self.seen.add(event_id)

    def save(self):
        """Persist the registry to disk."""
        with open(self.registry_path, 'w') as f:
            json.dump({"seen": sorted(list(self.seen))}, f, indent=2)
