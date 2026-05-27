"""
Reassembly statistics collector.

Aggregates metrics across all processed packet streams including
fragment counts, overlap rates, and reassembly success/failure.
"""


class ReassemblyStats:
    """Collects and aggregates reassembly metrics."""

    def __init__(self):
        self._streams_processed = 0
        self._total_fragments = 0
        self._total_overlaps = 0
        self._successful_reassemblies = 0
        self._failed_reassemblies = 0
        self._total_gaps = 0
        self._total_bytes_reassembled = 0
        self._per_stream = {}

    def record_stream(self, stream_id, fragments, overlaps, result):
        """Record metrics for one reassembled stream."""
        self._streams_processed += 1
        self._total_fragments += fragments
        self._total_overlaps += overlaps

        if result is not None and result["gaps"] == 0:
            self._successful_reassemblies += 1
            self._total_bytes_reassembled += result["total_length"]
        else:
            self._failed_reassemblies += 1
            if result:
                self._total_gaps += result["gaps"]

        self._per_stream[stream_id] = {
            "fragments": fragments,
            "overlaps": overlaps,
            "success": result is not None and result["gaps"] == 0,
            "length": result["total_length"] if result else 0,
            "gaps": result["gaps"] if result else 0,
        }

    def get_summary(self):
        return {
            "streams_processed": self._streams_processed,
            "total_fragments": self._total_fragments,
            "total_overlaps": self._total_overlaps,
            "successful_reassemblies": self._successful_reassemblies,
            "failed_reassemblies": self._failed_reassemblies,
            "total_gaps": self._total_gaps,
            "total_bytes_reassembled": self._total_bytes_reassembled,
            "overlap_rate": round(
                self._total_overlaps / max(1, self._total_fragments), 4
            ),
            "success_rate": round(
                self._successful_reassemblies / max(1, self._streams_processed), 4
            ),
        }

    def get_per_stream(self):
        return dict(self._per_stream)
