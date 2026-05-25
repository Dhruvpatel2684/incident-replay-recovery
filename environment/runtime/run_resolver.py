#!/usr/bin/env python3
"""
DNS Zone Resolver — main orchestration entrypoint.
"""

import configparser
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parser import load_zones
from cache import RecordCache
from resolver import resolve_query
from exporter import export_results

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
logger = logging.getLogger("dns.orchestrator")


def main():
    runtime_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(runtime_dir, "config", "resolver.ini")

    config = configparser.ConfigParser()
    config.read(config_path)

    logger.info("dns zone resolver starting")

    # Load zones
    zone_records, zone_metadata = load_zones(config)
    logger.info(f"loaded {len(zone_records)} zones")

    # Initialize cache
    cache_enabled = config.getboolean("cache", "enabled", fallback=True)
    max_entries = config.getint("cache", "max_entries", fallback=1000)
    cache = RecordCache(enabled=cache_enabled, max_entries=max_entries)

    # Load queries
    queries_path = os.path.join(runtime_dir, "queries", "batch_queries.json")
    with open(queries_path) as f:
        queries = json.load(f)
    logger.info(f"loaded {len(queries)} queries")

    # Resolve
    max_cname_depth = config.getint("resolver", "max_cname_depth", fallback=5)
    results = []
    for query in queries:
        result = resolve_query(query["name"], query["type"], zone_records, cache, max_cname_depth)
        results.append(result)

    logger.info(f"resolved {len(results)} queries")

    # Export
    export_results(results, zone_metadata, config)
    logger.info("resolution complete")


if __name__ == "__main__":
    main()
