"""
Test suite for task scheduler replay engine.

14 tests in 4 tiers:
- Tier 1 (6 tests): Structural checks - pass with buggy code
- Tier 2 (3 tests): Resource accounting checks - need Bugs 1+2 fixed
- Tier 3 (3 tests): Preemption validation checks - need Bug 3 fixed
- Tier 4 (2 tests): Full integrity checks - need all 4 bugs fixed
"""

import json
import os

# Output file paths
RUNTIME_DIR = "/app/runtime"
HISTORY_PATH = os.path.join(RUNTIME_DIR, "allocation_history.json")
REPORT_PATH = os.path.join(RUNTIME_DIR, "scheduler_report.json")


def load_history():
    """Load allocation_history.json."""
    with open(HISTORY_PATH, "r") as f:
        return json.load(f)


def load_report():
    """Load scheduler_report.json."""
    with open(REPORT_PATH, "r") as f:
        return json.load(f)


# =============================================================================
# TIER 1: Structural tests (pass with buggy code)
# =============================================================================

class TestTier1Structural:
    """Basic structural checks that pass even with buggy scheduler logic."""

    def test_output_files_exist(self):
        """Both output files must exist after replay."""
        assert os.path.exists(HISTORY_PATH), f"Missing: {HISTORY_PATH}"
        assert os.path.exists(REPORT_PATH), f"Missing: {REPORT_PATH}"

    def test_allocation_history_is_dict(self):
        """Allocation history must be a valid JSON object (dict)."""
        history = load_history()
        assert isinstance(history, dict), "Allocation history must be a JSON object"
        assert len(history) > 0, "Allocation history must not be empty"

    def test_report_has_required_fields(self):
        """Report must contain all required fields."""
        report = load_report()
        required_fields = [
            "total_tasks",
            "total_events",
            "preemptions",
            "resource_contentions",
            "pool_capacities",
            "final_pool_available",
            "utilization",
            "preemption_chain",
            "allocation_integrity_hash",
        ]
        for field in required_fields:
            assert field in report, f"Missing required field: {field}"

    def test_total_tasks_count(self):
        """Report must show 12 total tasks processed."""
        report = load_report()
        assert report["total_tasks"] == 12, (
            f"Expected 12 total tasks, got {report['total_tasks']}"
        )

    def test_total_events_count(self):
        """Report must show correct total event count from the log."""
        report = load_report()
        assert report["total_events"] == 45, (
            f"Expected 45 total events, got {report['total_events']}"
        )

    def test_pool_capacities_correct(self):
        """Report must show correct pool capacities."""
        report = load_report()
        expected = {"cpu": 32, "mem": 65536, "gpu": 4, "network": 10000}
        assert report["pool_capacities"] == expected, (
            f"Expected pool capacities {expected}, got {report['pool_capacities']}"
        )


# =============================================================================
# TIER 2: Resource accounting tests (need Bugs 1+2 fixed)
# =============================================================================

