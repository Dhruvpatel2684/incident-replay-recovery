"""
Test suite for job scheduler system.

Validates the correctness of the job scheduling and dispatch engine
by checking output files produced by the runtime system.

Tests are organized by difficulty:
- Basic tests: file existence, structure, record counts
- Medium tests: specific behaviors requiring 1-2 bug fixes
- Hard tests: behaviors requiring multiple bug fixes together
"""
import json
import os

OUTPUT_DIR = "/app/runtime/output"
DISPATCH_QUEUE_PATH = os.path.join(OUTPUT_DIR, "dispatch_queue.json")
SCHEDULER_SUMMARY_PATH = os.path.join(OUTPUT_DIR, "scheduler_summary.json")


def load_dispatch_queue():
    """Load dispatch queue from output file."""
    with open(DISPATCH_QUEUE_PATH, "r") as f:
        return json.load(f)


def load_scheduler_summary():
    """Load scheduler summary from output file."""
    with open(SCHEDULER_SUMMARY_PATH, "r") as f:
        return json.load(f)


# === EASY TESTS (pass even with buggy code) ===


def test_output_files_exist():
    """Verify that all expected output files are created by the system."""
    assert os.path.isfile(DISPATCH_QUEUE_PATH), (
        f"Missing output file: {DISPATCH_QUEUE_PATH}"
    )
    assert os.path.isfile(SCHEDULER_SUMMARY_PATH), (
        f"Missing output file: {SCHEDULER_SUMMARY_PATH}"
    )


def test_dispatch_queue_structure():
    """Verify dispatch queue has correct top-level structure and field names."""
    queue = load_dispatch_queue()
    assert isinstance(queue, list), "dispatch_queue.json must be a JSON array"
    assert len(queue) > 0, "Dispatch queue must not be empty"
    for entry in queue:
        assert "job_id" in entry, "Each entry must have 'job_id' field"
        assert "pool_id" in entry, "Each entry must have 'pool_id' field"
        assert "priority" in entry, "Each entry must have 'priority' field"
        assert "priority_rank" in entry, "Each entry must have 'priority_rank' field"
        assert "submit_time" in entry, "Each entry must have 'submit_time' field"
        assert "wait_ms" in entry, "Each entry must have 'wait_ms' field"
        assert "retries_allowed" in entry, "Each entry must have 'retries_allowed' field"
        assert "overdue" in entry, "Each entry must have 'overdue' field"
        assert "dispatch_position" in entry, "Each entry must have 'dispatch_position' field"


def test_scheduler_summary_structure():
    """Verify scheduler summary has correct structure with required fields."""
    summary = load_scheduler_summary()
    assert "scheduler_stats" in summary, "Summary must have 'scheduler_stats' field"
    assert "dispatch_queue_length" in summary, "Summary must have 'dispatch_queue_length' field"
    assert "total_jobs_loaded" in summary, "Summary must have 'total_jobs_loaded' field"
    stats = summary["scheduler_stats"]
    assert "total_scheduled" in stats, "scheduler_stats must have 'total_scheduled' field"
    assert "batch_count" in stats, "scheduler_stats must have 'batch_count' field"
    assert "max_wait_ms" in stats, "scheduler_stats must have 'max_wait_ms' field"
    assert "total_retries_allocated" in stats, "scheduler_stats must have 'total_retries_allocated' field"
    assert "overdue_count" in stats, "scheduler_stats must have 'overdue_count' field"
    assert "max_retries" in stats, "scheduler_stats must have 'max_retries' field"
    assert "active_pools" in stats, "scheduler_stats must have 'active_pools' field"


def test_dispatch_positions_sequential():
    """Verify dispatch positions are sequential integers starting from zero."""
    queue = load_dispatch_queue()
    positions = [entry["dispatch_position"] for entry in queue]
    expected = list(range(len(queue)))
    assert positions == expected, (
        f"Dispatch positions must be sequential 0..{len(queue)-1}"
    )


# === MEDIUM TESTS (require 1-2 bug fixes) ===


def test_gpu_pool_included():
    """Verify that jobs from the 'gpu' pool are included in the dispatch queue.

    The system should load data from all active pools including 'gpu'.
    If gpu pool jobs are missing, check pool filtering logic in
    /app/runtime/loader.py and the active_pools config value.
    """
    summary = load_scheduler_summary()
    active = summary["scheduler_stats"]["active_pools"]
    assert "gpu" in active, (
        "Pool 'gpu' must be in active_pools. "
        "Check how active_pools config value is parsed in /app/runtime/loader.py"
    )
    total = summary["total_jobs_loaded"]
    assert total == 55, (
        f"Expected 55 total jobs (18 compute + 18 storage + 19 gpu), got {total}. "
        "GPU pool jobs may be missing due to config parsing."
    )


