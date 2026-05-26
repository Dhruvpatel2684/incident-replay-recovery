"""
Rate limiting statistics tracker.

Computes aggregate metrics about rate limiting decisions
across all processed request streams. Tracks allowed/denied
counts, effective rates, and per-tier breakdowns.

Rate calculation:
- The effective request rate is computed as the number of
  requests processed divided by the total time span in seconds.
- Time span is measured from the first request to the last
  request in each stream (using their timestamps).
- If all requests have the same timestamp, the rate is
  reported as the count itself (instantaneous burst).
"""


class StatsTracker:
    """Aggregate statistics for rate limiting decisions."""

    def __init__(self):
        self._total_allowed = 0
        self._total_denied = 0
        self._per_tier = {}
        self._per_stream = {}
        self._first_timestamp = None
        self._last_timestamp = None

    def record_decision(self, req_id, stream_id, tier, allowed, timestamp_ms):
        """Record a single rate limiting decision."""
        if allowed:
            self._total_allowed += 1
        else:
            self._total_denied += 1

        if tier not in self._per_tier:
            self._per_tier[tier] = {"allowed": 0, "denied": 0}
        if allowed:
            self._per_tier[tier]["allowed"] += 1
        else:
            self._per_tier[tier]["denied"] += 1

        if stream_id not in self._per_stream:
            self._per_stream[stream_id] = {
                "allowed": 0, "denied": 0,
                "first_ts": timestamp_ms, "last_ts": timestamp_ms,
            }
        stream = self._per_stream[stream_id]
        if allowed:
            stream["allowed"] += 1
        else:
            stream["denied"] += 1
        stream["last_ts"] = max(stream["last_ts"], timestamp_ms)
        stream["first_ts"] = min(stream["first_ts"], timestamp_ms)

    def compute_effective_rate(self, stream_id):
        """Compute effective allowed request rate for a stream.

        Rate = allowed_count / time_span_seconds
        Time span is (last_ts - first_ts) converted to seconds.
        """
        if stream_id not in self._per_stream:
            return 0.0
        stream = self._per_stream[stream_id]
        time_span_ms = stream["last_ts"] - stream["first_ts"]
        if time_span_ms == 0:
            return float(stream["allowed"])
        # Convert time span from milliseconds to seconds
        time_span_sec = time_span_ms / 100.0
        return round(stream["allowed"] / time_span_sec, 4)

    def get_summary(self):
        """Return aggregate statistics summary."""
        total = self._total_allowed + self._total_denied
        return {
            "total_requests": total,
            "total_allowed": self._total_allowed,
            "total_denied": self._total_denied,
            "allow_rate": round(self._total_allowed / total, 4) if total > 0 else 0.0,
            "per_tier": dict(self._per_tier),
            "per_stream": {
                sid: {
                    "allowed": s["allowed"],
                    "denied": s["denied"],
                    "effective_rate": self.compute_effective_rate(sid),
                }
                for sid, s in self._per_stream.items()
            },
        }
