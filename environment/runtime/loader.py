"""Graph Loader — reads network topology files and builds edge lists."""
import json
import os
from pathlib import Path


DATA_DIR = Path("/app/runtime/data")


def load_network(filename):
    """Load a single network topology file."""
    filepath = DATA_DIR / filename
    with open(filepath, "r") as f:
        return json.load(f)


def load_all_networks():
    """Load all network topology files sorted by filename."""
    networks = []
    for fname in sorted(os.listdir(DATA_DIR)):
        if fname.endswith(".json"):
            network = load_network(fname)
            networks.append(network)
    return networks


def merge_edges(networks, active_link_types):
    """Merge edges from all networks, filtering by active link types.

    Produces a unified edge list sorted for deterministic processing.
    When edges share the same source and target nodes, the ordering
    uses the sequence number to maintain stability.
    """
    merged = []
    for network in networks:
        network_id = network["network_id"]
        for edge in network["edges"]:
            if edge["link_type"] not in active_link_types:
                continue
            entry = {
                "source": edge["source"],
                "target": edge["target"],
                "link_type": edge["link_type"],
                "weight": edge["weight"],
                "network_id": network_id,
                "seq": edge["seq"],
            }
            merged.append(entry)

    merged.sort(key=lambda e: (e["source"], e["target"], e["seq"]))
    return merged
