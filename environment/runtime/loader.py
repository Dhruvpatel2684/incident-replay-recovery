"""
Loads manifest declarations and live node state from JSON files.
"""

import json
import os
import logging

logger = logging.getLogger("drift.loader")


def load_manifests(manifest_dir):
    """Load all manifest JSON files from the manifests directory."""
    nodes = []
    for fname in sorted(os.listdir(manifest_dir)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(manifest_dir, fname)
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, list):
            nodes.extend(data)
        else:
            nodes.append(data)
    logger.info(f"loaded {len(nodes)} manifest declarations from {manifest_dir}")
    return nodes


def load_live_state(state_dir):
    """Load all live state JSON files."""
    nodes = []
    for fname in sorted(os.listdir(state_dir)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(state_dir, fname)
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, list):
            nodes.extend(data)
        else:
            nodes.append(data)
    logger.info(f"loaded {len(nodes)} live node states from {state_dir}")
    return nodes
