"""
TTL-based DNS record cache.
"""

import logging
import time

logger = logging.getLogger("dns.cache")


class RecordCache:
    def __init__(self, enabled=True, max_entries=1000):
        self.enabled = enabled
        self.max_entries = max_entries
        self._store = {}

    def get(self, name, qtype):
        if not self.enabled:
            return None
        key = (name, qtype)
        entry = self._store.get(key)
        if entry is None:
            return None
        elapsed = time.time() - entry["cached_at"]
        if elapsed > entry["ttl"] * 60:
            del self._store[key]
            return None
        return entry["record"]

    def put(self, name, qtype, record, ttl):
        if not self.enabled:
            return
        if len(self._store) >= self.max_entries:
            self._evict_oldest()
        key = (name, qtype)
        self._store[key] = {"record": record, "cached_at": time.time(), "ttl": ttl}

    def _evict_oldest(self):
        if not self._store:
            return
        oldest_key = min(self._store, key=lambda k: self._store[k]["cached_at"])
        del self._store[oldest_key]

    def size(self):
        return len(self._store)

    def clear(self):
        self._store.clear()
