"""
Register Allocator Engine - Graph Coloring Based

This module implements a register allocator using the DSatur (Degree of Saturation)
graph coloring algorithm. It reads an interference graph and live range data,
then produces register assignments and spill decisions.

The algorithm:
1. Build adjacency structure from interference graph
2. Validate all nodes have corresponding live range data
3. Compute spill costs based on usage patterns and loop depth
4. Apply DSatur coloring with configurable tie-breaking
5. Spill registers that cannot be colored within available physical registers
6. Output assignments, spill decisions, and diagnostics

THIS ENGINE IS CORRECT. If output is wrong, the input data is corrupt.
"""

import json
import configparser
import os
import sys
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class LiveRange:
    """Represents the live range of a virtual register."""
    vreg: str
    start_instruction: int
    end_instruction: int
    usage_count: int
    loop_depth: int
    def_points: List[int] = field(default_factory=list)
    use_points: List[int] = field(default_factory=list)

    def overlaps(self, other: 'LiveRange') -> bool:
        """Check if this live range overlaps with another."""
        return (self.start_instruction <= other.end_instruction and
                other.start_instruction <= self.end_instruction)

    @property
    def length(self) -> int:
        return self.end_instruction - self.start_instruction


@dataclass
class InterferenceGraph:
    """Represents the interference graph for register allocation."""
    nodes: List[str]
    edges: List[Tuple[str, str]]
    adjacency: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))

    def build_adjacency(self):
        """Build adjacency lists from edge list."""
        self.adjacency = defaultdict(set)
        for node in self.nodes:
            if node not in self.adjacency:
                self.adjacency[node] = set()
        for u, v in self.edges:
            if u not in self.nodes or v not in self.nodes:
                raise ValueError(
                    f"Edge ({u}, {v}) references node not in graph. "
                    f"Known nodes: {sorted(self.nodes)}"
                )
            self.adjacency[u].add(v)
            self.adjacency[v].add(u)

    def degree(self, node: str) -> int:
        """Return the degree of a node."""
        return len(self.adjacency[node])

    def neighbors(self, node: str) -> Set[str]:
        """Return the neighbors of a node."""
        return self.adjacency[node]


@dataclass
class ColoringResult:
    """Result of the graph coloring process."""
    assignments: Dict[str, str]  # vreg -> physical register
    spilled: List[str]  # vregs that were spilled
    coloring_order: List[str]  # order in which nodes were colored
    saturation_at_coloring: Dict[str, int]  # saturation when colored
    conflicts_detected: List[Tuple[str, str]]  # any conflicts found in validation


