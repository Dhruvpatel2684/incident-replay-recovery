"""
Token bucket rate limiter.

Implements a standard token bucket algorithm where tokens are
consumed on each request and refilled at a fixed rate. The bucket
has a maximum capacity and starts full.

Refill mechanics:
- Tokens are added at refill_rate per refill_interval
- Refill is computed lazily on each request based on elapsed time
- Partial intervals do NOT generate tokens (integer division)
- The bucket never exceeds its configured capacity

Example: with capacity=20, refill_rate=5, interval=1000ms:
  At t=0: 20 tokens (full)
  At t=999ms: still 20 tokens (no refill yet, interval not complete)
  At t=1000ms: 20 tokens (already full, refill capped)
  Consume 20 tokens at t=0, then at t=2500ms: 10 tokens added (2 intervals)
"""


class TokenBucket:
    """Token bucket with lazy refill computation."""

    def __init__(self, capacity, refill_rate, refill_interval_ms):
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._refill_interval_ms = refill_interval_ms
        self._tokens = capacity
        self._last_refill_time = 0

    def try_consume(self, timestamp_ms, tokens=1):
        """Attempt to consume tokens at the given timestamp.

        Returns True if tokens were available (request allowed),
        False otherwise (request denied).
        """
        self._refill(timestamp_ms)
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    def _refill(self, current_time_ms):
        """Compute and apply token refill based on elapsed time."""
        elapsed = current_time_ms - self._last_refill_time
        # Calculate complete intervals since last refill
        intervals = elapsed // self._refill_interval_ms
        if intervals > 0:
            new_tokens = (intervals + 1) * self._refill_rate
            self._tokens = min(self._capacity, self._tokens + new_tokens)
            self._last_refill_time += intervals * self._refill_interval_ms

    def get_tokens(self):
        """Return current token count."""
        return self._tokens

    def get_capacity(self):
        """Return bucket capacity."""
        return self._capacity

    def reset(self):
        """Reset bucket to full capacity."""
        self._tokens = self._capacity
        self._last_refill_time = 0
