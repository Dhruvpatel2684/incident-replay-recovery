"""
Transport receiver simulation.

Simulates receiver-side behavior: accepting segments, generating
cumulative ACKs, and advertising the receive window based on
available buffer space.
"""
from runtime.core.sequence import seq_add


class ReceiverModel:
    """Simulated transport receiver."""

    def __init__(self, buffer_capacity, loss_set=None):
        self._capacity = buffer_capacity
        self._buffer_used = 0
        self._next_expected = 0
        self._loss_set = loss_set or set()
        self._out_of_order = set()
        self._total_received = 0
        self._total_delivered = 0

    def receive_segment(self, seq_num):
        """Process incoming segment.

        Returns (ack_num, advertised_window) or None if lost.
        """
        if seq_num in self._loss_set:
            return None

        self._total_received += 1

        # Compute advertised window BEFORE consuming buffer
        adv_window = self._capacity - self._buffer_used

        if seq_num == self._next_expected:
            self._buffer_used += 1
            self._next_expected = seq_add(seq_num, 1)
            self._total_delivered += 1

            # Deliver any buffered out-of-order segments
            while self._next_expected in self._out_of_order:
                self._out_of_order.discard(self._next_expected)
                self._next_expected = seq_add(self._next_expected, 1)
                self._buffer_used += 1
                self._total_delivered += 1
        else:
            self._out_of_order.add(seq_num)
            self._buffer_used += 1

        return self._next_expected, adv_window

    def drain_buffer(self, amount):
        """Application consumes data from buffer."""
        self._buffer_used = max(0, self._buffer_used - amount)

    def get_stats(self):
        return {
            "total_received": self._total_received,
            "total_delivered": self._total_delivered,
            "buffer_used": self._buffer_used,
            "buffer_capacity": self._capacity,
            "next_expected": self._next_expected,
            "out_of_order_count": len(self._out_of_order),
        }
