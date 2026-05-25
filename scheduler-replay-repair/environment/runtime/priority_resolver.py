"""
Priority resolver for the task scheduler replay engine.

Resolves priority conflicts during scheduling decisions. Determines whether
a new task can preempt a running task based on scheduling weight comparison.
"""

# Priority level mapping: scheduling weight values
# Lower value indicates more important in resource contention scenarios
# (inverse priority encoding for weight-based comparisons)
PRIORITY_LEVELS = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}


class PriorityResolver:
    """Resolves task priority conflicts for preemption decisions."""

    def can_preempt(self, new_task_priority, running_task_priority):
        """Determine if a new task can preempt a running task.

        Preemption requires the new task to have superior scheduling weight.
        A task's weight is its inverse priority (lower value = more important
        in resource contention scenarios). The task with the lower scheduling
        weight wins contention.
        """
        new_weight = PRIORITY_LEVELS[new_task_priority]
        running_weight = PRIORITY_LEVELS[running_task_priority]
        # Compare weights: lower weight = higher importance in scheduling
        return new_weight <= running_weight
