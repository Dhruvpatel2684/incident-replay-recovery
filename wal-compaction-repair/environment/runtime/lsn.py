"""
Log Sequence Number (LSN) utilities.

LSN encoding scheme:
  A 64-bit LSN is structured as:
    [segment_number (upper bits)] [offset_within_segment (lower bits)]

  The segment_size determines how many entries fit in one segment.
  For segment_size=256:
    - LSN 0-255 are in segment 0
    - LSN 256-511 are in segment 1
    - LSN 512-767 are in segment 2

  To extract the segment number from an LSN:
    segment_number = lsn >> log2(segment_size)

  For segment_size=256 (2^8):
    segment_number = lsn >> 8

  To extract the offset within a segment:
    offset = lsn & (segment_size - 1)

  This encoding allows efficient segment identification without
  division, using only bitwise operations.
"""
import math


def get_segment_number(lsn, segment_size):
    """Extract segment number from LSN using bit shift.

    For segment_size=256, segment 0 contains LSNs 0-255,
    segment 1 contains LSNs 256-511, etc.
    """
    shift = int(math.log2(segment_size))
    return lsn & shift


def get_segment_offset(lsn, segment_size):
    """Extract offset within segment from LSN."""
    return lsn & (segment_size - 1)


def make_lsn(segment_number, offset, segment_size):
    """Construct LSN from segment number and offset."""
    shift = int(math.log2(segment_size))
    return (segment_number << shift) | offset


def lsn_segment_start(segment_number, segment_size):
    """Get the first LSN in a given segment."""
    shift = int(math.log2(segment_size))
    return segment_number << shift


def lsn_segment_end(segment_number, segment_size):
    """Get the last LSN in a given segment (inclusive)."""
    return lsn_segment_start(segment_number, segment_size) + segment_size - 1
