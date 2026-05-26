"""Main entry point for the Graph Reachability Analysis Engine.

Processes network topologies through:
1. Loading — read directed graph edges from network data files
2. Filtering — select edges with configured active link types
3. Merging — combine edges into a single sorted stream
4. Traversal — compute bounded BFS reachability from each node
5. Scoring — compute weighted path quality scores
6. Output — write reachability and scoring reports
"""
import json
import os
import configparser
from pathlib import Path

from runtime.loader import load_all_networks, merge_edges
from runtime.traversal import ReachabilityEngine
from runtime.scorer import PathScorer


CONFIG_PATH = Path("/app/runtime/config/topology.ini")
OUTPUT_DIR = Path("/app/runtime/output")


def main():
    """Run the full reachability analysis."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)

    raw_types = config.get("links", "active_link_types")
    active_link_types = set(raw_types.split(","))

    networks = load_all_networks()
    edges = merge_edges(networks, active_link_types)

    engine = ReachabilityEngine()
    reachability = engine.compute_all_reachability(edges)

    scorer = PathScorer()

    node_scores = {}
    level_summaries = {}
    for source_node in sorted(reachability.keys()):
        reach_map = reachability[source_node]
        if len(reach_map) > 1:
            scores, level_scores = scorer.compute_path_scores(
                edges, reach_map, source_node
            )
            node_scores[source_node] = scores
            level_summaries[source_node] = level_scores

    # Compute summary stats
    all_nodes = set()
    for edge in edges:
        all_nodes.add(edge["source"])
        all_nodes.add(edge["target"])

    total_reachable_pairs = sum(
        len(r) - 1 for r in reachability.values()
    )

    reachability_output = {
        "total_nodes": len(all_nodes),
        "total_edges": len(edges),
        "total_reachable_pairs": total_reachable_pairs,
        "active_link_types": sorted(active_link_types),
        "reachability_map": {
            node: {
                "reachable_count": len(reach) - 1,
                "max_depth": max(reach.values()) if reach else 0,
                "nodes": {k: v for k, v in sorted(reach.items()) if k != node},
            }
            for node, reach in sorted(reachability.items())
        },
    }

    scoring_output = {
        "node_scores": node_scores,
        "level_summaries": level_summaries,
        "total_scored_sources": len(node_scores),
    }

    with open(OUTPUT_DIR / "reachability.json", "w") as f:
        json.dump(reachability_output, f, indent=2)

    with open(OUTPUT_DIR / "scores.json", "w") as f:
        json.dump(scoring_output, f, indent=2)


if __name__ == "__main__":
    main()
