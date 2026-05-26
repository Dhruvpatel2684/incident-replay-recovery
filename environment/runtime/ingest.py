"""Event Ingestion — loads sensor events from zone data files."""
import json
import os
from pathlib import Path


DATA_DIR = Path("/app/runtime/data")


def load_zone(filename):
    """Load a single zone data file."""
    filepath = DATA_DIR / filename
    with open(filepath, "r") as f:
        return json.load(f)


def load_all_zones():
    """Load all zone data files sorted by filename."""
    zones = []
    for fname in sorted(os.listdir(DATA_DIR)):
        if fname.endswith(".json"):
            zone_data = load_zone(fname)
            zones.append(zone_data)
    return zones


def merge_events(zones, active_zones):
    """Merge events from active zones into a single sorted stream.

    Events are sorted by timestamp for temporal processing.
    When events share a timestamp, ordering uses sequence number
    to maintain a stable sort within the merged stream.
    """
    merged = []
    for zone in zones:
        zone_id = zone["zone_id"]
        if zone_id not in active_zones:
            continue
        for event in zone["events"]:
            entry = {
                "zone_id": zone_id,
                "seq": event["seq"],
                "timestamp": event["timestamp"],
                "x": event["x"],
                "y": event["y"],
                "reading": event["reading"],
            }
            merged.append(entry)

    merged.sort(key=lambda e: (e["timestamp"], e["seq"]))
    return merged