class TestTier2ResourceAccounting:
    """Tests that require correct resource pool accounting to pass.

    Bug 1 subtracts resources on preemption instead of adding them back,
    double-deducting from the pool and causing available resources to go
    negative. This cascades into incorrect grants for subsequent tasks.

    Bug 2 records requested amounts instead of granted amounts in the
    active allocations tracker. When tasks with partial allocations
    release, they return more than they held, inflating the pool.

    Together these bugs cause final_pool_available to exceed capacity.
    """

    def test_final_pool_available(self):
        """After all tasks complete, pool must return to full capacity.

        All tasks eventually release or get preempted. The final available
        resources must equal the pool capacities exactly.

        With Bug 1 (preemption subtracts instead of adds) and Bug 2
        (releases use requested instead of granted), the final available
        resources exceed capacity. For example, cpu might show 36 when
        capacity is 32.
        """
        report = load_report()
        expected = {"cpu": 32, "mem": 65536, "gpu": 4, "network": 10000}
        assert report["final_pool_available"] == expected, (
            f"Final pool available should equal pool capacities after all "
            f"tasks complete. Expected {expected}, got "
            f"{report['final_pool_available']}. If values exceed capacity, "
            f"check handle_preemption (should += not -=) and "
            f"allocate_resources (should track granted not requested)."
        )

    def test_allocation_granted_vs_requested(self):
        """Tasks with partial allocation must show granted < requested.

        task_006 requested cpu=4,mem=8192,gpu=1,network=2000 but should
        have received only cpu=2,mem=4096,gpu=0,network=1000 due to pool
        exhaustion after task_005 consumed most resources.

        With Bug 2, the active allocations tracker stores the full requested
        amounts, which means the release phase returns too much to the pool.
        """
        history = load_history()
        task_006 = history["task_006"]
        allocate_event = None
        for event in task_006["events"]:
            if event["type"] == "ALLOCATE":
                allocate_event = event
                break

        assert allocate_event is not None, "task_006 must have an ALLOCATE event"
        assert allocate_event["contention"] is True, (
            "task_006 should show contention=True (partial allocation)"
        )

        granted = allocate_event["resources_granted"]
        requested = allocate_event["resources_requested"]
        assert 0 < granted["cpu"] < requested["cpu"], (
            f"task_006 granted cpu ({granted['cpu']}) should be between 0 and "
            f"requested cpu ({requested['cpu']}). A partial allocation must "
            f"grant a non-zero amount less than the request. If granted is 0, "
            f"the pool went negative (Bug 1: preemption subtracts instead of "
            f"adds back resources)."
        )
        assert 0 < granted["mem"] < requested["mem"], (
            f"task_006 granted mem ({granted['mem']}) should be between 0 and "
            f"requested mem ({requested['mem']}). A partial allocation must "
            f"grant a non-zero amount less than the request."
        )

    def test_post_preemption_availability(self):
        """Resource contentions must reflect actual pool state.

        With correct accounting, only 2 tasks experience resource
        contention (task_006 and task_007, which request more than
        available at their allocation time).

        With Bug 1 causing pools to go negative, many subsequent
        allocations see 0 available resources, inflating the contention
        count far above 2.
        """
        report = load_report()
        assert report["resource_contentions"] == 2, (
            f"Expected exactly 2 resource contentions (task_006 and task_007), "
            f"got {report['resource_contentions']}. If this number is much "
            f"higher, the pool available resources went negative after "
            f"preemption (Bug 1: handle_preemption subtracts instead of adds), "
            f"causing all subsequent allocations to see 0 available."
        )


# =============================================================================
# TIER 3: Preemption validation tests (need Bug 3 fixed)
# =============================================================================

class TestTier3Preemption:
    """Tests that require correct priority comparison for preemption.

    Bug 3 uses an inverted comparison (new_weight <= running_weight) with
    misleading comments about 'inverse priority' and 'lower value = more
    important'. The PRIORITY_LEVELS mapping uses CRITICAL=4, HIGH=3,
    MEDIUM=2, LOW=1, so higher numeric value = higher actual priority.
    The correct check is new_weight > running_weight (strictly greater).

    With Bug 3, the comparison returns True only when new priority is
    lower or equal, meaning no valid preemption (higher preempts lower)
    passes validation. The preemption_chain ends up empty.
    """

    def test_preemption_count(self):
        """Exactly 3 preemptions must be validated in the report.

        The execution log contains 3 preemption events:
        - CRITICAL preempts MEDIUM (task_005 preempts task_003)
        - CRITICAL preempts HIGH (task_008 preempts task_002)
        - HIGH preempts LOW (task_009 preempts task_004)

        With Bug 3 (inverted comparison), can_preempt returns False for
        all valid preemptions (higher priority preempting lower), so
        preemption_count = 0.
        """
        report = load_report()
        assert report["preemptions"] == 3, (
            f"Expected 3 preemptions, got {report['preemptions']}. "
            f"If this is 0, the priority comparison is inverted. "
            f"PRIORITY_LEVELS maps CRITICAL=4, HIGH=3, MEDIUM=2, LOW=1. "
            f"can_preempt should return True when new_weight > running_weight "
            f"(strictly greater), not new_weight <= running_weight."
        )

    def test_preemption_direction(self):
        """Every preemption must have preemptor priority > preempted priority.

        Preemption is only valid when a higher-priority task displaces a
        lower-priority one. The preemption chain must show this direction
        for all 3 entries.
        """
        report = load_report()
        chain = report["preemption_chain"]
        priority_values = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}

        assert len(chain) == 3, (
            f"Expected 3 entries in preemption_chain, got {len(chain)}. "
            f"If empty, the priority resolver is rejecting all valid preemptions."
        )

        for entry in chain:
            preempting_val = priority_values[entry["preempting_priority"]]
            preempted_val = priority_values[entry["preempted_priority"]]
            assert preempting_val > preempted_val, (
                f"Preemption direction violated: {entry['preempting_priority']} "
                f"({preempting_val}) should be > {entry['preempted_priority']} "
                f"({preempted_val}) for {entry['preempting_task']} preempting "
                f"{entry['preempted_task']}."
            )

    def test_preemption_chain_priority_deltas(self):
        """All priority_delta values in the chain must be positive.

        priority_delta = preempting_level - preempted_level. Since preemption
        only occurs when the new task has strictly higher priority, all
        deltas must be > 0.

        Expected deltas: CRITICAL-MEDIUM=2, CRITICAL-HIGH=1, HIGH-LOW=2.
        """
        report = load_report()
        chain = report["preemption_chain"]

        assert len(chain) == 3, (
            f"Expected 3 entries in preemption_chain, got {len(chain)}"
        )

        for entry in chain:
            assert entry["priority_delta"] > 0, (
                f"priority_delta must be positive for valid preemption. "
                f"Got delta={entry['priority_delta']} for "
                f"{entry['preempting_task']} (priority={entry['preempting_priority']}) "
                f"preempting {entry['preempted_task']} "
                f"(priority={entry['preempted_priority']}). "
                f"If delta is 0 or negative, the priority comparison is wrong."
            )


