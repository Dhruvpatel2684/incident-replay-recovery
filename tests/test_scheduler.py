"""Tests for the priority task scheduler execution plan."""

import json
import os
import sys

import pytest

RUNTIME_DIR = "/app/runtime"
OUTPUT_DIR = os.path.join(RUNTIME_DIR, "output")
PLAN_PATH = os.path.join(OUTPUT_DIR, "execution_plan.json")
SUMMARY_PATH = os.path.join(OUTPUT_DIR, "schedule_summary.json")


def load_plan():
    """Load the execution plan output."""
    with open(PLAN_PATH) as f:
        return json.load(f)


def load_summary():
    """Load the schedule summary output."""
    with open(SUMMARY_PATH) as f:
        return json.load(f)


class TestOutputExists:
    """Basic output file existence checks."""

    def test_execution_plan_exists(self):
        """The execution_plan.json output file must exist."""
        assert os.path.exists(PLAN_PATH), (
            f"execution_plan.json not found at {PLAN_PATH}"
        )

    def test_schedule_summary_exists(self):
        """The schedule_summary.json output file must exist."""
        assert os.path.exists(SUMMARY_PATH), (
            f"schedule_summary.json not found at {SUMMARY_PATH}"
        )

    def test_summary_status_completed(self):
        """Summary status should be 'completed'."""
        summary = load_summary()
        assert summary["status"] == "completed", (
            f"Summary status is '{summary['status']}', expected 'completed'"
        )


class TestJobFiltering:
    """Tests for correct job group filtering."""

    def test_all_groups_included(self):
        """All four groups (batch, realtime, analytics, maintenance) should be processed.

        The config defines allowed_groups with all four groups. Ensure the
        scheduler correctly parses all group names from the comma-separated list.
        """
        summary = load_summary()
        expected_groups = ["analytics", "batch", "maintenance", "realtime"]
        assert sorted(summary["groups_processed"]) == expected_groups, (
            f"Groups mismatch. Got: {sorted(summary['groups_processed'])}, "
            f"Expected: {expected_groups}. "
            f"Check group name parsing in /app/runtime/scheduler.py get_allowed_groups()"
        )

    def test_total_jobs_scheduled(self):
        """All 30 jobs from all queues should be scheduled (none filtered out).

        Since all groups are in the allowed list, no jobs should be excluded.
        """
        plan = load_plan()
        assert plan["total_jobs_scheduled"] == 30, (
            f"Expected 30 jobs scheduled, got {plan['total_jobs_scheduled']}. "
            f"Jobs filtered out: {plan['jobs_filtered_out']}. "
            f"Check that group names are parsed correctly (strip whitespace)."
        )

    def test_no_jobs_filtered(self):
        """Zero jobs should be filtered out."""
        plan = load_plan()
        assert plan["jobs_filtered_out"] == 0, (
            f"Expected 0 jobs filtered, got {plan['jobs_filtered_out']}. "
            f"All groups should be in allowed_groups."
        )

    def test_analytics_jobs_present(self):
        """Analytics queue jobs must appear in the schedule."""
        plan = load_plan()
        analytics_jobs = [e for e in plan["schedule"] if e["queue"] == "analytics"]
        assert len(analytics_jobs) == 10, (
            f"Expected 10 analytics jobs, found {len(analytics_jobs)}. "
            f"Check allowed_groups parsing for whitespace issues."
        )


class TestBatchWindow:
    """Tests for correct batch window configuration."""

    def test_batch_window_value(self):
        """Batch window should be 15 minutes (from scheduler.execution section).

        The [scheduler.execution] section defines the precise batch_window,
        not the top-level [scheduler] section which has a different default.
        """
        plan = load_plan()
        assert plan["batch_window_minutes"] == 15, (
            f"Expected batch_window 15, got {plan['batch_window_minutes']}. "
            f"Read from [scheduler.execution] section, not [scheduler]."
        )

    def test_window_count(self):
        """With 15-minute windows over a 90-minute span, expect 7 windows."""
        plan = load_plan()
        assert len(plan["time_windows"]) == 7, (
            f"Expected 7 time windows, got {len(plan['time_windows'])}. "
            f"Verify batch_window is read from the correct config section."
        )

    def test_first_window_jobs(self):
        """First window (0-15 min) should contain jobs scheduled at 02:00."""
        plan = load_plan()
        w0 = plan["time_windows"].get("window_0", {})
        assert w0.get("job_count", 0) == 5, (
            f"Expected 5 jobs in window_0, got {w0.get('job_count', 0)}"
        )


