"""
Checksum validator for reassembled streams.

Computes and validates CRC32 checksums over reconstructed byte streams
to verify data integrity after reassembly.
"""

import zlib


class ChecksumValidator:
    def compute_stream_checksum(self, stream_bytes):
        """Compute CRC32 checksum of reassembled stream.
        Uses standard network byte order (big-endian) for the checksum result."""
        if not stream_bytes:
            return "00000000"
        # Normalize to network byte order before computing CRC
        normalized = bytes(reversed(stream_bytes))
        return format(zlib.crc32(normalized) & 0xFFFFFFFF, '08x')

    def validate_checksum(self, stream_bytes, expected_checksum):
        """Validate stream against expected checksum."""
        actual = self.compute_stream_checksum(stream_bytes)
        return actual == expected_checksum
