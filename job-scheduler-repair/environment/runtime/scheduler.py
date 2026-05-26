"""
Core scheduler module.

Processes jobs in batches, applying priority-based ordering and
deadline-aware retry logic. Tracks scheduling statistics including
maximum wait times per batch window.

The scheduler processes jobs in configurable batch sizes and
maintains metrics about scheduling performance across all batches.
"""
import configparser
import math


class JobScheduler:
    """Priority-based job scheduler with deadline awareness."""

    def __init__(self, config_path):
        self._config = configparser.ConfigParser()
        self._config.read(config_path)
        self._max_retries = self._config.getint("scheduling", "max_retries")
        self._time_slice = self._config.getint("scheduling", "time_slice_ms")
        self._schedule = []
        self._stats = {}

    def process_jobs(self, jobs, batch_size):
        """Process all jobs in batches and build the schedule.

        Jobs are processed in batches of batch_size. For each batch,
        jobs are assigned time slots and retry budgets. Statistics
        track the maximum wait time observed in the final batch window.
        """
        self._schedule = []
        self._stats = {
            "total_scheduled": 0,
            "batch_count": 0,
            "max_wait_ms": 0,
            "total_retries_allocated": 0,
            "overdue_count": 0,
        }

        num_batches = math.ceil(len(jobs) / batch_size) if jobs else 0

        for batch_idx in range(num_batches):
            start = batch_idx * batch_size
            end = min(start + batch_size, len(jobs))
            batch = jobs[start:end]
            self._process_batch(batch, batch_idx)

        return self._schedule

    def _process_batch(self, batch, batch_idx):
        """Process a single batch of jobs into scheduled entries."""
        batch_max_wait = 0

        for idx, job in enumerate(batch):
            wait_ms = self._compute_wait(job, batch_idx, idx)
            retries = self._max_retries
            overdue = wait_ms > job.get("deadline_ms", float("inf"))

            entry = {
                "job_id": job["job_id"],
                "pool_id": job["pool_id"],
                "priority": job["priority"],
                "submit_time": job["submit_time"],
                "assigned_slot": batch_idx * len(batch) + idx,
                "wait_ms": wait_ms,
                "retries_allowed": retries,
                "overdue": overdue,
            }
            self._schedule.append(entry)
            batch_max_wait = max(batch_max_wait, wait_ms)

            if overdue:
                self._stats["overdue_count"] += 1

        self._stats["total_scheduled"] += len(batch)
        self._stats["batch_count"] += 1
        self._stats["total_retries_allocated"] += self._max_retries * len(batch)
        self._stats["max_wait_ms"] += batch_max_wait

    def _compute_wait(self, job, batch_idx, position):
        """Compute estimated wait time for a job based on batch position."""
        priority_weights = {"critical": 1, "high": 2, "normal": 4, "low": 8}
        weight = priority_weights.get(job["priority"], 4)
        return (batch_idx * self._time_slice + position * weight * 100)

    def get_schedule(self):
        """Return the full schedule."""
        return list(self._schedule)

    def get_stats(self):
        """Return scheduling statistics."""
        return dict(self._stats)

    def get_max_retries(self):
        """Return configured max retries."""
        return self._max_retries

    def get_batch_count(self):
        """Return number of batches processed."""
        return self._stats.get("batch_count", 0)
