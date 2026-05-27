"""
Flow control simulation engine.

Replays recorded network traces through the sender/receiver models
to produce transmission analytics.
"""
import json
from runtime.transport.sender import TransportSender
from runtime.transport.receiver import ReceiverModel
from runtime.core.constants import INITIAL_WINDOW_SIZE


class FlowSimulation:
    """Event-driven flow control simulation."""

    def __init__(self, trace_data):
        self._events = trace_data["events"]
        self._config = trace_data.get("config", {})
        self._loss_set = set(trace_data.get("loss_set", []))

        recv_buf = self._config.get("receiver_buffer", 64)
        recv_win = self._config.get("initial_recv_window", INITIAL_WINDOW_SIZE)

        self._sender = TransportSender(recv_win)
        self._receiver = ReceiverModel(recv_buf, self._loss_set)
        self._pending = []

    def run(self):
        """Execute simulation trace and return summary."""
        for event in self._events:
            etype = event["type"]
            ts = event["time_ms"]

            if etype == "send":
                self._do_send(ts, event.get("count", 1))
            elif etype == "ack_arrive":
                self._do_ack(ts)
            elif etype == "timeout":
                self._sender.handle_timeout(ts)
            elif etype == "drain":
                self._receiver.drain_buffer(event.get("amount", 8))
            elif etype == "window_update":
                self._sender.update_recv_window(event.get("window", INITIAL_WINDOW_SIZE))

        return self._build_summary()

    def _do_send(self, ts, count):
        """Attempt to send count segments."""
        for _ in range(count):
            sent = self._sender.attempt_send(ts)
            if sent:
                seq = self._sender._next_seq - 1
                self._pending.append((ts, seq))

    def _do_ack(self, ts):
        """Deliver pending segments to receiver and process ACKs."""
        to_deliver = [(t, s) for t, s in self._pending if t < ts]
        self._pending = [(t, s) for t, s in self._pending if t >= ts]

        for _, seq in to_deliver:
            result = self._receiver.receive_segment(seq)
            if result is not None:
                ack_num, recv_win = result
                self._sender.receive_ack(ts, ack_num)
                self._sender.update_recv_window(recv_win)

    def _build_summary(self):
        """Build simulation results summary."""
        tx_log = self._sender.get_tx_log()
        sent = sum(1 for e in tx_log if e["type"] == "sent")
        blocked = sum(1 for e in tx_log if e["type"] == "blocked")
        retx = sum(1 for e in tx_log if "retransmit" in e["type"])

        return {
            "sender_stats": self._sender.get_stats(),
            "receiver_stats": self._receiver.get_stats(),
            "segments_sent": sent,
            "segments_blocked": blocked,
            "retransmissions": retx,
        }
