"""
Acknowledgement tracking for the transport layer.

Maintains the send buffer of unacknowledged segments and
processes incoming cumulative ACKs. Tracks duplicate ACKs
for fast retransmit triggering.

Cumulative ACK semantics: an ACK for number N confirms all
data with sequence numbers strictly less than N.
"""
from runtime.core.sequence import seq_after, seq_diff, seq_add
from runtime.core.constants import DUPLICATE_ACK_THRESHOLD


class AckTracker:
    """Tracks sent segments and processes acknowledgements."""

    def __init__(self):
        self._send_base = 0
        self._unacked = {}
        self._last_ack = 0
        self._dup_count = 0
        self._total_acked = 0
        self._total_sent = 0
        self._retransmit_pending = False

    def register_send(self, seq_num):
        """Record a segment being transmitted."""
        self._unacked[seq_num] = True
        self._total_sent += 1

    def process_ack(self, ack_num):
        """Process cumulative ACK.

        Returns (is_new: bool, freed_count: int).
        """
        if seq_after(ack_num, self._send_base):
            freed = seq_diff(ack_num, self._send_base)
            for i in range(freed):
                seq = seq_add(self._send_base, i)
                self._unacked.pop(seq, None)
            self._send_base = ack_num
            self._last_ack = ack_num
            self._dup_count = 0
            self._total_acked += freed
            self._retransmit_pending = False
            return True, freed
        elif ack_num == self._last_ack:
            self._dup_count += 1
            return False, 0
        return False, 0

    def has_triple_dup(self):
        """Check if triple duplicate ACK threshold reached."""
        return self._dup_count >= DUPLICATE_ACK_THRESHOLD

    def mark_retransmit(self):
        """Mark that a retransmission was triggered."""
        self._retransmit_pending = True
        self._dup_count = 0

    def get_flight_size(self):
        """Number of segments currently in-flight (unacknowledged)."""
        return len(self._unacked)

    def get_send_base(self):
        return self._send_base

    def get_stats(self):
        return {
            "total_sent": self._total_sent,
            "total_acked": self._total_acked,
            "in_flight": self.get_flight_size(),
            "send_base": self._send_base,
            "dup_ack_count": self._dup_count,
        }
