#!/usr/bin/env python3
"""
Oracle repair script for corrupted register allocator data.

This script repairs four types of corruption in the interference graph
and live range data:

1. Phantom nodes: Nodes in the graph with no corresponding live range data
2. Shifted live ranges: Ranges whose end_instruction exceeds max_instruction_index
3. Duplicate edges: Edges that appear more than once in the adjacency list
4. Missing edges: Interference edges that should exist based on overlapping live ranges

The repair process:
- Load config to get max_instruction_index
- Load and fix live ranges (shift correction)
- Load graph, remove phantoms, deduplicate
- Recompute edges from corrected live ranges
- Write repaired data back
"""

import json
import configparser
import os
import sys


def load_config(config_path):
    """Load configuration."""
    config = configparser.ConfigParser()
    config.read(config_path)
    return config


def repair_live_ranges(ranges_path, max_instruction_idx):
    """
    Fix shifted live ranges.
    
    Corruption: Some ranges have end_instruction exceeding max_instruction_index.
    These were shifted by +2 during a faulty serialization pass.
    Fix: Subtract 2 from any end_instruction > max_instruction_index.
    """
    with open(ranges_path, 'r') as f:
        data = json.load(f)
    
    fixed_count = 0
    for entry in data['ranges']:
        if entry['end_instruction'] > max_instruction_idx:
            entry['end_instruction'] -= 2
            fixed_count += 1
    
    print(f"[REPAIR] Fixed {fixed_count} shifted live ranges")
    return data


def repair_interference_graph(graph_path, live_ranges_data):
    """
    Fix the interference graph:
    1. Remove phantom nodes (nodes with no live range)
    2. Deduplicate edges
    3. Recompute edges based on corrected live ranges
    """
    with open(graph_path, 'r') as f:
        graph_data = json.load(f)
    
    # Build set of valid virtual registers from live ranges
    valid_vregs = set(entry['vreg'] for entry in live_ranges_data['ranges'])
    
    # Step 1: Remove phantom nodes
    original_nodes = graph_data['nodes']
    phantom_nodes = [n for n in original_nodes if n not in valid_vregs]
    cleaned_nodes = [n for n in original_nodes if n in valid_vregs]
    print(f"[REPAIR] Removed {len(phantom_nodes)} phantom nodes: {phantom_nodes}")
    
    # Step 2: Build live range lookup for overlap computation
    ranges_by_vreg = {}
    for entry in live_ranges_data['ranges']:
        ranges_by_vreg[entry['vreg']] = entry
    
    # Step 3: Recompute all edges from live range overlaps
    # Two registers interfere if their live ranges overlap
    recomputed_edges = set()
    vreg_list = sorted(cleaned_nodes)
    
    for i in range(len(vreg_list)):
        for j in range(i + 1, len(vreg_list)):
            vi = vreg_list[i]
            vj = vreg_list[j]
            ri = ranges_by_vreg[vi]
            rj = ranges_by_vreg[vj]
            
            # Overlap check: start_i <= end_j AND start_j <= end_i
            if (ri['start_instruction'] <= rj['end_instruction'] and
                rj['start_instruction'] <= ri['end_instruction']):
                recomputed_edges.add((vi, vj))
    
    # Count changes vs original (for diagnostics)
    original_edges_set = set()
    for e in graph_data['edges']:
        edge = tuple(sorted([e['from'], e['to']]))
        # Skip edges involving phantom nodes
        if edge[0] in valid_vregs and edge[1] in valid_vregs:
            original_edges_set.add(edge)
    
    duplicates_removed = len(graph_data['edges']) - len(original_edges_set) - len(
        [e for e in graph_data['edges'] 
         if e['from'] not in valid_vregs or e['to'] not in valid_vregs]
    )
    edges_added = recomputed_edges - original_edges_set
    edges_removed = original_edges_set - recomputed_edges
    
    print(f"[REPAIR] Deduplicated edges (removed ~{max(0, duplicates_removed)} duplicates)")
    print(f"[REPAIR] Added {len(edges_added)} missing edges: {sorted(edges_added)}")
    print(f"[REPAIR] Removed {len(edges_removed)} spurious edges")
    print(f"[REPAIR] Final edge count: {len(recomputed_edges)}")
    
    # Build repaired graph
    repaired_edges = [{"from": e[0], "to": e[1]} for e in sorted(recomputed_edges)]
    
    graph_data['nodes'] = cleaned_nodes
    graph_data['edges'] = repaired_edges
    
    return graph_data


def main():
    config_path = '/app/runtime/config.ini'
    data_dir = '/app/runtime/data'
    
    graph_path = os.path.join(data_dir, 'interference_graph.json')
    ranges_path = os.path.join(data_dir, 'live_ranges.json')
    
    print("=" * 60)
    print("Data Repair Script - Register Allocator")
    print("=" * 60)
    
    # Load config
    config = load_config(config_path)
    max_instruction_idx = int(config.get('program', 'max_instruction_index'))
    print(f"Max instruction index: {max_instruction_idx}")
    print()
    
    # Step 1: Repair live ranges (fix shifted ends)
    print("--- Phase 1: Repairing live ranges ---")
    repaired_ranges = repair_live_ranges(ranges_path, max_instruction_idx)
    
    # Write repaired ranges back
    with open(ranges_path, 'w') as f:
        json.dump(repaired_ranges, f, indent=2)
    print(f"Written repaired ranges to {ranges_path}")
    print()
    
    # Step 2: Repair interference graph
    print("--- Phase 2: Repairing interference graph ---")
    repaired_graph = repair_interference_graph(graph_path, repaired_ranges)
    
    # Write repaired graph back
    with open(graph_path, 'w') as f:
        json.dump(repaired_graph, f, indent=2)
    print(f"Written repaired graph to {graph_path}")
    print()
    
    print("=" * 60)
    print("Repair complete. Data is ready for allocation.")
    print("=" * 60)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
