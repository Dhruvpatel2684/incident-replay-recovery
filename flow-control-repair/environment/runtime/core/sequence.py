"""
Sequence number arithmetic with modular wraparound.

All sequence comparisons must handle wraparound at SEQUENCE_MODULUS.
"""
from runtime.core.constants import SEQUENCE_MODULUS


def seq_after(a, b):
    """Return True if sequence a is logically after sequence b."""
    diff = (a - b) % SEQUENCE_MODULUS
    return 0 < diff < SEQUENCE_MODULUS // 2


def seq_diff(a, b):
    """Compute logical distance from b to a."""
    diff = (a - b) % SEQUENCE_MODULUS
    if diff < SEQUENCE_MODULUS // 2:
        return diff
    return diff - SEQUENCE_MODULUS


def seq_add(base, offset):
    """Add offset to a sequence number with wraparound."""
    return (base + offset) % SEQUENCE_MODULUS
