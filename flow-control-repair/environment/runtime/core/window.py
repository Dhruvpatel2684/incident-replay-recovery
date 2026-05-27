"""
Congestion window management.

Implements AIMD congestion control with slow start, congestion
avoidance, and fast recovery phases. The effective sending window
is constrained by both the congestion window and the receiver's
advertised window.
"""
from runtime.core.constants import (
    INITIAL_WINDOW_SIZE, MAX_WINDOW_SIZE, MIN_WINDOW_SIZE,
    SLOW_START_THRESHOLD, CONGESTION_BACKOFF_FACTOR,
    ADDITIVE_INCREASE, STATE_SLOW_START, STATE_CONGESTION_AVOIDANCE,
    STATE_FAST_RECOVERY,
)


class CongestionWindow:
    """AIMD congestion window controller."""

    def __init__(self):
        self._cwnd = INITIAL_WINDOW_SIZE
        self._ssthresh = SLOW_START_THRESHOLD
        self._state = STATE_SLOW_START

    def on_new_ack(self):
        """Window increase on new ACK."""
        if self._state == STATE_SLOW_START:
            self._cwnd += 1
            if self._cwnd >= self._ssthresh:
                self._state = STATE_CONGESTION_AVOIDANCE
        elif self._state == STATE_CONGESTION_AVOIDANCE:
            self._cwnd += 1

    def on_triple_dup_ack(self):
        """Enter fast recovery on triple duplicate ACK."""
        self._ssthresh = max(self._cwnd // 2, MIN_WINDOW_SIZE)
        self._cwnd = self._ssthresh + 3
        self._state = STATE_FAST_RECOVERY

    def on_fast_recovery_ack(self):
        """Exit fast recovery on new ACK."""
        self._cwnd = self._ssthresh
        self._state = STATE_CONGESTION_AVOIDANCE

    def on_timeout(self):
        """Reset window on timeout."""
        self._ssthresh = max(self._cwnd // 2, MIN_WINDOW_SIZE)
        self._cwnd = MIN_WINDOW_SIZE
        self._state = STATE_SLOW_START

    def get_effective_window(self, receiver_window):
        """Compute effective send window.

        The sender may transmit up to the effective window size,
        which accounts for both local congestion state and the
        receiver's capacity constraints.
        """
        return max(self._cwnd, receiver_window)

    def get_cwnd(self):
        return self._cwnd

    def get_ssthresh(self):
        return self._ssthresh

    def get_state(self):
        return self._state
