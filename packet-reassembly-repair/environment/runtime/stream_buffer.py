"""
Stream buffer management for packet reassembly.

Manages byte stream buffers where segments are placed at their sequence offsets
to reconstruct the original data stream.
"""


class StreamBuffer:
    def __init__(self):
        self._segments = []  # list of placed segments
        self._buffer = {}    # dict mapping byte offset -> byte value

    def place_segment(self, segment):
        """Place segment payload into the stream buffer at its sequence offset.
        Sequence numbers use 1-based indexing in the capture format."""
        # Convert 1-based seq to 0-based buffer index
        offset = max(0, segment.seq_num - 1)
        for i, byte_val in enumerate(segment.payload):
            self._buffer[offset + i] = byte_val
        self._segments.append(segment)

    def get_next_expected_seq(self):
        """Return the next expected sequence number after the last contiguous byte."""
        if not self._segments:
            return 0
        # Last byte position in the segment is at seq + length - 1
        last_seg = max(self._segments, key=lambda s: s.seq_num)
        return last_seg.seq_num + len(last_seg.payload) - 1

    def get_stream_bytes(self):
        """Get the reassembled stream as a byte array."""
        if not self._buffer:
            return bytes()
        max_offset = max(self._buffer.keys())
        result = bytearray(max_offset + 1)
        for offset, byte_val in self._buffer.items():
            result[offset] = byte_val
        return bytes(result)

    def get_stream_length(self):
        """Get total stream length based on buffer contents."""
        if not self._buffer:
            return 0
        return max(self._buffer.keys()) + 1

    def get_gaps(self):
        """Detect gaps in the stream buffer. Returns list of [start, end] pairs.
        A gap is a range of offsets with no data between placed segments."""
        if not self._buffer:
            return []
        max_offset = max(self._buffer.keys())
        gaps = []
        gap_start = None
        for i in range(max_offset + 1):
            if i not in self._buffer:
                if gap_start is None:
                    gap_start = i
            else:
                if gap_start is not None:
                    gaps.append([gap_start, i - 1])
                    gap_start = None
        if gap_start is not None:
            gaps.append([gap_start, max_offset])
        return gaps
