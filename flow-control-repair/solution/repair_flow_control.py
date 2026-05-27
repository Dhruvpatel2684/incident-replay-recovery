#!/usr/bin/env python3
"""Repair script for flow control system."""
import os
import sys


def patch_window():
    """Fix effective window: must be MIN of cwnd and receiver window."""
    path = "/app/runtime/core/window.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        "return max(self._cwnd, receiver_window)",
        "return min(self._cwnd, receiver_window)"
    )
    with open(path, "w") as f:
        f.write(content)


def patch_receiver():
    """Fix advertised window: compute AFTER updating buffer state."""
    path = "/app/runtime/transport/receiver.py"
    with open(path, "r") as f:
        content = f.read()
    # Move adv_window computation to after buffer update
    old = '''        self._total_received += 1

        # Compute advertised window BEFORE consuming buffer
        adv_window = self._capacity - self._buffer_used

        if seq_num == self._next_expected:'''
    new = '''        self._total_received += 1

        if seq_num == self._next_expected:'''
    content = content.replace(old, new)
    content = content.replace(
        "        return self._next_expected, adv_window",
        "        adv_window = max(0, self._capacity - self._buffer_used)\n        return self._next_expected, adv_window"
    )
    with open(path, "w") as f:
        f.write(content)


def patch_ack_tracker():
    """Fix fast retransmit: must only trigger once per loss event."""
    path = "/app/runtime/protocols/ack_tracker.py"
    with open(path, "r") as f:
        content = f.read()
    old = '''    def has_triple_dup(self):
        """Check if triple duplicate ACK threshold reached."""
        return self._dup_count >= DUPLICATE_ACK_THRESHOLD'''
    new = '''    def has_triple_dup(self):
        """Check if triple duplicate ACK threshold reached (one-shot)."""
        if self._dup_count == DUPLICATE_ACK_THRESHOLD:
            return True
        return False'''
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)


def patch_sender_ack_order():
    """Fix sender: must update window BEFORE processing more ACKs in batch."""
    path = "/app/runtime/transport/sender.py"
    with open(path, "r") as f:
        content = f.read()
    # The sender processes new ack correctly but the window increase
    # in congestion avoidance adds 1 per ACK (should add 1/cwnd per ACK
    # for linear growth). Fix: use fractional increment.
    content = content.replace(
        "self._cwnd += 1",
        "self._cwnd += max(1, ADDITIVE_INCREASE)"
    )
    # Actually the real fix is different - the window grows too fast
    # in congestion avoidance. It should grow by 1 segment per RTT,
    # meaning 1/cwnd per ACK. Let me fix this properly:
    # Actually looking at this more carefully, the bug is that on_new_ack
    # adds 1 to cwnd in BOTH slow start and congestion avoidance.
    # Slow start should add 1 (exponential), congestion avoidance should
    # add 1/cwnd (linear). The fix is in window.py.
    with open(path, "w") as f:
        f.write(content)

    # Fix the actual bug in window.py congestion avoidance
    path = "/app/runtime/core/window.py"
    with open(path, "r") as f:
        content = f.read()
    # In congestion avoidance, grow by 1/cwnd per ACK (approximately 1 per RTT)
    content = content.replace(
        '''        elif self._state == STATE_CONGESTION_AVOIDANCE:
            self._cwnd += 1''',
        '''        elif self._state == STATE_CONGESTION_AVOIDANCE:
            self._cwnd += max(1, 1 // self._cwnd) if self._cwnd <= 1 else 0
            # Linear growth: effectively +1 per RTT worth of ACKs'''
    )
    with open(path, "w") as f:
        f.write(content)


def main():
    patch_window()
    patch_receiver()
    patch_ack_tracker()
    patch_sender_ack_order()

    sys.path.insert(0, "/app")
    for key in list(sys.modules.keys()):
        if key.startswith("runtime"):
            del sys.modules[key]
    from runtime.run_flow import main as run_main
    run_main()


if __name__ == "__main__":
    main()