def test_max_retries_correct():
    """Verify the scheduler uses correct max_retries from deadline config.

    The scheduler should use deadline-specific retry parameters.
    The value should be 2 (from [scheduling.deadlines] section).
    """
    summary = load_scheduler_summary()
    max_retries = summary["scheduler_stats"]["max_retries"]
    assert max_retries == 2, (
        f"Expected max_retries=2 (from [scheduling.deadlines] section), "
        f"got {max_retries}. Check which config section is read in "
        "/app/runtime/scheduler.py"
    )


def test_max_wait_ms_valid():
    """Verify max_wait_ms represents maximum across batches, not a sum.

    The max_wait_ms statistic should be the single highest wait time
    observed in any batch, not an accumulated total across batches.
    """
    summary = load_scheduler_summary()
    max_wait = summary["scheduler_stats"]["max_wait_ms"]
    assert max_wait <= 12000, (
        f"max_wait_ms={max_wait} is too large. It should be the maximum "
        "wait time from a single batch, not a sum across batches. "
        "Check max_wait_ms accumulation logic in /app/runtime/scheduler.py"
    )
    assert max_wait > 0, (
        f"max_wait_ms={max_wait} must be positive"
    )


# === HARD TESTS (require 3-4 bug fixes together) ===


def test_dispatch_order_deterministic():
    """Verify dispatch queue is ordered by (priority_rank, submit_time, pool_id, job_id).

    When multiple jobs have the same priority and submit_time from
    different pools, the sort must use pool_id as tertiary key and
    job_id as quaternary key for deterministic ordering. Check sort
    logic in /app/runtime/dispatcher.py build_dispatch_queue method.
    """
    queue = load_dispatch_queue()
    for i in range(len(queue) - 1):
        curr = queue[i]
        nxt = queue[i + 1]
        key_curr = (curr["priority_rank"], curr["submit_time"], curr["pool_id"], curr["job_id"])
        key_nxt = (nxt["priority_rank"], nxt["submit_time"], nxt["pool_id"], nxt["job_id"])
        assert key_curr <= key_nxt, (
            f"Dispatch queue not in correct order at position {i}: "
            f"{key_curr} should come before {key_nxt}. "
            "Queue must be sorted by (priority_rank, submit_time, pool_id, job_id). "
            "Check sort key in /app/runtime/dispatcher.py"
        )


def test_dispatch_includes_all_pools():
    """Verify dispatch queue contains jobs from all active pools including gpu.

    Jobs from compute, storage, and gpu pools should all be present.
    The gpu pool has 19 jobs that must be included in the dispatch.
    """
    queue = load_dispatch_queue()
    pools_in_queue = set(entry["pool_id"] for entry in queue)
    assert "gpu" in pools_in_queue, (
        "Dispatch queue must include jobs from 'gpu' pool. "
        "Check pool loading in /app/runtime/loader.py"
    )
    assert "compute" in pools_in_queue, (
        "Dispatch queue must include jobs from 'compute' pool"
    )
    assert "storage" in pools_in_queue, (
        "Dispatch queue must include jobs from 'storage' pool"
    )
    assert len(queue) == 55, (
        f"Expected 55 jobs in dispatch queue, got {len(queue)}"
    )


def test_complete_system_accuracy():
    """Verify full system produces correct results with all fixes applied.

    This test checks:
    - Correct total job count (55 from all pools)
    - Correct max_retries (2 from deadlines config)
    - Valid max_wait_ms (max, not sum)
    - Total retries allocated matches job_count * max_retries
    """
    summary = load_scheduler_summary()
    queue = load_dispatch_queue()

    assert summary["total_jobs_loaded"] == 55, (
        f"Expected 55 jobs loaded, got {summary['total_jobs_loaded']}"
    )

    stats = summary["scheduler_stats"]
    assert stats["max_retries"] == 2, (
        f"Expected max_retries=2, got {stats['max_retries']}"
    )

    assert stats["max_wait_ms"] <= 12000, (
        f"max_wait_ms={stats['max_wait_ms']} should be <= 12000 "
        "(single batch max, not accumulated sum)"
    )

    expected_total_retries = 55 * 2
    assert stats["total_retries_allocated"] == expected_total_retries, (
        f"Expected total_retries_allocated={expected_total_retries} "
        f"(55 jobs * 2 retries), got {stats['total_retries_allocated']}"
    )

    assert summary["dispatch_queue_length"] == 55, (
        f"Expected dispatch_queue_length=55, got {summary['dispatch_queue_length']}"
    )

    gpu_jobs = [e for e in queue if e["pool_id"] == "gpu"]
    assert len(gpu_jobs) == 19, (
        f"Expected 19 gpu jobs in queue, got {len(gpu_jobs)}"
    )
