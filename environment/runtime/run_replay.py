#!/usr/bin/env python3
"""Replay recovery runtime orchestrator."""

import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime.db import initialize
from runtime.ingest import ingest_feeds
from runtime.reconstruct import build_windows
from runtime.cursor import create_session, initialize_cursors, simulate_concurrent_replay
from runtime.retention import apply_retention
from runtime.export import export_timeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("replay.orchestrator")


def main():
    logger.info("replay recovery runtime starting")

    initialize()

    event_count = ingest_feeds()
    if event_count == 0:
        logger.error("no events ingested, aborting")
        sys.exit(1)

    window_count = build_windows()
    if window_count == 0:
        logger.error("no replay windows constructed, aborting")
        sys.exit(1)

    session_id = create_session()
    initialize_cursors(session_id)

    # retention pass
    apply_retention()

    # simulate partial recovery scenario with concurrent checkpoint
    simulate_concurrent_replay(session_id)

    # export finalized timeline
    timeline_path, integrity_path = export_timeline()

    logger.info("replay recovery complete")
    logger.info("timeline: %s", timeline_path)
    logger.info("integrity: %s", integrity_path)


if __name__ == "__main__":
    main()
