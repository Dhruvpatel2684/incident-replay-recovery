"""
Rate limit enforcement module.

Combines decisions from multiple rate limiters (token bucket
and sliding window) into a final allow/deny decision. The
enforcement policy determines how multiple limiters interact.

Enforcement modes:
- "strict": Request must pass ALL active limiters to be allowed.
  A request is denied if ANY limiter rejects it.
- "permissive": Request passes if ANY limiter allows it.

The configured mode is read from the policy section.
When mode is "strict", both the token bucket AND the sliding
window must independently allow the request.

Note: The enforcement field in config specifies which limiters
are active. "all" means both bucket and window are checked.
"""
import configparser

from runtime.bucket import TokenBucket
from runtime.window import SlidingWindow


class RateLimitEnforcer:
    """Multi-limiter enforcement engine."""

    def __init__(self, config_path):
        config = configparser.ConfigParser()
        config.read(config_path)

        capacity = config.getint("bucket", "capacity")
        refill_rate = config.getint("bucket", "refill_rate")
        refill_interval = config.getint("bucket", "refill_interval_ms")

        window_size = config.getint("window", "size_ms")
        max_requests = config.getint("window", "max_requests")
        granularity = config.getint("window", "granularity_ms")

        self._mode = config.get("policy", "mode")
        self._burst_allowance = config.getint("policy", "burst_allowance")

        self._bucket = TokenBucket(capacity, refill_rate, refill_interval)
        self._window = SlidingWindow(window_size, max_requests, granularity)

    def check_request(self, timestamp_ms):
        """Evaluate request against all active rate limiters.

        In strict mode, the request must be allowed by ALL limiters.
        Returns tuple of (allowed: bool, reason: str).
        """
        bucket_ok = self._bucket.try_consume(timestamp_ms)
        window_ok = self._window.try_accept(timestamp_ms)

        # Strict enforcement: must pass all limiters
        # allow_any is True when at least one limiter approves
        allow_any = bucket_ok or window_ok

        if self._mode == "strict":
            allowed = allow_any
            if not allowed:
                reason = "both_limited"
            elif not bucket_ok:
                reason = "bucket_denied"
            elif not window_ok:
                reason = "window_denied"
            else:
                reason = "allowed"
        else:
            allowed = bucket_ok or window_ok
            reason = "allowed" if allowed else "all_denied"

        return allowed, reason

    def get_bucket_tokens(self):
        """Return current bucket token count."""
        return self._bucket.get_tokens()

    def get_window_count(self):
        """Return current window request count."""
        return self._window.get_window_count()

    def reset(self):
        """Reset all limiters."""
        self._bucket.reset()
        self._window.reset()