class DSaturAllocator:
    """
    DSatur-based register allocator.
    
    DSatur (Degree of Saturation) selects the next vertex to color based on
    the number of distinct colors already used by its neighbors (saturation).
    Ties are broken by the configured tie-breaking strategy.
    """

    def __init__(self, config_path: str):
        self.config = configparser.ConfigParser()
        self.config.read(config_path)
        
        self.physical_registers = self.config.get('registers', 'physical_registers').split(',')
        self.num_physical = int(self.config.get('registers', 'num_physical_registers'))
        self.max_instruction_idx = int(self.config.get('program', 'max_instruction_index'))
        self.num_virtual_expected = int(self.config.get('program', 'num_virtual_registers'))
        
        self.base_spill_cost = float(self.config.get('spill', 'base_spill_cost'))
        self.loop_depth_mult = float(self.config.get('spill', 'loop_depth_multiplier'))
        self.low_usage_thresh = int(self.config.get('spill', 'low_usage_threshold'))
        self.low_usage_factor = float(self.config.get('spill', 'low_usage_cost_factor'))
        
        self.strategy = self.config.get('coloring', 'strategy')
        self.tie_break = self.config.get('coloring', 'tie_break')
        
        self.assignments_file = self.config.get('output', 'assignments_file')
        self.spill_report_file = self.config.get('output', 'spill_report_file')
        self.diagnostics_file = self.config.get('output', 'diagnostics_file')

    def load_interference_graph(self, graph_path: str) -> InterferenceGraph:
        """Load interference graph from JSON file."""
        with open(graph_path, 'r') as f:
            data = json.load(f)
        
        nodes = data['nodes']
        edges = [(e['from'], e['to']) for e in data['edges']]
        
        graph = InterferenceGraph(nodes=nodes, edges=edges)
        graph.build_adjacency()
        return graph

    def load_live_ranges(self, ranges_path: str) -> Dict[str, LiveRange]:
        """Load live range data from JSON file."""
        with open(ranges_path, 'r') as f:
            data = json.load(f)
        
        ranges = {}
        for entry in data['ranges']:
            lr = LiveRange(
                vreg=entry['vreg'],
                start_instruction=entry['start_instruction'],
                end_instruction=entry['end_instruction'],
                usage_count=entry['usage_count'],
                loop_depth=entry['loop_depth'],
                def_points=entry.get('def_points', []),
                use_points=entry.get('use_points', [])
            )
            ranges[lr.vreg] = lr
        return ranges

    def load_register_classes(self, classes_path: str) -> Dict[str, List[str]]:
        """Load register class constraints."""
        with open(classes_path, 'r') as f:
            data = json.load(f)
        return data['classes']

    def validate_graph(self, graph: InterferenceGraph, 
                       live_ranges: Dict[str, LiveRange]) -> List[str]:
        """
        Validate that all graph nodes have corresponding live range data.
        Returns list of error messages. Engine FAILS if any node lacks live range data.
        """
        errors = []
        for node in graph.nodes:
            if node not in live_ranges:
                errors.append(
                    f"FATAL: Node '{node}' in interference graph has no live range data. "
                    f"Cannot allocate register for undefined virtual register."
                )
        return errors

    def compute_spill_cost(self, vreg: str, live_range: LiveRange) -> float:
        """
        Compute the spill cost for a virtual register.
        Higher cost = less desirable to spill.
        """
        base = self.base_spill_cost
        depth_factor = 1.0 + (live_range.loop_depth * self.loop_depth_mult)
        usage_factor = live_range.usage_count
        
        if live_range.usage_count < self.low_usage_thresh:
            usage_factor *= self.low_usage_factor
        
        # Normalize by live range length to prefer spilling long-lived registers
        length_factor = max(1, live_range.length)
        
        cost = (base * depth_factor * usage_factor) / length_factor
        return round(cost, 4)

    def select_spill_candidate(self, candidates: List[str],
                                live_ranges: Dict[str, LiveRange],
                                graph: InterferenceGraph) -> str:
        """
        Select the best spill candidate from uncolorable nodes.
        Prefers nodes with lowest spill cost (easiest to spill).
        """
        best = None
        best_cost = float('inf')
        
        for vreg in candidates:
            if vreg in live_ranges:
                cost = self.compute_spill_cost(vreg, live_ranges[vreg])
                # Adjust by degree - higher degree nodes free more resources when spilled
                adjusted_cost = cost / max(1, graph.degree(vreg))
                if adjusted_cost < best_cost:
                    best_cost = adjusted_cost
                    best = vreg
        
        return best if best else candidates[0]

    def dsatur_coloring(self, graph: InterferenceGraph,
                        live_ranges: Dict[str, LiveRange],
                        register_classes: Dict[str, List[str]]) -> ColoringResult:
        """
        Perform DSatur graph coloring with spilling.
        
        Algorithm:
        1. Initialize all nodes as uncolored, saturation = 0
        2. Repeat until all nodes colored or spilled:
           a. Select uncolored node with highest saturation
           b. Break ties by configured strategy
           c. Assign lowest available color from allowed register class
           d. If no color available, mark as spill candidate
           e. Update saturation of neighbors
        3. Process spill candidates
        """
        color_map: Dict[str, Optional[str]] = {}
        saturation: Dict[str, Set[str]] = {n: set() for n in graph.nodes}
        colored_set: Set[str] = set()
        spill_candidates: List[str] = []
        coloring_order: List[str] = []
        sat_at_coloring: Dict[str, int] = {}

        uncolored = set(graph.nodes)

        while uncolored:
            # Select node with maximum saturation
            max_sat = -1
            candidates_for_next = []
            
            for node in uncolored:
                sat_val = len(saturation[node])
                if sat_val > max_sat:
                    max_sat = sat_val
                    candidates_for_next = [node]
                elif sat_val == max_sat:
                    candidates_for_next.append(node)

            # Tie-breaking
            if len(candidates_for_next) > 1:
                if self.tie_break == 'highest_degree':
                    candidates_for_next.sort(
                        key=lambda n: graph.degree(n), reverse=True
                    )
                elif self.tie_break == 'lowest_index':
                    candidates_for_next.sort(
                        key=lambda n: int(n[1:]) if n[1:].isdigit() else 0
                    )
                elif self.tie_break == 'highest_spill_cost':
                    candidates_for_next.sort(
                        key=lambda n: self.compute_spill_cost(n, live_ranges[n])
                        if n in live_ranges else 0,
                        reverse=True
                    )

            selected = candidates_for_next[0]
            uncolored.remove(selected)
            coloring_order.append(selected)
            sat_at_coloring[selected] = len(saturation[selected])

            # Get allowed registers for this virtual register
            allowed = register_classes.get(selected, self.physical_registers[:])
            
            # Find colors used by neighbors
            neighbor_colors = set()
            for neighbor in graph.neighbors(selected):
                if neighbor in color_map and color_map[neighbor] is not None:
                    neighbor_colors.add(color_map[neighbor])

            # Assign first available color from allowed set
            assigned_color = None
            for reg in allowed:
                if reg not in neighbor_colors:
                    assigned_color = reg
                    break

            if assigned_color is not None:
                color_map[selected] = assigned_color
                colored_set.add(selected)
                # Update saturation of uncolored neighbors
                for neighbor in graph.neighbors(selected):
                    if neighbor in uncolored:
                        saturation[neighbor].add(assigned_color)
            else:
                # Cannot color - mark as spill candidate
                color_map[selected] = None
                spill_candidates.append(selected)

        # Validate: check for conflicts in colored assignments
        conflicts = []
        for u, v in graph.edges:
            if (u in color_map and v in color_map and
                color_map[u] is not None and color_map[v] is not None and
                color_map[u] == color_map[v]):
                conflicts.append((u, v))

        # Build final assignments (excluding spilled)
        assignments = {k: v for k, v in color_map.items() if v is not None}

        return ColoringResult(
            assignments=assignments,
            spilled=spill_candidates,
            coloring_order=coloring_order,
            saturation_at_coloring=sat_at_coloring,
            conflicts_detected=conflicts
        )

    def run(self, data_dir: str) -> Tuple[Dict, Dict, Dict]:
        """
        Run the full register allocation process.
        
        Returns: (assignments_data, spill_report, diagnostics)
        """
        graph_path = os.path.join(data_dir, 'interference_graph.json')
        ranges_path = os.path.join(data_dir, 'live_ranges.json')
        classes_path = os.path.join(data_dir, 'register_classes.json')

        # Load data
        graph = self.load_interference_graph(graph_path)
        live_ranges = self.load_live_ranges(ranges_path)
        register_classes = self.load_register_classes(classes_path)

        # Validate
        errors = self.validate_graph(graph, live_ranges)
        if errors:
            error_report = {
                'status': 'FATAL_ERROR',
                'errors': errors,
                'hint': 'All nodes in interference graph must have corresponding live range data'
            }
            return None, None, error_report

        # Validate live ranges don't exceed max instruction index
        range_warnings = []
        for vreg, lr in live_ranges.items():
            if lr.end_instruction > self.max_instruction_idx:
                range_warnings.append(
                    f"WARNING: {vreg} end_instruction={lr.end_instruction} "
                    f"exceeds max_instruction_index={self.max_instruction_idx}"
                )
            if lr.start_instruction > lr.end_instruction:
                error_report = {
                    'status': 'FATAL_ERROR',
                    'errors': [f"Invalid live range for {vreg}: start > end"],
                    'hint': 'Live range start must be <= end'
                }
                return None, None, error_report

        # Perform coloring
        result = self.dsatur_coloring(graph, live_ranges, register_classes)

        # Build output
        assignments_data = {
            'status': 'SUCCESS' if not result.conflicts_detected else 'CONFLICTS_DETECTED',
            'num_colored': len(result.assignments),
            'num_spilled': len(result.spilled),
            'num_conflicts': len(result.conflicts_detected),
            'assignments': result.assignments,
            'conflicts': [{'vreg1': c[0], 'vreg2': c[1], 
                          'register': result.assignments.get(c[0], 'unknown')} 
                         for c in result.conflicts_detected]
        }

        spill_report = {
            'spilled_registers': result.spilled,
            'spill_costs': {
                vreg: self.compute_spill_cost(vreg, live_ranges[vreg])
                for vreg in result.spilled if vreg in live_ranges
            },
            'total_spill_count': len(result.spilled),
            'registers_freed': sum(
                graph.degree(v) for v in result.spilled
            )
        }

        diagnostics = {
            'graph_stats': {
                'num_nodes': len(graph.nodes),
                'num_edges': len(graph.edges),
                'max_degree': max(graph.degree(n) for n in graph.nodes) if graph.nodes else 0,
                'avg_degree': round(
                    sum(graph.degree(n) for n in graph.nodes) / len(graph.nodes), 2
                ) if graph.nodes else 0
            },
            'coloring_order': result.coloring_order,
            'saturation_at_coloring': result.saturation_at_coloring,
            'range_warnings': range_warnings,
            'chromatic_lower_bound': max(
                graph.degree(n) + 1 for n in graph.nodes
            ) if graph.nodes else 0
        }

        return assignments_data, spill_report, diagnostics

    def write_outputs(self, assignments_data, spill_report, diagnostics):
        """Write all output files."""
        os.makedirs(os.path.dirname(self.assignments_file), exist_ok=True)
        os.makedirs(os.path.dirname(self.spill_report_file), exist_ok=True)
        os.makedirs(os.path.dirname(self.diagnostics_file), exist_ok=True)

        if assignments_data is not None:
            with open(self.assignments_file, 'w') as f:
                json.dump(assignments_data, f, indent=2)
        
        if spill_report is not None:
            with open(self.spill_report_file, 'w') as f:
                json.dump(spill_report, f, indent=2)
        
        if diagnostics is not None:
            with open(self.diagnostics_file, 'w') as f:
                json.dump(diagnostics, f, indent=2)
