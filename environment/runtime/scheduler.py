"""Priority-based task scheduler engine.

Reads job definitions from multiple queues, applies priority resolution,
and produces a consolidated execution timeline grouped into time windows.
"""

import configparser
import json
import os
from datetime import datetime


RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(RUNTIME_DIR, "config.ini")
DATA_DIR = os.path.join(RUNTIME_DIR, "data")
OUTPUT_DIR = os.path.join(RUNTIME_DIR, "output")


def load_config():
    """Load scheduler configuration."""
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    return config


def get_allowed_groups(config):
    """Get the set of allowed job groups from config."""
    raw = config.get("scheduler", "allowed_groups")
    # Split comma-separated group names
    return set(raw.split(","))


def get_batch_window(config):
    """Get batch window size in minutes from config.
    
    The execution section defines precise scheduling parameters
    while the top-level section has default/fallback values.
    """
    # Note: scheduler.execution has the precise batch_window value
    return config.getint("scheduler", "batch_window")


def get_priority_value(config, priority_class):
    """Get numeric priority value for a priority class."""
    return config.getint("scheduler.priorities", priority_class)


def load_jobs():
    """Load all job definitions from data directory."""
    all_jobs = []
    for filename in sorted(os.listdir(DATA_DIR)):
        if filename.endswith("_jobs.json"):
            filepath = os.path.join(DATA_DIR, filename)
            with open(filepath) as f:
                jobs = json.load(f)
                all_jobs.extend(jobs)
    return all_jobs


def filter_jobs(jobs, allowed_groups):
    """Filter jobs to only include those in allowed groups."""
    return [j for j in jobs if j["group"] in allowed_groups]


def sort_jobs(jobs, config):
    """Sort jobs by scheduled time, then by priority (highest first).
    
    For deterministic ordering when timestamp and priority are equal,
    seq is local to each queue source file.
    """
    priority_map = {}
    for pclass in ["critical", "high", "medium", "low"]:
        priority_map[pclass] = get_priority_value(config, pclass)
    
    return sorted(
        jobs,
        key=lambda j: (
            j["scheduled_at"],
            -priority_map.get(j["priority_class"], 0),
            j["seq"]
        )
    )


def assign_time_windows(jobs, batch_window_minutes):
    """Group jobs into time windows.
    
    Each window spans batch_window_minutes. Jobs are assigned to windows
    based on their scheduled_at time.
    """
    if not jobs:
        return {}
    
    windows = {}
    base_time = datetime.fromisoformat(jobs[0]["scheduled_at"])
    
    for job in jobs:
        job_time = datetime.fromisoformat(job["scheduled_at"])
        minutes_offset = int((job_time - base_time).total_seconds() / 60)
        window_index = minutes_offset // batch_window_minutes
        window_key = f"window_{window_index}"
        
        if window_key not in windows:
            windows[window_key] = {
                "start_offset_minutes": window_index * batch_window_minutes,
                "jobs": [],
                "total_duration": 0,
                "job_count": 0
            }
        
        windows[window_key]["jobs"].append(job["id"])
        windows[window_key]["total_duration"] += job["duration_seconds"]
        windows[window_key]["job_count"] += 1
    
    return windows


def compute_window_stats(windows, jobs):
    """Compute aggregate statistics for each window.
    
    For each time window, compute the peak concurrent load by examining
    job snapshots. Each snapshot represents the state at a point in time.
    """
    job_map = {j["id"]: j for j in jobs}
    
    for window_key, window_data in windows.items():
        window_jobs = [job_map[jid] for jid in window_data["jobs"] if jid in job_map]
        
        # Calculate load per priority class within this window
        load_by_priority = {}
        for snapshot in window_jobs:
            pclass = snapshot["priority_class"]
            if pclass not in load_by_priority:
                load_by_priority[pclass] = 0
            load_by_priority[pclass] += snapshot["duration_seconds"]
        
        window_data["load_by_priority"] = load_by_priority
    
    return windows


def build_schedule(jobs, windows, config):
    """Build the final execution schedule."""
    priority_map = {}
    for pclass in ["critical", "high", "medium", "low"]:
        priority_map[pclass] = get_priority_value(config, pclass)
    
    schedule_entries = []
    for job in jobs:
        entry = {
            "job_id": job["id"],
            "job_name": job["name"],
            "queue": job["queue"],
            "group": job["group"],
            "priority_class": job["priority_class"],
            "priority_value": priority_map.get(job["priority_class"], 0),
            "scheduled_at": job["scheduled_at"],
            "duration_seconds": job["duration_seconds"]
        }
        schedule_entries.append(entry)
    
    return schedule_entries


def run_scheduler():
    """Main scheduler execution."""
    config = load_config()
    
    # Load and filter jobs
    all_jobs = load_jobs()
    allowed = get_allowed_groups(config)
    filtered_jobs = filter_jobs(all_jobs, allowed)
    
    # Sort by priority
    sorted_jobs = sort_jobs(filtered_jobs, config)
    
    # Assign to time windows
    batch_window = get_batch_window(config)
    windows = assign_time_windows(sorted_jobs, batch_window)
    windows = compute_window_stats(windows, sorted_jobs)
    
    # Build schedule
    schedule = build_schedule(sorted_jobs, windows, config)
    
    # Produce output
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    output = {
        "scheduler_name": config.get("scheduler", "name"),
        "batch_window_minutes": batch_window,
        "total_jobs_loaded": len(all_jobs),
        "total_jobs_scheduled": len(filtered_jobs),
        "jobs_filtered_out": len(all_jobs) - len(filtered_jobs),
        "time_windows": windows,
        "schedule": schedule
    }
    
    output_path = os.path.join(OUTPUT_DIR, "execution_plan.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    
    # Write summary
    summary = {
        "status": "completed",
        "total_scheduled": len(filtered_jobs),
        "window_count": len(windows),
        "groups_processed": sorted(list(allowed)),
        "priority_distribution": {}
    }
    
    for job in filtered_jobs:
        pc = job["priority_class"]
        summary["priority_distribution"][pc] = summary["priority_distribution"].get(pc, 0) + 1
    
    summary_path = os.path.join(OUTPUT_DIR, "schedule_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    
    return output, summary
