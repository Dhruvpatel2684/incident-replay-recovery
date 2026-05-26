"""
Repair script for the build orchestrator's graph analyzer.

Fixes three interacting bugs in graph_analyzer.py:

1. are_independent() - Was checking only direct adjacency (one-hop edges)
   instead of full transitive reachability. Two targets connected through
   intermediate nodes were incorrectly reported as independent.

2. compute_priority() - Was using out-degree (direct dependent count) instead
   of the longest path from the target to any terminal node. This failed to
   capture how much total downstream work depends on a target.

3. find_parallel_set() - Was using a descending-priority greedy approach
   which coupled with bugs 1 and 2 produced an inflated and invalid set.
   Correct approach: find the widest topological layer (maximum antichain),
   preferring layers with lower average priority (closer to terminals).
"""

import sys
import os
import textwrap

# Path to the buggy module
GRAPH_ANALYZER_PATH = "/app/runtime/graph_analyzer.py"


def apply_fix():
    """Rewrite graph_analyzer.py with corrected algorithms."""

    fixed_code = textwrap.dedent('''\
        """
        Dependency graph analysis module for the build orchestrator.

        Provides functions to analyze the build target DAG:
        - Independence checking between targets (via transitive reachability)
        - Priority computation for scheduling (via critical path length)
        - Parallel execution set identification (via maximum antichain)

        Repaired: Fixed reachability, priority, and parallel set algorithms.
        """

        from collections import defaultdict, deque


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
                self.dependents = defaultdict(list)
                self.dependencies = defaultdict(list)

                for t in targets:
                    tid = t["id"]
                    for dep in t["dependencies"]:
                        self.dependents[dep].append(tid)
                        self.dependencies[tid].append(dep)

            def _can_reach(self, src, dst):
                """
                Check if there is any directed path from src to dst.

                Uses BFS through the dependents graph to find transitive connections.
                """
                visited = set()
                queue = deque([src])
                while queue:
                    node = queue.popleft()
                    if node == dst:
                        return True
                    if node in visited:
                        continue
                    visited.add(node)
                    for next_node in self.dependents.get(node, []):
                        queue.append(next_node)
                return False

            def are_independent(self, target_a, target_b):
                """
                Determine if two targets are independent (can execute in parallel).

                Two targets are independent if neither can reach the other through
                any path in the dependency graph (transitive closure check).
                """
                if self._can_reach(target_a, target_b):
                    return False
                if self._can_reach(target_b, target_a):
                    return False
                return True

            def compute_priority(self, target_id):
                """
                Compute scheduling priority for a target.

                Priority = longest path (by duration) from this target to any
                terminal node. This captures the total downstream critical path
                that depends on this target being completed.
                """
                if not hasattr(self, '_priority_cache'):
                    self._priority_cache = {}
                return self._compute_priority_recursive(target_id)

            def _compute_priority_recursive(self, tid):
                """Recursively compute longest path from tid to any terminal."""
                if tid in self._priority_cache:
                    return self._priority_cache[tid]

                deps = self.dependents.get(tid, [])
                if not deps:
                    # Terminal node - priority is just its own duration
                    self._priority_cache[tid] = self.targets[tid]["estimated_duration_ms"]
                    return self._priority_cache[tid]

                # Find the longest downstream path
                best_downstream = 0
                for d in deps:
                    val = self._compute_priority_recursive(d)
                    if val > best_downstream:
                        best_downstream = val

                result = self.targets[tid]["estimated_duration_ms"] + best_downstream
                self._priority_cache[tid] = result
                return result

            def compute_all_priorities(self):
                """Compute priorities for all targets."""
                priorities = {}
                for tid in self.target_ids:
                    priorities[tid] = self.compute_priority(tid)
                return priorities

            def find_parallel_set(self):
                """
                Find the maximum set of targets that can execute in parallel.

                Uses the topological layer approach: computes execution stages
                (each stage is a valid antichain), then selects the widest stage.
                Among stages of equal width, prefers the one with lowest average
                priority (closest to terminals, fewest ordering constraints).

                Returns:
                    List of target ids forming the maximum antichain
                """
                priorities = self.compute_all_priorities()
                stages = self.compute_execution_stages()

                # Find the widest stage (maximum antichain)
                max_width = max(len(s) for s in stages)
                widest_stages = [s for s in stages if len(s) == max_width]

                # Break ties: prefer stage with lowest average priority (ascending)
                best_stage = min(
                    widest_stages,
                    key=lambda s: sum(priorities[t] for t in s) / len(s)
                )

                return sorted(best_stage)

            def find_critical_path(self):
                """
                Find the critical path - the longest dependency chain by duration.

                Returns:
                    List of target ids on the critical path (from start to end)
                """
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
                    ready = []
                    for tid in remaining:
                        deps = set(self.dependencies.get(tid, []))
                        if deps.issubset(completed):
                            ready.append(tid)

                    if not ready:
                        break

                    stages.append(sorted(ready))
                    completed.update(ready)
                    remaining -= set(ready)

                return stages
    ''')

    with open(GRAPH_ANALYZER_PATH, 'w') as f:
        f.write(fixed_code)

    print("[repair] Fixed graph_analyzer.py:")
    print("  - are_independent: now uses BFS reachability (transitive closure)")
    print("  - compute_priority: now uses longest-path-to-terminal (critical path contribution)")
    print("  - find_parallel_set: now uses widest topological layer with ascending priority tie-break")


if __name__ == "__main__":
    apply_fix()
