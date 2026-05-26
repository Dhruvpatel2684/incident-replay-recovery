"""
Sliding window rate limiter.

Implements a sliding window counter that tracks requests within
a configurable time window. The window is divided into fixed-size
granularity slots for efficient counting.

Window mechanics:
- The window spans size_ms milliseconds into the past
- Requests are counted in granularity_ms slots
- A request at time T looks back at [T - size_ms, T) for the count
- Request is allowed if count < max_requests

Slot calculation:
- Each timestamp maps to a slot index: timestamp_ms // granularity_ms
- Active slots are those within the current window
- The current slot (containing the request timestamp) is INCLUDED
  in the count since the request occupies that slot
"""


class SlidingWindow:
    """Sliding window counter with slot-based tracking."""

    def __init__(self, size_ms, max_requests, granularity_ms):
        self._size_ms = size_ms
        self._max_requests = max_requests
        self._granularity_ms = granularity_ms
        self._slots = {}

    def try_accept(self, timestamp_ms):
        """Check if request at timestamp is within rate limit.

        Counts all requests in the window [timestamp - size_ms, timestamp].
        Returns True if under limit, False if at capacity.
        """
        self._expire_old_slots(timestamp_ms)
        current_count = self._count_active(timestamp_ms)

        if current_count < self._max_requests:
            slot_idx = timestamp_ms // self._granularity_ms
            self._slots[slot_idx] = self._slots.get(slot_idx, 0) + 1
            return True
        return False

    def _expire_old_slots(self, current_time_ms):
        """Remove slots that have fallen outside the window."""
        window_start = current_time_ms - self._size_ms
        cutoff_slot = window_start // self._granularity_ms
        expired = [s for s in self._slots if s < cutoff_slot]
        for s in expired:
            del self._slots[s]

    def _count_active(self, timestamp_ms):
        """Count requests in all active slots within the window."""
        window_start = timestamp_ms - self._size_ms
        start_slot = window_start // self._granularity_ms
        end_slot = timestamp_ms // self._granularity_ms

        total = 0
        for slot_idx, count in self._slots.items():
            if start_slot <= slot_idx <= end_slot:
                total += count
        return total

    def get_window_count(self):
        """Return total count across all active slots."""
        return sum(self._slots.values())

    def get_max_requests(self):
        """Return configured maximum requests per window."""
        return self._max_requests

    def reset(self):
        """Clear all slots."""
        self._slots = {}
