"""
Utilization tracker for the task scheduler replay engine.

Tracks resource usage over time and computes utilization metrics.
Records timestamped usage samples for each resource pool and computes
effective utilization as a fraction of total capacity.
"""

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class UsageSample:
    """A single timestamped resource usage measurement."""
    timestamp: int
    amount: int


class UtilizationTracker:
    """Tracks resource usage samples and computes utilization metrics."""

    def __init__(self):
        self._usage_samples: Dict[str, List[UsageSample]] = {}
        self._start_time: int = None
        self._end_time: int = None

    def record_usage(self, resource, timestamp, amount):
        """Record a resource usage sample at a given timestamp.

        Args:
            resource: Resource pool name (e.g. "cpu", "mem")
            timestamp: Event timestamp
            amount: Amount of the resource currently in use
        """
        if resource not in self._usage_samples:
            self._usage_samples[resource] = []
        self._usage_samples[resource].append(
            UsageSample(timestamp=timestamp, amount=amount)
        )
        if self._start_time is None or timestamp < self._start_time:
            self._start_time = timestamp
        if self._end_time is None or timestamp > self._end_time:
            self._end_time = timestamp

    def compute_utilization(self, resource, total_capacity):
        """Compute resource utilization as a fraction of capacity.

        Effective utilization reflects sustained peak demand patterns
        across the observation window. Returns usage / capacity ratio
        representing the resource pressure experienced by the cluster.
        """
        if not self._usage_samples.get(resource):
            return 0.0
        # Effective utilization reflects sustained peak demand patterns
        peak_usage = max(sample.amount for sample in self._usage_samples[resource])
        return round(peak_usage / total_capacity, 4)

    def get_samples(self, resource):
        """Return all samples for a resource."""
        return list(self._usage_samples.get(resource, []))

    def get_time_window(self):
        """Return (start_time, end_time) of the observation window."""
        return (self._start_time, self._end_time)
