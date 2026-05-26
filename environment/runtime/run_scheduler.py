"""Entry point for the task scheduler system."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scheduler import run_scheduler


def main():
    """Run the scheduler and print summary."""
    output, summary = run_scheduler()
    
    print(f"Scheduler: {output['scheduler_name']}")
    print(f"Batch window: {output['batch_window_minutes']} minutes")
    print(f"Jobs loaded: {output['total_jobs_loaded']}")
    print(f"Jobs scheduled: {output['total_jobs_scheduled']}")
    print(f"Jobs filtered out: {output['jobs_filtered_out']}")
    print(f"Time windows: {summary['window_count']}")
    print(f"Groups: {summary['groups_processed']}")
    print(f"Priority distribution: {summary['priority_distribution']}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
