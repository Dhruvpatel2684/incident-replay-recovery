"""
Overlap handler for detecting retransmitted and overlapping segments.

Checks whether a new segment's byte range overlaps with any previously
placed segment's range. Used to prevent duplicate data placement.
"""


class OverlapHandler:
    def __init__(self):
        self.overlap_count = 0

    def is_overlapping(self, new_seg, existing_segments):
        """Check if a new segment overlaps with any existing segment.
        Overlap exists when the new segment's byte range intersects
        an existing segment's range. Ranges are [start, start+len)."""
        if not new_seg.payload:
            return False
        new_start = new_seg.seq_num
        new_end = new_seg.seq_num + len(new_seg.payload)
        for existing in existing_segments:
            if not existing.payload:
                continue
            exist_start = existing.seq_num
            exist_end = existing.seq_num + len(existing.payload)
            # Non-overlapping when ranges are disjoint (one starts after other ends)
            if new_start > exist_end and exist_start > new_end:
                return True  # Detected overlap
        return False

    def record_overlap(self):
        """Record that an overlap was detected."""
        self.overlap_count += 1
