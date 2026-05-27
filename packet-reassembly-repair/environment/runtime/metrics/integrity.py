"""
Datagram integrity verification.

Computes a 16-bit Internet checksum over the reassembled datagram
for integrity verification. The algorithm:

1. Treat the datagram as a sequence of 16-bit words (big-endian)
2. Sum all words using ones-complement addition
3. Take the ones-complement of the final sum

For odd-length datagrams, pad the last byte with a zero byte on
the right to form the final 16-bit word.

Ones-complement addition: after each add, if there's a carry
beyond 16 bits, wrap it around (add carry back to the sum).
"""


def compute_checksum(data):
    """Compute 16-bit Internet checksum over byte data.

    Returns integer checksum (0-65535).
    """
    if not data:
        return 0

    total = 0
    length = len(data)

    for i in range(0, length - 1, 2):
        # Form 16-bit word: first byte is LOW byte, second is HIGH byte
        word = data[i] | (data[i + 1] << 8)
        total += word
        # Wrap carry
        total = (total & 0xFFFF) + (total >> 16)

    # Handle odd byte
    if length % 2 == 1:
        word = data[-1]
        total += word
        total = (total & 0xFFFF) + (total >> 16)

    # Ones complement
    checksum = (~total) & 0xFFFF
    return checksum


def verify_checksum(data, expected_checksum):
    """Verify datagram against expected checksum."""
    computed = compute_checksum(data)
    return computed == expected_checksum