class TestWindowStats:
    """Tests for window load statistics computation."""

    def test_window_load_uses_last_value(self):
        """Window load_by_priority should use last-write-wins per snapshot.

        The load calculation should NOT accumulate durations across jobs.
        In window_4 (60-75 min offset), the 'high' priority jobs are
        B007 (200s) and R008 (25s). With accumulation (bug), high=225.
        With last-write-wins (correct), high=25 (R008 is the last snapshot).
        """
        plan = load_plan()
        w4 = plan["time_windows"].get("window_4", {})
        load = w4.get("load_by_priority", {})
        # In window_4, high-priority jobs iterate as B007(200s) then R008(25s)
        # last-write-wins: load["high"] = 25
        assert load.get("high") == 25, (
            f"Window 4 high load should be 25 (last-write-wins from R008), "
            f"got {load.get('high')}. "
            f"Check compute_window_stats — should use assignment not accumulation."
        )

    def test_window_critical_load(self):
        """Window_0 critical load should be the last critical job's duration."""
        plan = load_plan()
        w0 = plan["time_windows"].get("window_0", {})
        load = w0.get("load_by_priority", {})
        # In window_0, critical jobs: R001(10s), only one critical
        assert load.get("critical") == 10, (
            f"Window 0 critical load should be 10, got {load.get('critical')}"
        )


class TestSortOrder:
    """Tests for correct job priority sorting."""

    def test_sort_at_same_timestamp(self):
        """Jobs at same timestamp should sort by priority then priority_class then seq.

        At 2024-01-15T02:15:00, multiple jobs from different queues share the
        same timestamp. They should be ordered by:
        1. Priority value (descending - critical first)
        2. Priority class name (alphabetical tiebreaker)
        3. Sequence number

        The priority_class field provides deterministic ordering when numeric
        priority values are identical.
        """
        plan = load_plan()
        schedule = plan["schedule"]

        # Find jobs at 02:15:00
        jobs_at_0215 = [e for e in schedule if e["scheduled_at"] == "2024-01-15T02:15:00"]

        # Should be ordered: critical first, then high, then medium, then low
        # Within same priority: alphabetical by priority_class (they're same), then by seq
        assert len(jobs_at_0215) == 6, (
            f"Expected 6 jobs at 02:15, found {len(jobs_at_0215)}"
        )

        # First should be critical (R003)
        assert jobs_at_0215[0]["job_id"] == "R003", (
            f"First job at 02:15 should be R003 (critical), got {jobs_at_0215[0]['job_id']}. "
            f"Check sort key includes priority_class for deterministic ordering "
            f"of same-priority jobs from different queues."
        )

    def test_sort_high_priority_tiebreaker(self):
        """When two 'high' priority jobs share a timestamp, sort by priority_class then seq.

        At 2024-01-15T02:15:00, high-priority jobs are A003 and B004.
        With priority_class as tiebreaker: 'high' == 'high', so seq breaks tie.
        But they're from different queues, so queue matters via priority_class sort.
        """
        plan = load_plan()
        schedule = plan["schedule"]
        jobs_at_0215 = [e for e in schedule if e["scheduled_at"] == "2024-01-15T02:15:00"]
        high_jobs = [j for j in jobs_at_0215 if j["priority_class"] == "high"]

        assert len(high_jobs) == 2, f"Expected 2 high jobs at 02:15, got {len(high_jobs)}"
        # A003 (seq=3) should come before B004 (seq=4) since both are "high" class
        assert high_jobs[0]["job_id"] == "A003", (
            f"First high-priority job at 02:15 should be A003 (seq=3), "
            f"got {high_jobs[0]['job_id']}. "
            f"Ensure sort uses priority_class as tiebreaker for same-priority jobs."
        )

    def test_overall_schedule_order(self):
        """Schedule entries should be in correct chronological-priority order."""
        plan = load_plan()
        schedule = plan["schedule"]

        # Verify first job is one of the 02:00 critical jobs
        assert schedule[0]["scheduled_at"] == "2024-01-15T02:00:00", (
            f"First scheduled job should be at 02:00, got {schedule[0]['scheduled_at']}"
        )
        assert schedule[0]["priority_class"] == "critical", (
            f"First job should be critical priority, got {schedule[0]['priority_class']}"
        )
