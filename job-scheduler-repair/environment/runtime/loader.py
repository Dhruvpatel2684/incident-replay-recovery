"""
Job loader module for the scheduler system.

Loads job definitions from worker pool feed files and filters
based on active pool configuration. Each pool feed contains
jobs assigned to that specific worker pool.

Note: deadline-specific scheduling parameters are defined in
the [scheduling.deadlines] section of the configuration file.
"""
import json
import os
import configparser


class PoolLoader:
    """Loads and filters job data from worker pool feed files."""

    def __init__(self, config_path):
        self._config = configparser.ConfigParser()
        self._config.read(config_path)
        self._data_dir = self._config.get("pools", "data_directory")
        raw_pools = self._config.get("pools", "active_pools")
        self._active_pools = set(raw_pools.split(","))

    def get_active_pools(self):
        """Return set of active pool identifiers."""
        return self._active_pools

    def load_all_jobs(self):
        """Load jobs from all active pool feeds.

        Returns list of job dicts. Only includes jobs whose pool_id
        is in the active set.
        """
        all_jobs = []
        feed_files = sorted(os.listdir(self._data_dir))
        for fname in feed_files:
            if not fname.endswith("_pool.json"):
                continue
            pool_id = fname.replace("_pool.json", "")
            if pool_id not in self._active_pools:
                continue
            fpath = os.path.join(self._data_dir, fname)
            with open(fpath, "r") as f:
                jobs = json.load(f)
            for job in jobs:
                job["_source_file"] = fname
            all_jobs.extend(jobs)
        return all_jobs

    def get_batch_size(self):
        """Return configured batch size for processing."""
        return self._config.getint("scheduling", "batch_size")
