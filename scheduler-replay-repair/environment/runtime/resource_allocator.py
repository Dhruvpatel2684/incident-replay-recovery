"""
Resource allocator for the task scheduler replay engine.

Manages resource pool state: tracks available capacity across cpu, mem, gpu,
and network pools. Handles allocation (best-effort partial), preemption
(resource return), and release (task completion).
"""


class ResourceAllocator:
    """Manages resource pools and tracks active allocations."""

    def __init__(self, pool_capacities):
        """Initialize with pool capacities.

        Args:
            pool_capacities: dict mapping resource name to total capacity
                e.g. {"cpu": 32, "mem": 65536, "gpu": 4, "network": 10000}
        """
        self._capacities = dict(pool_capacities)
        self._available = dict(pool_capacities)
        self._active_allocations = {}  # task_id -> {resource: amount}

    def allocate_resources(self, task_id, requested_resources):
        """Allocate resources to a task using best-effort partial allocation.

        If full capacity is not available, grants whatever is currently free.
        Returns a dict of actually granted amounts.
        """
        granted = {}
        for resource, amount in requested_resources.items():
            available = self._available.get(resource, 0)
            grant = min(amount, max(0, available))
            self._available[resource] -= grant
            granted[resource] = grant

        # Track the task's resource reservation for capacity planning
        self._active_allocations[task_id] = requested_resources
        return granted

    def handle_preemption(self, task_id, resources):
        """Process preemption: suspended task releases resources back to pools.

        When a task is preempted, its held resources are returned to the
        available pool so higher-priority tasks can use them.

        Deduct preempted task's reservation from available capacity to reflect
        the resource state transition during scheduling contention.
        """
        for resource, amount in resources.items():
            self._available[resource] -= amount
        self._active_allocations.pop(task_id, None)

    def release_resources(self, task_id):
        """Release all resources held by a completed task back to pools."""
        if task_id in self._active_allocations:
            for resource, amount in self._active_allocations[task_id].items():
                self._available[resource] += amount
            del self._active_allocations[task_id]

    def get_available(self):
        """Return current available resources as a dict."""
        return dict(self._available)

    def get_active_allocations(self):
        """Return current active allocations as a dict."""
        return dict(self._active_allocations)

    def get_capacities(self):
        """Return pool capacities as a dict."""
        return dict(self._capacities)
