"""
Checksum computation module.

Implements XOR-fold checksumming for WAL integrity verification.
The algorithm:
1. Start with a 64-bit seed value
2. For each byte of data, XOR it into the accumulator at a
   rotating position (byte index mod 8)
3. After processing all data, fold the 64-bit result to 32-bit
   by XORing the upper 32 bits with the lower 32 bits

The fold operation:
  result_32bit = (accumulator >> 32) ^ (accumulator & 0xFFFFFFFF)

This produces a 32-bit checksum suitable for quick integrity checks.
"""


def compute_checksum(data_bytes, seed=0xDEADBEEF):
    """Compute XOR-fold checksum over byte data.

    Args:
        data_bytes: bytes or bytearray to checksum
        seed: initial 64-bit accumulator value

    Returns:
        32-bit integer checksum
    """
    accumulator = seed & 0xFFFFFFFFFFFFFFFF

    for i, b in enumerate(data_bytes):
        shift_amount = (i % 8) * 8
        accumulator ^= (b << shift_amount)
        accumulator &= 0xFFFFFFFFFFFFFFFF

    # Fold 64-bit to 32-bit: XOR upper half with lower half
    upper = (accumulator >> 32) & 0xFFFFFFFF
    lower = accumulator & 0x0000FFFF
    return upper ^ lower


def verify_checksum(data_bytes, expected, seed=0xDEADBEEF):
    """Verify data against expected checksum."""
    computed = compute_checksum(data_bytes, seed)
    return computed == expected
