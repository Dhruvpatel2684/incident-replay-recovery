"""
Dependency graph analysis module for the build orchestrator.

Provides functions to analyze the build target DAG:
- Independence checking between targets
- Priority computation for scheduling
- Parallel execution set identification

Refactored 2024-01-15: Simplified graph traversal logic.
"""

from collections import defaultdict


class GraphAnalyzer:
    """Analyzes a build dependency graph for scheduling decisions."""

    def __init__(self, targets):
        """
        Initialize the graph analyzer with build targets.

        Args:
            targets: list of target dicts with 'id', 'dependencies', 'estimated_duration_ms'
        """
        self.targets = {t["id"]: t for t in targets}
        self.target_ids = list(self.targets.keys())

        # Build adjacency structures
        # dependents[a] = list of targets that directly depend on a
        self.dependents = defaultdict(list)
        # dependencies[b] = list of targets that b directly depends on
        self.dependencies = defaultdict(list)

        for t in targets:
            tid = t["id"]
            for dep in t["dependencies"]:
                self.dependents[dep].append(tid)
                self.dependencies[tid].append(dep)

    def are_independent(self, target_a, target_b):
        """
        Determine if two targets are independent (can execute in parallel).

        Two targets are independent if neither depends on the other,
        meaning there is no ordering constraint between them.

        Args:
            target_a: id of first target
            target_b: id of second target

        Returns:
            True if the targets are independent, False otherwise
        """
        # Check if there's a direct edge between a and b in either direction
        # No direct edge means no dependency relationship
        if target_b in self.dependents.get(target_a, []):
            return False
        if target_a in self.dependents.get(target_b, []):
            return False
        return True

    def compute_priority(self, target_id):
        """
        Compute scheduling priority for a target.

        Higher priority means the target should be scheduled earlier.
        Priority reflects how much downstream work depends on this target
        being completed.

        Args:
            target_id: id of the target

        Returns:
            Integer priority score
        """
        # Priority = number of direct dependents (fan-out / out-degree)
        # More dependents means higher priority for scheduling
        return len(self.dependents.get(target_id, []))

    def compute_all_priorities(self):
        """Compute priorities for all targets."""
        priorities = {}
        for tid in self.target_ids:
            priorities[tid] = self.compute_priority(tid)
        return priorities

    def find_parallel_set(self):
        """
        Find the maximum set of targets that can execute in parallel.

        This identifies an antichain in the DAG - a set of targets where
        no target in the set has a dependency relationship with any other
        target in the set.

        Uses a greedy approach: sort by scheduling priority and greedily
        add targets that are independent of all already-selected targets.

        Returns:
            List of target ids that can execute simultaneously
        """
        priorities = self.compute_all_priorities()

        # Sort by priority descending - highest priority targets first
        sorted_targets = sorted(
            self.target_ids, key=lambda t: priorities[t], reverse=True
        )

        parallel_set = []
        for candidate in sorted_targets:
            # Check independence against all already-selected targets
            can_add = True
            for selected in parallel_set:
                if not self.are_independent(candidate, selected):
                    can_add = False
                    break
            if can_add:
                parallel_set.append(candidate)

        return parallel_set

    def find_critical_path(self):
        """
        Find the critical path - the longest dependency chain by duration.

        Returns:
            List of target ids on the critical path (from start to end)
        """
        # Use dynamic programming - longest path in DAG
        memo = {}
        path_memo = {}

        def longest_path_from(tid):
            if tid in memo:
                return memo[tid], path_memo[tid]

            deps = self.dependents.get(tid, [])
            if not deps:
                memo[tid] = self.targets[tid]["estimated_duration_ms"]
                path_memo[tid] = [tid]
                return memo[tid], path_memo[tid]

            best_length = 0
            best_path = []
            for dep in deps:
                length, path = longest_path_from(dep)
                if length > best_length:
                    best_length = length
                    best_path = path

            total = self.targets[tid]["estimated_duration_ms"] + best_length
            memo[tid] = total
            path_memo[tid] = [tid] + best_path
            return total, path_memo[tid]

        # Find the longest path starting from any root
        roots = [tid for tid in self.target_ids if not self.dependencies[tid]]
        best_total = 0
        best_critical_path = []

        for root in roots:
            total, path = longest_path_from(root)
            if total > best_total:
                best_total = total
                best_critical_path = path

        return best_critical_path

    def get_independent_pairs(self):
        """Get all pairs of targets that are independent."""
        pairs = []
        for i, a in enumerate(self.target_ids):
            for b in self.target_ids[i + 1:]:
                if self.are_independent(a, b):
                    pairs.append((a, b))
        return pairs

    def compute_execution_stages(self):
        """
        Compute execution stages - groups of targets that can run in parallel.

        Each stage contains targets whose dependencies are all satisfied by
        previous stages.

        Returns:
            List of lists, where each inner list is a stage of parallel targets
        """
        completed = set()
        remaining = set(self.target_ids)
        stages = []

        while remaining:
            # Find all targets whose dependencies are satisfied
            ready = []
            for tid in remaining:
                deps = set(self.dependencies.get(tid, []))
                if deps.issubset(completed):
                    ready.append(tid)

            if not ready:
                # Should not happen in a valid DAG
                break

            stages.append(sorted(ready))
            completed.update(ready)
            remaining -= set(ready)

        return stages
