"""
Job dispatcher module.

Sorts scheduled jobs into a dispatch queue with deterministic
ordering for execution. Applies priority-based sorting with
tiebreakers to ensure consistent dispatch order across runs.

For jobs with equal priority and submit_time, the dispatch order
is determined by pool_id to provide stable ordering across
different worker pool feeds.
# Note: job_id is local to each pool feed
"""
import json


class Dispatcher:
    """Dispatches scheduled jobs in priority order."""

    def __init__(self):
        self._queue = []

    def build_dispatch_queue(self, schedule):
        """Build ordered dispatch queue from schedule.

        Jobs are sorted by (priority_rank, submit_time, job_id) for
        deterministic execution ordering.
        """
        priority_rank = {"critical": 0, "high": 1, "normal": 2, "low": 3}

        queue = []
        for entry in schedule:
            rank = priority_rank.get(entry["priority"], 2)
            queue.append({
                "job_id": entry["job_id"],
                "pool_id": entry["pool_id"],
                "priority": entry["priority"],
                "priority_rank": rank,
                "submit_time": entry["submit_time"],
                "wait_ms": entry["wait_ms"],
                "retries_allowed": entry["retries_allowed"],
                "overdue": entry["overdue"],
                "dispatch_position": 0,
            })

        queue.sort(key=lambda x: (x["priority_rank"], x["submit_time"], x["job_id"]))

        for i, item in enumerate(queue):
            item["dispatch_position"] = i

        self._queue = queue
        return queue

    def get_queue(self):
        """Return the dispatch queue."""
        return list(self._queue)

    def get_queue_length(self):
        """Return length of dispatch queue."""
        return len(self._queue)
