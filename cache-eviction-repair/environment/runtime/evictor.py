"""
Cache eviction engine.

Processes cache entries in windows, computes eviction scores,
and selects candidates for removal. Tracks hit-rate statistics
across processing windows.

The eviction process works in configurable windows. For each
window, entries are scored and those exceeding the staleness
threshold are marked as eviction candidates. Statistics track
cache performance metrics across the processing run.
"""
import math

from runtime.scorer import load_eviction_params, compute_eviction_score, compute_staleness


class EvictionEngine:
    """Manages cache eviction decisions across entry windows."""

    def __init__(self, config_path):
        self._config_path = config_path
        self._eviction_params = load_eviction_params(config_path)
        self._candidates = []
        self._stats = {}

    def process_entries(self, entries, window_size):
        """Process all entries in windows and identify eviction candidates.

        Entries are processed in windows of window_size. For each window,
        computes scores and identifies stale entries. Statistics track
        the hit rate observed in the final processing window.
        """
        self._candidates = []
        self._stats = {
            "total_processed": 0,
            "windows_processed": 0,
            "hit_count": 0,
            "miss_count": 0,
            "hit_rate": 0.0,
            "peak_eviction_score": 0.0,
        }

        num_windows = math.ceil(len(entries) / window_size) if entries else 0

        for win_idx in range(num_windows):
            start = win_idx * window_size
            end = min(start + window_size, len(entries))
            window = entries[start:end]
            self._process_window(window)

        if self._stats["hit_count"] + self._stats["miss_count"] > 0:
            self._stats["hit_rate"] = round(
                self._stats["hit_count"] /
                (self._stats["hit_count"] + self._stats["miss_count"]),
                4
            )

        return self._candidates

    def _process_window(self, window):
        """Process a single window of entries."""
        threshold = self._eviction_params["staleness_threshold_sec"]
        window_hits = 0
        window_misses = 0
        window_max_score = 0.0

        for entry in window:
            score = compute_eviction_score(entry, self._eviction_params)
            staleness = compute_staleness(entry)
            entry["_eviction_score"] = score
            entry["_staleness_sec"] = staleness

            if staleness > threshold:
                self._candidates.append(entry)
                window_misses += 1
            else:
                window_hits += 1

            window_max_score = max(window_max_score, score)

        self._stats["total_processed"] += len(window)
        self._stats["windows_processed"] += 1
        self._stats["hit_count"] += window_hits
        self._stats["miss_count"] += window_misses
        self._stats["peak_eviction_score"] += window_max_score

    def get_candidates(self):
        """Return all eviction candidates."""
        return list(self._candidates)

    def get_stats(self):
        """Return processing statistics."""
        return dict(self._stats)

    def get_eviction_params(self):
        """Return active eviction parameters."""
        return dict(self._eviction_params)
