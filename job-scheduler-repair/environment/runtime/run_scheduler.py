"""
Main entry point for the job scheduler system.

Orchestrates the full scheduling flow:
1. Load job data from active worker pool feeds
2. Process jobs through the priority scheduler in batches
3. Build dispatch queue with deterministic ordering
4. Write results to output files
"""
import json
import os

from runtime.loader import PoolLoader
from runtime.scheduler import JobScheduler
from runtime.dispatcher import Dispatcher


CONFIG_PATH = "/app/runtime/config.ini"
OUTPUT_DIR = "/app/runtime/output"


def main():
    """Run the job scheduler system end-to-end."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    loader = PoolLoader(CONFIG_PATH)
    jobs = loader.load_all_jobs()
    batch_size = loader.get_batch_size()

    scheduler = JobScheduler(CONFIG_PATH)
    schedule = scheduler.process_jobs(jobs, batch_size)

    dispatcher = Dispatcher()
    dispatch_queue = dispatcher.build_dispatch_queue(schedule)

    stats = scheduler.get_stats()
    stats["max_retries"] = scheduler.get_max_retries()
    stats["active_pools"] = sorted(loader.get_active_pools())

    summary = {
        "scheduler_stats": stats,
        "dispatch_queue_length": dispatcher.get_queue_length(),
        "total_jobs_loaded": len(jobs),
    }

    with open(os.path.join(OUTPUT_DIR, "dispatch_queue.json"), "w") as f:
        json.dump(dispatch_queue, f, indent=2)

    with open(os.path.join(OUTPUT_DIR, "scheduler_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