# =============================================================================
# TIER 4: Full integrity tests (need ALL 4 bugs fixed)
# =============================================================================

class TestTier4FullIntegrity:
    """Tests that require all bugs to be fixed simultaneously.

    These tests verify the complete pipeline works end-to-end:
    correct resource accounting, priority-based preemption validation,
    and time-weighted utilization computation.
    """

    def test_utilization_metrics(self):
        """Utilization values must be time-weighted averages below 1.0.

        Correct utilization is computed as:
            integral(usage_over_time) / (capacity * total_time)

        This gives a fraction between 0 and 1 representing the average
        resource usage across the observation window.

        With Bug 4 (peak/capacity instead of time-weighted average), values
        can exceed 1.0 when Bug 1 causes usage to be computed from negative
        available resources. With correct accounting (Bugs 1+2 fixed) but
        Bug 4 still present, peak-based utilization would be close to 1.0
        (since pools get fully utilized at peak). Only time-weighted average
        gives the correct sub-1.0 values.
        """
        report = load_report()
        utilization = report["utilization"]

        for resource, value in utilization.items():
            assert 0.0 < value < 1.0, (
                f"Utilization for {resource} should be between 0 and 1 "
                f"(time-weighted average), got {value}. If value >= 1.0, "
                f"either the resource accounting is wrong (Bugs 1+2) causing "
                f"inflated usage, or utilization is computed as peak/capacity "
                f"(Bug 4) instead of time-weighted average."
            )

        # Check specific expected ranges for each resource
        assert 0.60 < utilization["cpu"] < 0.75, (
            f"CPU utilization should be ~0.70 (time-weighted average), "
            f"got {utilization['cpu']}"
        )
        assert 0.60 < utilization["mem"] < 0.75, (
            f"Memory utilization should be ~0.69 (time-weighted average), "
            f"got {utilization['mem']}"
        )

    def test_allocation_integrity_hash(self):
        """The integrity hash must match the expected value.

        This is a SHA-256 hash (first 16 hex chars) computed over the sorted
        allocation state. It depends on:
        - Correct resource grants (Bug 2 fixed) - granted amounts in events
        - Correct preemption processing (Bug 1 fixed) - released amounts
        - Correct priority validation (Bug 3 fixed) - preemption chain
        - Correct utilization (Bug 4 fixed) - does not affect hash directly
          but allocation events include correct granted amounts

        All bugs affecting allocation_history events must be fixed for the
        hash to match.
        """
        report = load_report()
        expected_hash = "9f70af4929aef2a8"
        assert report["allocation_integrity_hash"] == expected_hash, (
            f"Integrity hash mismatch. Expected '{expected_hash}', got "
            f"'{report['allocation_integrity_hash']}'. This hash is computed "
            f"over the canonical allocation events for each task. It depends "
            f"on correct resource grants (not requested amounts stored in "
            f"active_allocations), correct preemption resource returns, and "
            f"correct priority-based preemption validation. All four bugs in "
            f"resource_allocator.py, priority_resolver.py, and "
            f"utilization_tracker.py must be fixed simultaneously."
        )
