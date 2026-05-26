"""Main entry point for the Geospatial Event Correlation Engine.

Processes sensor events through:
1. Ingestion — load events from zone data files
2. Filtering — select only events from configured active zones
3. Grid Indexing — assign events to spatial grid cells
4. Correlation — compute temporal correlation scores and build clusters
5. Output — write correlation results to JSON files
"""
import json
import os
import configparser
from pathlib import Path

from runtime.ingest import load_all_zones, merge_events
from runtime.grid import SpatialGrid
from runtime.correlator import EventCorrelator


CONFIG_PATH = Path("/app/runtime/config/cluster.ini")
OUTPUT_DIR = Path("/app/runtime/output")


def main():
    """Run the full correlation process."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)

    cell_size = config.getfloat("grid", "cell_size")
    origin_x = config.getfloat("grid", "origin_x")
    origin_y = config.getfloat("grid", "origin_y")

    raw_zones = config.get("zones", "active_zones")
    active_zones = set(raw_zones.split(","))

    zones = load_all_zones()
    events = merge_events(zones, active_zones)

    grid = SpatialGrid(cell_size, origin_x, origin_y)
    cell_assignments = {}
    for event in events:
        cell = grid.insert(event)
        key = f"{event['zone_id']}_{event['seq']}"
        cell_assignments[key] = list(cell)

    correlator = EventCorrelator()
    window_scores = correlator.compute_window_scores(events, grid)
    clusters = correlator.build_clusters(events, grid)

    index_output = {
        "total_events": len(events),
        "active_zones": sorted(active_zones),
        "cell_count": grid.cell_count(),
        "cell_assignments": cell_assignments,
    }

    correlation_output = {
        "window_scores": window_scores,
        "clusters": clusters,
        "total_clusters": len(clusters),
        "total_correlated_events": sum(c["event_count"] for c in clusters),
    }

    with open(OUTPUT_DIR / "spatial_index.json", "w") as f:
        json.dump(index_output, f, indent=2)

    with open(OUTPUT_DIR / "correlation.json", "w") as f:
        json.dump(correlation_output, f, indent=2)


if __name__ == "__main__":
    main()
