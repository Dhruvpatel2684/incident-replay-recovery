"""
Tests for the build orchestrator execution plan.

Validates correctness of dependency analysis, scheduling priorities,
parallelism identification, and critical path computation.
"""

import json
import hashlib
import os
import pytest
from collections import deque, defaultdict


PLAN_PATH = "/app/runtime/output/build_plan.json"
TARGETS_PATH = "/app/runtime/build_targets.json"


@pytest.fixture(scope="session")
def plan():
    """Load the build plan."""
    with open(PLAN_PATH, "r") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def targets():
    """Load raw build targets."""
    with open(TARGETS_PATH, "r") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def graph(targets):
    """Build the dependency graph structures."""
    targets_map = {t["id"]: t for t in targets}
    dependents = defaultdict(list)
    dependencies = defaultdict(list)
    for t in targets:
        tid = t["id"]
        for dep in t["dependencies"]:
            dependents[dep].append(tid)
            dependencies[tid].append(dep)
    return {
        "targets_map": targets_map,
        "dependents": dependents,
        "dependencies": dependencies,
        "target_ids": list(targets_map.keys())
    }


def can_reach(graph_data, src, dst):
    """Check if there is a directed path from src to dst."""
    visited = set()
    queue = deque([src])
    while queue:
        node = queue.popleft()
        if node == dst:
            return True
        if node in visited:
            continue
        visited.add(node)
        for n in graph_data["dependents"].get(node, []):
            queue.append(n)
    return False


# ============================================================
# TIER 1: Structural tests (always pass, even with bugs)
# ============================================================

class TestStructural:
    """Basic structural validation of the build plan."""

    def test_plan_file_exists(self):
        """The plan output file must exist."""
        assert os.path.exists(PLAN_PATH), "build_plan.json not found"

    def test_plan_has_all_targets(self, plan):
        """Plan must contain all 15 build targets."""
        assert plan["total_targets"] == 15
        assert len(plan["targets"]) == 15

    def test_plan_has_required_fields(self, plan):
        """Plan must have all required top-level fields."""
        required = ["plan_version", "total_targets", "targets", "analysis",
                    "priorities", "fingerprint"]
        for field in required:
            assert field in plan, f"Missing field: {field}"

    def test_target_durations_present(self, plan):
        """Every target must have a positive duration."""
        for t in plan["targets"]:
            assert "estimated_duration_ms" in t
            assert t["estimated_duration_ms"] > 0

    def test_dag_is_acyclic(self, plan):
        """The dependency graph must be acyclic (valid DAG)."""
        targets_map = {t["id"]: t for t in plan["targets"]}
        visited = set()
        in_stack = set()

        def has_cycle(node):
            if node in in_stack:
                return True
            if node in visited:
                return False
            visited.add(node)
            in_stack.add(node)
            for dep in targets_map[node]["dependencies"]:
                if has_cycle(dep):
                    return True
            in_stack.discard(node)
            return False

        for tid in targets_map:
            assert not has_cycle(tid), f"Cycle detected involving {tid}"

    def test_no_self_dependencies(self, plan):
        """No target should depend on itself."""
        for t in plan["targets"]:
            assert t["id"] not in t["dependencies"], \
                f"{t['id']} depends on itself"

    def test_all_deps_resolve(self, plan):
        """All dependency references must point to valid targets."""
        valid_ids = {t["id"] for t in plan["targets"]}
        for t in plan["targets"]:
            for dep in t["dependencies"]:
                assert dep in valid_ids, \
                    f"{t['id']} depends on unknown target {dep}"


# ============================================================
# TIER 2: Medium difficulty (some fail with bugs)
# ============================================================

class TestMedium:
    """Tests that validate analysis correctness at medium granularity."""

    def test_independent_pair_count(self, plan):
        """Independent pair count should reflect transitive dependencies.

        With 15 targets in a connected DAG, the count of truly independent
        pairs (no path between them in either direction) should be
        significantly less than C(15,2) = 105.
        """
        count = plan["analysis"]["independent_pair_count"]
        # Correct value is 29. Buggy value is 84.
        assert count <= 40, \
            f"Independent pair count {count} is too high - suggests adjacency-only checking"
        assert count >= 20, \
            f"Independent pair count {count} is too low"

    def test_critical_path_length(self, plan):
        """Critical path duration must equal the longest chain in the DAG."""
        cp_length = plan["analysis"]["critical_path_length_ms"]
        assert cp_length == 11300, \
            f"Critical path length {cp_length} != expected 11300ms"

    def test_priority_ordering_mid_graph(self, plan):
        """Targets with longer downstream paths should have higher priority.

        target_3 (parser-module) leads to a chain of length 5 to terminal.
        target_4 (config-module) leads to a chain of length 5 but shorter duration.
        target_3's priority should be higher than target_4's because its
        downstream critical path is longer in total duration.
        """
        priorities = plan["priorities"]
        # Correct: target_3=10100 > target_4=9600
        # Buggy: target_3=1 < target_4=2 (out-degree)
        assert priorities["target_3"] > priorities["target_4"], \
            f"target_3 (priority {priorities['target_3']}) should have higher " \
            f"priority than target_4 (priority {priorities['target_4']}) " \
            f"due to longer downstream critical path"


