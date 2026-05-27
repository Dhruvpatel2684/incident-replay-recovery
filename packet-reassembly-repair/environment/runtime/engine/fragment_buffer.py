"""
Fragment buffer management.

Stores incoming IP fragments indexed by their offset within the
original datagram. Detects overlapping fragments which may indicate
an evasion attack (e.g., Teardrop, overlapping payload injection).

Overlap detection rule: fragment A overlaps with existing fragment B
if A's byte range [offset, offset+length) intersects with B's range
[B.offset, B.offset+B.length). Specifically, overlap exists when:
  A.offset < B.offset + B.length  AND  A.offset + A.length > B.offset

A fragment that starts exactly where another ends (A.offset == B.end)
is NOT overlapping - it is adjacent.
"""


class FragmentBuffer:
    """Ordered buffer of IP fragments with overlap detection."""

    def __init__(self):
        self._fragments = []
        self._overlaps_detected = 0
        self._total_inserted = 0

    def insert(self, offset, length, payload, frag_id):
        """Insert a fragment into the buffer.

        Returns True if overlap was detected with existing fragments.
        """
        self._total_inserted += 1
        overlap_found = False

        for existing in self._fragments:
            ex_start = existing["offset"]
            ex_end = ex_start + existing["length"]
            new_start = offset
            new_end = offset + length

            # Check if ranges intersect
            if new_start < ex_end and new_end > ex_start:
                overlap_found = True
                break

        if overlap_found:
            self._overlaps_detected += 1

        self._fragments.append({
            "offset": offset,
            "length": length,
            "payload": payload,
            "frag_id": frag_id,
            "has_overlap": overlap_found,
        })

        # Keep sorted by offset for sequential reassembly
        self._fragments.sort(key=lambda f: f["offset"])
        return overlap_found

    def get_fragments(self):
        """Return all fragments in offset order."""
        return list(self._fragments)

    def get_overlap_count(self):
        return self._overlaps_detected

    def get_total_inserted(self):
        return self._total_inserted

    def get_coverage_bitmap(self, total_length):
        """Compute byte coverage bitmap for gap detection."""
        covered = [False] * total_length
        for frag in self._fragments:
            start = frag["offset"]
            end = min(start + frag["length"], total_length)
            for i in range(start, end):
                covered[i] = True
        return covered

    def has_complete_coverage(self, total_length):
        """Check if all bytes from 0 to total_length are covered."""
        bitmap = self.get_coverage_bitmap(total_length)
        return all(bitmap)
