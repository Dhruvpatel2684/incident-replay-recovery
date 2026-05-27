"""
Transport sender coordinating window, ACK tracking, and flow control.

Processes send opportunities and ACK arrivals, making transmission
decisions based on the effective window constraint.
"""
from runtime.core.window import CongestionWindow
from runtime.core.sequence import seq_add
from runtime.protocols.ack_tracker import AckTracker


class TransportSender:
    """Flow-controlled transport sender."""

    def __init__(self, initial_recv_window):
        self._window = CongestionWindow()
        self._tracker = AckTracker()
        self._recv_window = initial_recv_window
        self._next_seq = 0
        self._tx_log = []

    def attempt_send(self, timestamp_ms):
        """Try to send one segment. Returns True if sent, False if blocked."""
        effective = self._window.get_effective_window(self._recv_window)
        in_flight = self._tracker.get_flight_size()

        if in_flight >= effective:
            self._tx_log.append({
                "type": "blocked", "seq": self._next_seq,
                "time_ms": timestamp_ms, "window": effective,
                "flight": in_flight,
            })
            return False

        seq = self._next_seq
        self._tracker.register_send(seq)
        self._next_seq = seq_add(seq, 1)
        self._tx_log.append({
            "type": "sent", "seq": seq, "time_ms": timestamp_ms,
            "window": effective, "flight": in_flight + 1,
        })
        return True

    def receive_ack(self, timestamp_ms, ack_num):
        """Process incoming ACK."""
        is_new, freed = self._tracker.process_ack(ack_num)

        if is_new:
            if self._window.get_state() == "fast_recovery":
                self._window.on_fast_recovery_ack()
            else:
                self._window.on_new_ack()
        else:
            if self._tracker.has_triple_dup():
                self._window.on_triple_dup_ack()
                self._tracker.mark_retransmit()
                self._tx_log.append({
                    "type": "fast_retransmit",
                    "seq": self._tracker.get_send_base(),
                    "time_ms": timestamp_ms,
                    "window": self._window.get_cwnd(),
                    "flight": self._tracker.get_flight_size(),
                })

        return is_new, freed

    def handle_timeout(self, timestamp_ms):
        """Handle RTO timeout."""
        self._window.on_timeout()
        self._tx_log.append({
            "type": "timeout", "seq": self._tracker.get_send_base(),
            "time_ms": timestamp_ms, "window": self._window.get_cwnd(),
            "flight": self._tracker.get_flight_size(),
        })

    def update_recv_window(self, new_window):
        """Update receiver advertised window."""
        self._recv_window = new_window

    def get_tx_log(self):
        return list(self._tx_log)

    def get_stats(self):
        return {
            "cwnd": self._window.get_cwnd(),
            "ssthresh": self._window.get_ssthresh(),
            "state": self._window.get_state(),
            "recv_window": self._recv_window,
            "next_seq": self._next_seq,
            **self._tracker.get_stats(),
        }