# ============================================================
# TIER 3: Hard (fail with bugs, require correct algorithms)
# ============================================================

class TestHard:
    """Tests requiring correct graph algorithms to pass."""

    def test_parallel_set_size(self, plan):
        """The maximum parallel set (antichain) should have exactly 3 targets.

        The DAG width (longest antichain) is 3, matching the widest
        topological layer.
        """
        size = plan["analysis"]["parallel_set_size"]
        assert size == 3, \
            f"Parallel set size {size} != expected 3 (maximum antichain)"

    def test_parallel_set_is_antichain(self, plan, graph):
        """Every pair of targets in the parallel set must be truly independent.

        No target in the set should have any path (direct or transitive)
        to any other target in the set.
        """
        pset = plan["analysis"]["parallel_set"]
        for i, a in enumerate(pset):
            for b in pset[i + 1:]:
                reachable_ab = can_reach(graph, a, b)
                reachable_ba = can_reach(graph, b, a)
                assert not reachable_ab and not reachable_ba, \
                    f"Parallel set contains dependent pair: {a} <-> {b}"

    def test_priority_range(self, plan):
        """Priorities should span a meaningful range reflecting path lengths.

        With durations ranging from 800-2500ms and paths of length 6,
        priorities should span thousands, not single digits.
        """
        priorities = plan["priorities"]
        values = list(priorities.values())
        priority_range = max(values) - min(values)
        assert priority_range >= 5000, \
            f"Priority range {priority_range} is too small - " \
            f"suggests out-degree instead of path length"

    def test_critical_path_targets(self, plan):
        """The critical path must contain the correct sequence of targets."""
        cp = plan["analysis"]["critical_path"]
        expected = ["target_1", "target_3", "target_6", "target_9",
                    "target_12", "target_14"]
        assert cp == expected, \
            f"Critical path {cp} != expected {expected}"


# ============================================================
# TIER 4: Integration tests
# ============================================================

class TestIntegration:
    """End-to-end integration tests for plan correctness."""

    def test_plan_respects_dependencies(self, plan):
        """No target should be scheduled in a stage before its dependencies."""
        stages = plan["analysis"]["execution_stages"]
        stage_of = {}
        for idx, stage in enumerate(stages):
            for tid in stage:
                stage_of[tid] = idx

        targets_map = {t["id"]: t for t in plan["targets"]}
        for t in plan["targets"]:
            for dep in t["dependencies"]:
                assert stage_of[dep] < stage_of[t["id"]], \
                    f"{t['id']} in stage {stage_of[t['id']]} but dep " \
                    f"{dep} in stage {stage_of[dep]}"

    def test_total_parallel_stages(self, plan):
        """The DAG should decompose into exactly 6 execution stages."""
        assert plan["analysis"]["total_stages"] == 6, \
            f"Expected 6 stages, got {plan['analysis']['total_stages']}"

    def test_makespan_estimate(self, plan):
        """Makespan should equal sum of max durations per stage.

        With correct parallelism, makespan should be significantly
        less than serial time.
        """
        makespan = plan["analysis"]["makespan_ms"]
        serial = plan["analysis"]["serial_time_ms"]
        assert makespan == 11600, \
            f"Makespan {makespan} != expected 11600ms"
        assert serial > makespan, \
            "Serial time should exceed parallel makespan"

    def test_fingerprint_valid(self, plan):
        """The fingerprint must match expected correct analysis data.

        The fingerprint is computed from the analysis results. If any
        analysis values are wrong, the fingerprint won't match the
        expected value for correct output.
        """
        # Recompute fingerprint from plan data
        fingerprint_data = {
            "independent_pair_count": plan["analysis"]["independent_pair_count"],
            "critical_path": plan["analysis"]["critical_path"],
            "parallel_set": plan["analysis"]["parallel_set"],
            "priorities": plan["priorities"],
            "total_stages": plan["analysis"]["total_stages"],
            "makespan_ms": plan["analysis"]["makespan_ms"]
        }
        raw = json.dumps(fingerprint_data, sort_keys=True)
        computed = hashlib.sha256(raw.encode()).hexdigest()

        # The fingerprint in the plan should be self-consistent
        assert plan["fingerprint"] == computed, \
            "Fingerprint does not match plan content"

        # Additionally, verify the fingerprint matches the known-correct value
        expected_fingerprint = "ffb78646bdd972d8c55e7d58953fed79cb2ce0a849fdad1b7a7ba02bbafb932d"
        assert plan["fingerprint"] == expected_fingerprint, \
            f"Fingerprint {plan['fingerprint']} does not match expected " \
            f"correct value - analysis data is incorrect"
